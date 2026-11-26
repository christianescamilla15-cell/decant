"""Runbook de la carga histórica por mes (S3 paso 3, ADR 0013 y 0016; criterios 4, 5, 11 y 12).

    python -m corte.runbook preparar [--recrear]        # esquemas, roles, catálogo y consumibles en el destino
    python -m corte.runbook ensayo  --mes 2021-01       # el mes en una transacción REVERTIDA sobre el mismo destino
    python -m corte.runbook aplicar --mes 2021-01       # reversa generada antes; sólo INSERT; cuadra o no confirma
    python -m corte.runbook reversa --mes 2021-01       # vuelve a la huella previa o no confirma; negada tras el
                                                        # punto de no retorno
    python -m corte.runbook cierre  [--margen-folios N] # setval desde IDENT_CURRENT, folios con margen, llaves foráneas
    python -m corte.runbook estado

Origen: el respaldo FECHADO restaurado como `BFN_DIVISAS_CORTE` en el SQL Server del legado (DECANT_SA_PASSWORD,
DECANT_PUERTO). Destino: PostgreSQL (DECANT_PG_PASSWORD, DECANT_PG_PUERTO), base `decant_corte`. El corte de cada
tabla sale del manifiesto del respaldo y tiene que ser el medido en el paso 2 (`corte/cifras/corte.json`).

Reglas que el runbook hace cumplir (cada una con su control negativo en `corte/carga_ci.py`):
- `aplicar` exige un ensayo verde del mismo mes, con el mismo plan y sobre la misma huella previa; se niega con un
  automatismo del TO-BE encendido; corre con un rol que sólo puede INSERTAR en las tablas del legado; guarda la
  reversa ANTES de insertar; y confirma sólo si la huella del mes es igual en origen y destino y las filas con
  id ≤ corte siguen idénticas.
- `reversa` revierte sólo el último mes aplicado, con un rol que sólo puede BORRAR, y confirma sólo si el destino
  vuelve a la huella previa (las 7 tablas, las secuencias y los consumibles). Lo que el TO-BE ya trabajó lo dice la
  bitácora de ACCIONES de negocio, nunca el token de concurrencia: desde la primera acción (o el primer aviso al
  exterior) el sistema registra el punto de no retorno y `reversa` se niega.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from corte import carga, codigo
from corte.carga import CON_IDENTIDAD, TABLAS

ORIGEN_BASE = 'BFN_DIVISAS_CORTE'
DESTINO_BASE = 'decant_corte'
DDL = Path(__file__).with_name('destino.sql')
CORTE_MEDIDO = Path(__file__).parent / 'cifras' / 'corte.json'
TRABAJO = codigo.RAIZ / 'corte' / 'carga-trabajo'
LLAVES_FORANEAS = (
    ('fk_operacion_moneda', 'operacion', 'moneda', 'moneda', 'codigo'),
    ('fk_orden_operacion', 'orden_pago', 'operacion_id', 'operacion', 'id'),
    ('fk_orden_moneda', 'orden_pago', 'moneda', 'moneda', 'codigo'),
    ('fk_solicitada_orden', 'partida_solicitada', 'orden_id', 'orden_pago', 'id'),
    ('fk_liquidada_orden', 'partida_liquidada', 'orden_id', 'orden_pago', 'id'),
)


# El SQL del destino que nombra tablas se arma SÓLO aquí, con identificadores de la especificación cerrada
# (`carga.TABLAS`): una tabla que no está ahí es KeyError, nunca texto del usuario.
PLANTILLAS = {
    'max': 'SELECT max(id) FROM {tabla}',
    'filas': 'SELECT {columnas} FROM {tabla} WHERE id > %s AND id <= %s',
    'mas_alla': 'SELECT count(*) FROM {tabla} WHERE id > %s',
    'hasta_el_corte': 'SELECT count(*), max(id) FROM {tabla} WHERE id <= %s',
    'borrar': 'DELETE FROM {tabla} WHERE id > %s AND id <= %s',
    'copiar': 'COPY {tabla} ({columnas}) FROM STDIN',
    'totales': 'SELECT count(*), max(id), sum({monto}) FROM {tabla}',
}


def _q(plantilla: str, tabla: str):
    from psycopg import sql
    t = TABLAS[tabla]
    return sql.SQL(PLANTILLAS[plantilla]).format(
        tabla=sql.Identifier('legado', t.nombre), columnas=sql.SQL(', ').join(map(sql.Identifier, t.nombres)),
        monto=sql.Identifier(t.monto) if t.monto else sql.SQL('NULL::numeric'))


def _q_llave_foranea(nombre: str, tabla: str, columna: str, padre: str, llave: str):
    from psycopg import sql
    return sql.SQL('ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {} ({})').format(
        sql.Identifier('legado', TABLAS[tabla].nombre), sql.Identifier(nombre), sql.Identifier(columna),
        sql.Identifier('legado', TABLAS[padre].nombre), sql.Identifier(llave))


def _q_crear_base(base: str):
    from psycopg import sql
    if not base.replace('_', '').isalnum() or not base.isascii():
        raise Negado(f'nombre de base no válido: {base!r}')
    return sql.SQL('CREATE DATABASE {}').format(sql.Identifier(base))


class Negado(Exception):
    """El runbook se niega a hacer algo: el porqué va en el mensaje y no se escribió nada."""


FOLIOS_DEL_VIVO = 'SELECT serie, siguiente FROM BFN_DIVISAS.dbo.folio ORDER BY serie'


class NoCuadra(Exception):
    """La verificación dentro de la transacción falló: se revirtió y el destino quedó como estaba."""

    def __init__(self, faltas: list[str]):
        super().__init__('; '.join(faltas))
        self.faltas = faltas


# ── conexiones ──────────────────────────────────────────────────────────────────────────────────────────────────

def conectar_origen(base: str = ORIGEN_BASE):
    from legado.conexion import conectar
    return conectar(base)


def conectar_destino(base: str = DESTINO_BASE, crear: bool = False):
    import psycopg

    from paridad.tobe import parametros
    if crear:
        with psycopg.connect(dbname='postgres', autocommit=True, **parametros()) as admin:
            existe = admin.execute('SELECT 1 FROM pg_database WHERE datname = %s', (base,)).fetchone()
            if not existe:
                admin.execute(_q_crear_base(base))
    return psycopg.connect(dbname=base, autocommit=True, **parametros())


# ── el corte y el plan ──────────────────────────────────────────────────────────────────────────────────────────

def cortes(manifiesto: Path | None, medido: Path = CORTE_MEDIDO) -> dict[str, int]:
    """El corte de cada tabla: MAX(id) en el respaldo (manifiesto), que debe ser el corte medido por dos caminos en el
    paso 2 (versionado). Sin manifiesto, el medido."""
    tablas = json.loads(medido.read_text(encoding='utf-8'))['tablas']
    del_paso_2 = {t.removeprefix('dbo.'): v['por_identidad']['corte'] for t, v in tablas.items()
                  if v.get('por_identidad')}
    if manifiesto is None:
        return del_paso_2
    del_respaldo = {t.removeprefix('dbo.'): v['max_id']
                    for t, v in json.loads(manifiesto.read_text(encoding='utf-8'))['tablas'].items()
                    if t.removeprefix('dbo.') in del_paso_2}
    if del_respaldo != del_paso_2:
        raise Negado(f'el corte del respaldo {del_respaldo} no es el medido por dos caminos en el paso 2 '
                     f'{del_paso_2}')
    return del_respaldo


def leer_plan(ms, corte: dict[str, int], grieta: str | None = None) -> dict:
    cursor = ms.cursor()
    agregados, totales = {}, {}
    for t in CON_IDENTIDAD:
        cursor.execute(carga.PLAN[t.nombre], {'corte': corte[t.nombre], **carga.ventana_grieta(grieta)})
        agregados[t.nombre] = cursor.fetchall()
        cursor.execute(carga.TOTALES[t.nombre], {'corte': corte[t.nombre]})
        totales[t.nombre] = cursor.fetchone()
    return carga.plan(agregados, totales, corte, grieta=grieta)


# ── lecturas del destino ────────────────────────────────────────────────────────────────────────────────────────

def _q_huella(tabla: carga.Tabla):
    from psycopg import sql
    return sql.SQL("""SELECT count(*), {maximo}, encode(sha256(convert_to(coalesce(string_agg(
    encode(sha256(convert_to(t::text, 'UTF8')), 'hex'), '' ORDER BY t.{llave}), ''), 'UTF8')), 'hex')
FROM {tabla} AS t""").format(
        maximo=sql.SQL('max(t.id)') if tabla.identidad else sql.SQL('NULL'),
        llave=sql.Identifier(tabla.nombres[0]), tabla=sql.Identifier('legado', tabla.nombre))


def huella_destino(pg) -> dict:
    """La huella del destino: por tabla (filas, MAX(id) y sha256 de las huellas de sus filas en orden, con la forma
    de texto de PostgreSQL de cada renglón), el estado de cada secuencia y los consumibles."""
    tablas = {}
    for t in TABLAS.values():
        filas, maximo, sha = pg.execute(_q_huella(t)).fetchone()
        tablas[t.nombre] = {'filas': filas, 'max_id': maximo, 'huella': sha}
    secuencias = {}
    for t in CON_IDENTIDAD:
        valor, llamado = pg.execute(_q_secuencia(t)).fetchone()
        secuencias[t.nombre] = {'last_value': valor, 'is_called': llamado}
    folios = {s: {'siguiente': n, 'actualizado': None if a is None else a.isoformat()}
              for s, n, a in pg.execute('SELECT serie, siguiente, actualizado FROM legado.folio ORDER BY serie')}
    return {'tablas': tablas, 'secuencias': secuencias, 'folios': folios}


def _q_secuencia(t: carga.Tabla):
    from psycopg import sql
    return sql.SQL('SELECT last_value, is_called FROM {}').format(sql.Identifier('legado', t.secuencia))


def maximos(pg) -> dict[str, int | None]:
    return {t.nombre: pg.execute(_q('max', t.nombre)).fetchone()[0] for t in CON_IDENTIDAD}


def registro(pg) -> dict[str, int]:
    """Hasta dónde llega cada tabla según los meses APLICADOS del registro (el segundo camino del corte del destino)."""
    resultado: dict[str, int] = {}
    for (rangos,) in pg.execute("SELECT rangos FROM corte.carga_mes WHERE estado = 'aplicado'"):
        for t, r in rangos.items():
            if r['filas']:
                resultado[t] = max(resultado.get(t, 0), r['hasta'])
    return resultado


def encendidos(pg) -> list[str]:
    return [n for (n,) in pg.execute('SELECT nombre FROM corte.interruptor WHERE encendido ORDER BY nombre')]


def no_retorno(pg) -> dict | None:
    fila = pg.execute('SELECT instante, motivo, referencia FROM corte.no_retorno').fetchone()
    return None if fila is None else {'instante': fila[0].isoformat(), 'motivo': fila[1], 'referencia': fila[2]}


INDICES_UNICOS_DESTINO = """SELECT t.relname, i.relname, a.attname, k.ord
FROM pg_index x
JOIN pg_class i ON i.oid = x.indexrelid
JOIN pg_class t ON t.oid = x.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
CROSS JOIN LATERAL unnest(x.indkey) WITH ORDINALITY AS k(attnum, ord)
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
WHERE n.nspname = 'legado' AND x.indisunique
ORDER BY 1, 2, 4"""


def mismos_indices_unicos(ms, pg) -> dict:
    cursor = ms.cursor()
    cursor.execute(carga.INDICES_UNICOS_ORIGEN)
    origen = carga.indices_unicos(cursor.fetchall())
    destino = carga.indices_unicos(pg.execute(INDICES_UNICOS_DESTINO).fetchall())
    return {'origen': origen, 'destino': destino, 'iguales': origen == destino}


# ── lecturas del origen ─────────────────────────────────────────────────────────────────────────────────────────

def filas_por_rango(ms, tabla: str, desde: int, hasta: int) -> list[tuple]:
    cursor = ms.cursor()
    cursor.execute(carga.POR_RANGO[tabla], {'desde': desde, 'hasta': hasta})
    return [tuple(f) for f in cursor.fetchall()]


def huella_origen_mes(ms, mes: str, corte: dict[str, int]) -> dict[str, dict]:
    """El mes de VERDAD: las filas por su sello en hora local, sin mirar el plan."""
    inicio, fin = carga.frontera(mes)
    cursor = ms.cursor()
    resultado = {}
    for t in CON_IDENTIDAD:
        cursor.execute(carga.POR_SELLO[t.nombre], {'inicio': inicio, 'fin': fin, 'corte': corte[t.nombre]})
        resultado[t.nombre] = carga.huella_de_filas(t, (tuple(f) for f in cursor.fetchall()))
    return resultado


def huella_destino_mes(pg, rango: dict[str, dict]) -> dict[str, dict]:
    resultado = {}
    for t in CON_IDENTIDAD:
        r = rango[t.nombre]
        filas = pg.execute(_q('filas', t.nombre), (r['desde'], r['hasta'])).fetchall()
        resultado[t.nombre] = carga.huella_de_filas(t, filas)
    return resultado


# ── preparar ────────────────────────────────────────────────────────────────────────────────────────────────────

def preparar(pg, ms, recrear: bool = False) -> dict:
    """Esquemas, roles, catálogo (monedas, que no tienen mes) y consumibles en cero. Antes de nada más, los MISMOS
    índices únicos que el origen."""
    existe = pg.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'legado'").fetchone()
    if existe and not recrear:
        raise Negado('el destino ya está preparado (usa --recrear para empezar de cero)')
    with pg.transaction():
        if existe:
            pg.execute('DROP SCHEMA legado CASCADE; DROP SCHEMA corte CASCADE')
        pg.execute(DDL.read_text(encoding='utf-8'))
        cursor = ms.cursor()
        cursor.execute(carga.CATALOGO['moneda'])
        monedas = [tuple(f) for f in cursor.fetchall()]
        with pg.cursor().copy(_q('copiar', 'moneda')) as copia:
            for fila in monedas:
                copia.write_row(fila)
        cursor.execute(carga.CATALOGO['folio'])
        series = [s for s, _n, _a in cursor.fetchall()]
        for serie in series:
            pg.execute('INSERT INTO legado.folio (serie, siguiente, actualizado) VALUES (%s, 1, NULL)', (serie,))
    indices = mismos_indices_unicos(ms, pg)
    if not indices['iguales']:
        raise Negado(f"el destino no tiene los mismos índices únicos que el origen: {indices}")
    origen_monedas = carga.huella_de_filas(TABLAS['moneda'], monedas)
    destino_monedas = carga.huella_de_filas(TABLAS['moneda'], pg.execute(
        'SELECT codigo, numerico, nombre, decimales, activa FROM legado.moneda').fetchall())
    if origen_monedas != destino_monedas:
        raise NoCuadra([f'moneda: origen {origen_monedas} ≠ destino {destino_monedas}'])
    return {'monedas': origen_monedas, 'series': series, 'indices_unicos': indices['destino'],
            'indices_unicos_iguales': indices['iguales']}


# ── ensayo y aplicar ────────────────────────────────────────────────────────────────────────────────────────────

def _ultimo_ensayo(pg, mes: str, sha: str) -> tuple[bool, dict] | None:
    fila = pg.execute('SELECT verde, huella_previa FROM corte.ensayo WHERE mes = %s AND plan_sha = %s '
                      'ORDER BY id DESC LIMIT 1', (mes, sha)).fetchone()
    return None if fila is None else (fila[0], fila[1])


def _jsonb(valor):
    from psycopg.types.json import Jsonb
    return Jsonb(valor)


def cargar_mes(pg, ms, p: dict, mes: str, corte: dict[str, int], *, confirmar: bool,
               plantar: dict[str, list[tuple]] | None = None, sin_guarda: bool = False,
               trabajo: Path | None = None) -> dict:
    """El corazón de `ensayo` (confirmar=False: todo en una transacción que se revierte) y de `aplicar`.
    `plantar` y `sin_guarda` existen sólo para los controles negativos: no se exponen en la línea de órdenes."""
    t0 = time.monotonic()
    verbo = 'aplicar' if confirmar else 'ensayo'
    if mes not in p['meses']:
        raise Negado(f'{mes} no es uno de los {len(p["meses"])} meses del plan')
    if p['faltas'] and not sin_guarda:
        raise Negado(f"el plan no parte por rangos contiguos: {p['faltas'][:5]}")
    rango = carga.rangos(p, mes)
    previa = huella_destino(pg)
    if confirmar:
        prendidos = encendidos(pg)
        if prendidos:
            raise Negado(f'hay automatismos del TO-BE encendidos: {prendidos}; se apagan antes de aplicar')
    actual, faltas = carga.corte_del_destino(maximos(pg), registro(pg))
    if faltas:
        raise Negado(f'el corte del destino no coincide por sus dos caminos: {faltas}')
    if not sin_guarda:
        faltas = carga.guarda_de_rangos(rango, actual)
        if faltas:
            raise Negado(f'{mes}: sólo ids > corte: {faltas}')
    if confirmar:
        ensayado = _ultimo_ensayo(pg, mes, p['sha'])
        if ensayado is None or not ensayado[0]:
            raise Negado(f'{mes}: no hay un ensayo verde con este plan ({p["sha"][:12]}); un choque en el ensayo '
                         'detiene el corte')
        cambios = carga.diferencias_de_huella(ensayado[1], previa)
        if cambios:
            raise Negado(f'{mes}: el destino cambió desde el ensayo: {cambios[:5]}')
    t1 = time.monotonic()
    origen = huella_origen_mes(ms, mes, corte)
    lotes = {t.nombre: filas_por_rango(ms, t.nombre, rango[t.nombre]['desde'], rango[t.nombre]['hasta'])
             if rango[t.nombre]['filas'] else [] for t in CON_IDENTIDAD}
    for t, extra in (plantar or {}).items():
        lotes[t] = [*lotes[t], *extra]
    if not sin_guarda:
        for t in CON_IDENTIDAD:
            fuera = carga.ids_fuera((f[0] for f in lotes[t.nombre]), rango[t.nombre]['desde'],
                                    rango[t.nombre]['hasta'], actual[t.nombre])
            if fuera:
                raise Negado(f'{mes}: {t.nombre} trae {len(fuera)} filas con id ≤ corte {actual[t.nombre]} o fuera '
                             f'de su rango: {fuera[:carga.MUESTRA]}')
    t2 = time.monotonic()
    folios = carga.folios_del_lote(lotes)
    rev = carga.reversa(mes, p, previa)
    registro_id = None
    if confirmar:
        registro_id = pg.execute(
            'INSERT INTO corte.carga_mes (mes, plan_sha, estado, rangos, reversa, huella_previa) '
            "VALUES (%s, %s, 'reversa_generada', %s, %s, %s) RETURNING id",
            (mes, p['sha'], _jsonb(rango), _jsonb(rev), _jsonb(rev['huella_previa']))).fetchone()[0]
        if trabajo is not None:
            trabajo.mkdir(parents=True, exist_ok=True)
            (trabajo / f'reversa_{mes}.json').write_text(json.dumps(rev, ensure_ascii=False, indent=1) + '\n',
                                                         encoding='utf-8')
    resultado = {'mes': mes, 'verbo': verbo, 'plan_sha': p['sha'], 'corte_del_destino': actual, 'previa': previa,
                 'filas': {t: len(v) for t, v in lotes.items()}, 'rangos': rango, 'folios': folios,
                 'huella_origen': origen}
    try:
        with pg.transaction(force_rollback=not confirmar):
            pg.execute('SET LOCAL ROLE decant_corte_aplica')        # sólo INSERT en las tablas del legado
            txid = pg.execute('SELECT txid_current()').fetchone()[0]
            for t in CON_IDENTIDAD:
                if not lotes[t.nombre]:
                    continue
                with pg.cursor().copy(_q('copiar', t.nombre)) as copia:
                    for fila in lotes[t.nombre]:
                        copia.write_row(fila)
                pg.execute('SELECT setval(%s::regclass, %s, true)',
                           (f'legado.{t.secuencia}', max(f[0] for f in lotes[t.nombre])))
            for serie, valor in sorted(folios.items()):
                pg.execute('UPDATE legado.folio SET siguiente = GREATEST(siguiente, %s) WHERE serie = %s',
                           (valor, serie))
            destino = huella_destino_mes(pg, rango)
            resultado['huella_destino'] = destino
            faltas = carga.comparar_mes(origen, destino)
            # 0 filas nuevas con id ≤ corte: el rol no puede actualizar ni borrar y el índice único no deja repetir un
            # id, así que basta contar (la reversa compara después la huella completa de esas mismas filas)
            cambiadas = []
            for t in CON_IDENTIDAD:
                filas, maximo = pg.execute(_q('hasta_el_corte', t.nombre), (actual[t.nombre],)).fetchone()
                antes = previa['tablas'][t.nombre]
                if (filas, maximo) != (antes['filas'], antes['max_id']):
                    cambiadas.append(t.nombre)
                    faltas.append(f'{t.nombre}: con id ≤ corte {actual[t.nombre]} había {antes["filas"]} filas '
                                  f'(MAX {antes["max_id"]}) y ahora {filas} (MAX {maximo})')
                mas_alla = pg.execute(_q('mas_alla', t.nombre), (rango[t.nombre]['hasta'],)).fetchone()[0]
                if mas_alla:
                    faltas.append(f'{t.nombre}: {mas_alla} filas después del fin del mes ({rango[t.nombre]["hasta"]})')
            resultado['tablas_con_filas_nuevas_hasta_el_corte'] = cambiadas
            if faltas:
                raise NoCuadra(faltas)
            if confirmar:
                pg.execute("UPDATE corte.carga_mes SET estado = 'aplicado', carga_txid = %s, huella_mes = %s, "
                           'aplicada_en = clock_timestamp() WHERE id = %s',
                           (txid, _jsonb({'origen': origen, 'destino': destino}), registro_id))
    except Exception as error:
        _restaurar_secuencias(pg, previa['secuencias'])
        if confirmar and registro_id is not None:
            pg.execute("UPDATE corte.carga_mes SET estado = 'fallido', detalle = %s WHERE id = %s",
                       (str(error)[:2000], registro_id))
        if not confirmar:
            _anotar_ensayo(pg, mes, p['sha'], previa, False, {**_sin_huellas(resultado), 'error': str(error)[:2000]})
        raise
    resultado['segundos'] = {'guardas': round(t1 - t0, 2), 'leer_origen': round(t2 - t1, 2),
                             'escribir_y_verificar': round(time.monotonic() - t2, 2)}
    if not confirmar:
        _restaurar_secuencias(pg, previa['secuencias'])
        _anotar_ensayo(pg, mes, p['sha'], previa, True, _sin_huellas(resultado))
    return resultado


def _restaurar_secuencias(pg, secuencias: dict[str, dict]) -> None:
    """`setval` NO es transaccional en PostgreSQL: una transacción revertida (el ensayo, o una verificación que no
    cuadra) deja las secuencias donde las movió. Se regresan aquí, a los valores leídos antes (si no, la huella lo
    ve)."""
    for t, s in sorted(secuencias.items()):
        pg.execute('SELECT setval(%s::regclass, %s, %s)', (f'legado.{TABLAS[t].secuencia}', s['last_value'],
                                                            s['is_called']))


def _sin_huellas(resultado: dict) -> dict:
    return {k: v for k, v in resultado.items() if k not in ('huella_origen', 'huella_destino', 'previa')}


def _anotar_ensayo(pg, mes: str, sha: str, previa: dict, verde: bool, resultado: dict) -> None:
    pg.execute('INSERT INTO corte.ensayo (mes, plan_sha, huella_previa, verde, resultado) VALUES (%s, %s, %s, %s, %s)',
               (mes, sha, _jsonb({'tablas': previa['tablas'], 'secuencias': previa['secuencias']}), verde,
                _jsonb(json.loads(json.dumps(resultado, default=str)))))


# ── reversa ─────────────────────────────────────────────────────────────────────────────────────────────────────

def revertir(pg, mes: str, *, restaurar_secuencias: bool = True,
             excluir: Callable[[object, str, dict, int | None], object] | None = None) -> dict:
    """Ejecuta la reversa GUARDADA del último mes aplicado y confirma sólo si el destino vuelve a la huella previa.
    `restaurar_secuencias=False` y `excluir` existen sólo para los controles negativos (reversas plantadas)."""
    t0 = time.monotonic()
    punto = no_retorno(pg)
    if punto is not None:
        raise Negado(f"punto de no retorno registrado el {punto['instante']} ({punto['motivo']}: "
                     f"{punto['referencia']}): volver a la huella previa borraría lo capturado; sólo hacia adelante")
    fila = pg.execute("SELECT id, reversa, carga_txid FROM corte.carga_mes WHERE mes = %s AND estado = 'aplicado' "
                      'ORDER BY id DESC LIMIT 1', (mes,)).fetchone()
    if fila is None:
        raise Negado(f'{mes} no está aplicado: no hay reversa que correr')
    registro_id, rev, txid = fila
    ultimo = pg.execute("SELECT max(id) FROM corte.carga_mes WHERE estado = 'aplicado'").fetchone()[0]
    if ultimo != registro_id:
        raise Negado(f'{mes} no es el último mes aplicado: las reversas van en orden inverso')
    trabajadas = []
    for t, r in rev['borrar'].items():
        trabajadas += pg.execute('SELECT id, accion, fila FROM corte.accion_negocio WHERE tabla = %s AND fila > %s '
                                 'AND fila <= %s', (f'legado.{t}', r['desde'], r['hasta'])).fetchall()
    if trabajadas:
        raise Negado(f'{mes}: el TO-BE ya trabajó filas del mes (bitácora de acciones de negocio): {trabajadas[:10]}')
    borradas: dict = {}
    antes = huella_destino(pg)['secuencias']
    try:
        ahora = _ejecutar_reversa(pg, registro_id, rev, txid, borradas, restaurar_secuencias, excluir)
    except Exception:
        _restaurar_secuencias(pg, antes)
        raise
    return {'mes': mes, 'borradas': borradas, 'huella': 'igual a la previa', 'ahora': ahora,
            'segundos': round(time.monotonic() - t0, 2)}


def _ejecutar_reversa(pg, registro_id: int, rev: dict, txid: int | None, borradas: dict, restaurar_secuencias: bool,
                      excluir) -> dict:
    with pg.transaction():
        pg.execute('SET LOCAL ROLE decant_corte_revierte')          # sólo DELETE en las tablas del legado
        for t, r in sorted(rev['borrar'].items()):
            borrar = _q('borrar', t) if excluir is None else excluir(_q('borrar', t), t, r, txid)
            borradas[t] = pg.execute(borrar, (r['desde'], r['hasta'])).rowcount
        if restaurar_secuencias:
            for t, s in sorted(rev['secuencias'].items()):
                pg.execute('SELECT setval(%s::regclass, %s, %s)',
                           (f'legado.{TABLAS[t].secuencia}', s['last_value'], s['is_called']))
        for serie, valor in sorted(rev['folios'].items()):
            pg.execute('UPDATE legado.folio SET siguiente = %s WHERE serie = %s', (valor, serie))
        ahora = huella_destino(pg)
        faltas = carga.diferencias_de_huella(rev['huella_previa'], ahora)
        if faltas:
            raise NoCuadra(faltas)
        pg.execute("UPDATE corte.carga_mes SET estado = 'revertido', revertida_en = clock_timestamp() WHERE id = %s",
                   (registro_id,))
    return ahora


# ── cierre ──────────────────────────────────────────────────────────────────────────────────────────────────────

def cerrar(pg, ms, p: dict, corte: dict[str, int], margen: int, vivo: bool = True) -> dict:
    """Con los 36 meses aplicados: setval de cada secuencia desde IDENT_CURRENT del origen (no desde MAX(id)), los
    consumibles con margen ANTES del delta, las llaves foráneas validadas y los totales globales de cada tabla."""
    if pg.execute("SELECT 1 FROM pg_constraint WHERE conname = %s", (LLAVES_FORANEAS[0][0],)).fetchone():
        raise Negado('el destino ya está cerrado (tiene sus llaves foráneas): el cierre corre una sola vez')
    aplicados = {m for (m,) in pg.execute("SELECT DISTINCT mes FROM corte.carga_mes WHERE estado = 'aplicado'")}
    faltan = [m for m in p['meses'] if m not in aplicados]
    if faltan:
        raise Negado(f'faltan {len(faltan)} meses por aplicar: {faltan[:6]}')
    cursor = ms.cursor()
    totales, faltas = {}, []
    for t in CON_IDENTIDAD:
        cursor.execute(carga.TOTALES[t.nombre], {'corte': corte[t.nombre]})
        filas, maximo, monto = cursor.fetchone()
        cursor.execute(carga.IDENT_CURRENT[t.nombre])
        ident = int(cursor.fetchone()[0])
        d_filas, d_max, d_monto = pg.execute(_q('totales', t.nombre)).fetchone()
        totales[t.nombre] = {'origen': {'filas': int(filas), 'max_id': int(maximo), 'monto': None if monto is None
                                        else format(monto, 'f'), 'ident_current': ident},
                             'destino': {'filas': d_filas, 'max_id': d_max,
                                         'monto': None if d_monto is None else format(d_monto, 'f')}}
        o, d = totales[t.nombre]['origen'], totales[t.nombre]['destino']
        if (o['filas'], o['max_id'], o['monto']) != (d['filas'], d['max_id'], d['monto']):
            faltas.append(f'{t.nombre}: origen {o} ≠ destino {d}')
    cursor.execute(carga.CATALOGO['folio'])
    folios_origen = {s: (int(n), a) for s, n, a in cursor.fetchall()}
    usados_vivo = {}
    if vivo:            # el legado siguió consumiendo folios después del respaldo: el margen debe quedar arriba
        cursor.execute(FOLIOS_DEL_VIVO)
        usados_vivo = {s: int(n) for s, n in cursor.fetchall()}
    consumibles = {}
    for serie, (siguiente, _actualizado) in sorted(folios_origen.items()):
        nuevo = siguiente + margen
        consumibles[serie] = {'origen': siguiente, 'margen': margen, 'destino': nuevo,
                              'legado_vivo_ya_usa_hasta': usados_vivo.get(serie)}
        if serie in usados_vivo and nuevo <= usados_vivo[serie]:
            faltas.append(f'folio {serie}: el margen no alcanza: {nuevo} ≤ {usados_vivo[serie]} que el legado ya usa')
    if faltas:
        raise NoCuadra(faltas)
    with pg.transaction():
        for t in CON_IDENTIDAD:
            pg.execute('SELECT setval(%s::regclass, %s, true)',
                       (f'legado.{t.secuencia}', totales[t.nombre]['origen']['ident_current']))
        for serie, c in consumibles.items():
            pg.execute('UPDATE legado.folio SET siguiente = %s, actualizado = %s WHERE serie = %s',
                       (c['destino'], folios_origen[serie][1], serie))
        for llave_foranea in LLAVES_FORANEAS:
            pg.execute(_q_llave_foranea(*llave_foranea))
    secuencias = huella_destino(pg)['secuencias']
    return {'totales': totales, 'consumibles': consumibles, 'secuencias': secuencias,
            'llaves_foraneas': [n for n, *_ in LLAVES_FORANEAS]}


def estado(pg) -> dict:
    return {'meses': [{'mes': m, 'estado': e, 'aplicada_en': str(a), 'revertida_en': str(r)} for m, e, a, r in
                      pg.execute('SELECT mes, estado, aplicada_en, revertida_en FROM corte.carga_mes ORDER BY id')],
            'interruptores_encendidos': encendidos(pg), 'no_retorno': no_retorno(pg),
            'huella': huella_destino(pg)}


# ── línea de órdenes ────────────────────────────────────────────────────────────────────────────────────────────

def _ultimo_manifiesto() -> Path | None:
    candidatos = sorted((codigo.RAIZ / 'respaldos').glob('respaldo_*.json'))
    return candidatos[-1] if candidatos else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.runbook', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('verbo', choices=('preparar', 'ensayo', 'aplicar', 'reversa', 'cierre', 'estado'))
    parser.add_argument('--mes')
    parser.add_argument('--recrear', action='store_true')
    parser.add_argument('--margen-folios', type=int, default=10_000)
    parser.add_argument('--manifiesto', type=Path, default=None)
    parser.add_argument('--origen-base', default=os.environ.get('DECANT_CORTE_ORIGEN', ORIGEN_BASE))
    parser.add_argument('--destino-base', default=os.environ.get('DECANT_CORTE_DESTINO', DESTINO_BASE))
    parser.add_argument('--trabajo', type=Path, default=TRABAJO)
    args = parser.parse_args(argv)
    if args.verbo in ('ensayo', 'aplicar', 'reversa') and not args.mes:
        parser.error(f'{args.verbo} necesita --mes AAAA-MM')
    manifiesto = args.manifiesto or _ultimo_manifiesto()
    try:
        with conectar_destino(args.destino_base, crear=args.verbo == 'preparar') as pg:
            if args.verbo == 'estado':
                print(json.dumps(estado(pg), ensure_ascii=False, indent=1, default=str))
                return 0
            if args.verbo == 'reversa':
                salida = {k: v for k, v in revertir(pg, args.mes).items() if k != 'ahora'}
                print(json.dumps(salida, ensure_ascii=False, indent=1, default=str))
                return 0
            corte = cortes(manifiesto)
            with conectar_origen(args.origen_base) as ms:
                if args.verbo == 'preparar':
                    salida = preparar(pg, ms, recrear=args.recrear)
                else:
                    p = leer_plan(ms, corte)
                    if args.verbo == 'cierre':
                        salida = cerrar(pg, ms, p, corte, args.margen_folios)
                    else:
                        salida = _sin_huellas(cargar_mes(pg, ms, p, args.mes, corte, confirmar=args.verbo == 'aplicar',
                                                         trabajo=args.trabajo))
        print(json.dumps(salida, ensure_ascii=False, indent=1, default=str))
        return 0
    except (Negado, NoCuadra) as error:
        print(f'{args.verbo}: {type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
