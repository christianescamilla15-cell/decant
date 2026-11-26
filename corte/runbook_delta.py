"""Runbook del delta del mismo día (S3 paso 4, ADR 0013 y 0016; criterios 5, 7, 8 y 12).

    python -m corte.runbook_delta preparar     # registro y roles del delta, sobre la base cerrada
    python -m corte.runbook_delta ensayo       # el delta en una transacción REVERTIDA sobre el mismo destino
    python -m corte.runbook_delta aplicar      # reversa generada antes; INSERT + UPDATE acotado; cuadra o no confirma
    python -m corte.runbook_delta reversa      # vuelve a la huella previa o no confirma; negada tras el no retorno
    python -m corte.runbook_delta cifras       # cifras de control del destino contra las versionadas del paso 2
    python -m corte.runbook_delta estado

Origen: el legado VIVO (`BFN_DIVISAS`, el que deja ./ciclo.sh) y la foto del congelamiento (`legado/datos/vivo_*.json`).
Destino: la base cerrada (`decant_corte`, DECANT_PG_PASSWORD, DECANT_PG_PUERTO). El corte es el del manifiesto del
respaldo y el congelamiento el de la foto del vivo; los dos tienen que ser los medidos por dos caminos en el paso 2.

Reglas que hace cumplir (cada una con su control negativo en `corte/delta_ci.py`):
- el delta se toma POR ID: la selección se compara con el rango de la identidad (corte, congelamiento] y lo que falta
  se nombra;
- `aplicar` exige un ensayo verde del mismo plan sobre la misma huella previa, se niega con un automatismo encendido o
  si el delta ya está aplicado (también la base lo impide), corre con un rol que inserta y actualiza SÓLO las columnas
  que el legado cambia, guarda la reversa (con los valores previos) ANTES de escribir y confirma sólo si: cada lote es
  igual en origen y destino, las filas actualizadas quedan como el origen al congelamiento, el resto de las filas del
  corte sigue idéntico, no queda nada después del congelamiento, el catálogo es el del congelamiento, hay 0 duplicados
  por documento y 0 choques de folio;
- `reversa` se niega desde el punto de no retorno y confirma sólo si el destino vuelve a la huella previa (las 7
  tablas, las secuencias y los folios).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from corte import carga, cifras, codigo, delta, runbook
from corte.carga import TABLAS
from corte.cifras import Contexto, Operacion, Partida, Registro
from corte.delta import MUTABLES, ORDEN_BORRAR, ORDEN_INSERTAR
from corte.runbook import Negado, NoCuadra, _jsonb, _q, _restaurar_secuencias

DDL = Path(__file__).with_name('delta.sql')
ORIGEN_VIVO = 'BFN_DIVISAS'
CIFRAS = Path(__file__).parent / 'cifras'
CIFRAS_PASO_2 = CIFRAS / 'cifras-de-control.json'
HUELLA_PASO_2 = CIFRAS / 'huella.json'
DATOS = codigo.RAIZ / 'legado' / 'datos'
TRABAJO = codigo.RAIZ / 'corte' / 'delta-trabajo'
ROL_APLICA, ROL_REVIERTE = 'decant_corte_delta_aplica', 'decant_corte_delta_revierte'
MUESTRA = delta.MUESTRA

# Duplicados por documento EN EL DESTINO: más de un registro vigente por (uetr, sucursal de su operación).
DUPLICADOS = """SELECT o.uetr, p.sucursal, array_agg(o.id ORDER BY o.id)
FROM legado.orden_pago o LEFT JOIN legado.operacion p ON p.id = o.operacion_id
WHERE o.estatus <> 'REEMPLAZADA'
GROUP BY o.uetr, p.sucursal HAVING count(*) > 1 ORDER BY 1, 2"""

# Los registros viejos que SALEN: REEMPLAZADA y con un registro vigente del mismo documento que entró en el delta.
SALEN = """SELECT v.id, n.id
FROM legado.orden_pago v
JOIN legado.operacion p ON p.id = v.operacion_id
JOIN legado.orden_pago n ON n.uetr = v.uetr AND n.estatus <> 'REEMPLAZADA' AND n.id > %s
JOIN legado.operacion q ON q.id = n.operacion_id AND q.sucursal = p.sucursal
WHERE v.id = ANY(%s::bigint[]) AND v.estatus = 'REEMPLAZADA'
ORDER BY v.id"""


# ── SQL del destino armado sólo con identificadores de la especificación cerrada (`carga.TABLAS`) ───────────────

def _q_por_ids(tabla: str):
    """Las filas de una lista de llaves (ids, o códigos de moneda), con el arreglo del tipo de la llave."""
    from psycopg import sql
    t = TABLAS[tabla]
    arreglo = sql.SQL('%s::bigint[]' if t.identidad else '%s::text[]')
    return sql.SQL('SELECT {} FROM {} WHERE {} = ANY({}) ORDER BY {}').format(
        sql.SQL(', ').join(map(sql.Identifier, t.nombres)), sql.Identifier('legado', t.nombre),
        sql.Identifier(t.nombres[0]), arreglo, sql.Identifier(t.nombres[0]))


def _q_huella_hasta(tabla: str):
    """sha256 de las filas con id ≤ corte que NO están en la lista (en el servidor, como `runbook.huella_destino`)."""
    from psycopg import sql
    return sql.SQL("""SELECT count(*), encode(sha256(convert_to(coalesce(string_agg(
    encode(sha256(convert_to(t::text, 'UTF8')), 'hex'), '' ORDER BY t.id), ''), 'UTF8')), 'hex')
FROM {tabla} AS t WHERE t.id <= %s AND NOT (t.id = ANY(%s::bigint[]))""").format(
        tabla=sql.Identifier('legado', TABLAS[tabla].nombre))


def _q_actualizar(tabla: str):
    """UPDATE sólo de las columnas mutables de la tabla, por su llave."""
    from psycopg import sql
    t = TABLAS[tabla]
    return sql.SQL('UPDATE {} SET {} WHERE {} = %s').format(
        sql.Identifier('legado', t.nombre),
        sql.SQL(', ').join(sql.SQL('{} = %s').format(sql.Identifier(c)) for c in MUTABLES[tabla]),
        sql.Identifier(t.nombres[0]))


def _q_max_folio(tabla: str):
    from psycopg import sql
    return sql.SQL("SELECT max(substr(folio, 4)::bigint) FROM {} WHERE folio ~ %s").format(
        sql.Identifier('legado', TABLAS[tabla].nombre))


def _q_rol(rol: str):
    from psycopg import sql
    return sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(rol))


# ── preparar ────────────────────────────────────────────────────────────────────────────────────────────────────

def preparar(pg) -> dict:
    """Registro y roles del delta (`delta.sql`), una vez, sobre la base cerrada."""
    if pg.execute("SELECT to_regclass('corte.carga_delta')").fetchone()[0] is not None:
        raise Negado('el delta ya está preparado en este destino')
    if pg.execute("SELECT to_regclass('corte.carga_mes')").fetchone()[0] is None:
        raise Negado('el destino no tiene la carga por mes: el delta va sobre la base cerrada')
    with pg.transaction():
        pg.execute(DDL.read_text(encoding='utf-8'))
    return {'registro': ['corte.carga_delta', 'corte.ensayo_delta'], 'roles': [ROL_APLICA, ROL_REVIERTE]}


# ── leer el delta (origen vivo + destino) ───────────────────────────────────────────────────────────────────────

def foto_del_catalogo(vivo: dict) -> list[tuple] | None:
    filas = (vivo.get('al_congelamiento', {}).get('catalogo') or {}).get('moneda')
    return None if filas is None else [tuple(f) for f in filas]


def leer_delta(pg, ms, corte: dict[str, int], tope: dict[str, int], vivo: dict) -> dict:
    """Lee del legado vivo y del destino todo lo que el delta necesita y arma su plan (con su sha)."""
    t0 = time.monotonic()
    cursor = ms.cursor()
    cursor.execute(delta.CAMBIOS, {'corte': corte['bitacora']})
    cambios = delta.cambios_por_bitacora(cursor.fetchall(), corte, tope)
    faltas = list(cambios['faltas'])
    lotes = {t: runbook.filas_por_rango(ms, t, corte[t], tope[t]) for t in ORDEN_INSERTAR}
    identidad = {t: [f[0] for f in lotes[t]] for t in ORDEN_INSERTAR}
    # las órdenes, al congelamiento: las del lote (entran así) y las del corte (las que cambiaron se actualizan)
    del_corte = runbook.filas_por_rango(ms, 'orden_pago', 0, corte['orden_pago'])
    ordenes, f = delta.al_congelamiento([*del_corte, *lotes['orden_pago']], cambios['posteriores'])
    faltas += f
    del_corte = [r for r in ordenes if r[0] <= corte['orden_pago']]
    lotes['orden_pago'] = [r for r in ordenes if r[0] > corte['orden_pago']]
    en_destino = pg.execute(_q('filas', 'orden_pago'), (0, corte['orden_pago'])).fetchall()
    actualizar, f = delta.actualizaciones(del_corte, en_destino, cambios['al_corte'])
    faltas += f
    actualizadas_origen = [r for r in del_corte if r[0] in actualizar]
    # el catálogo: la foto del congelamiento contra el destino (y contra el legado de ahora: lo posterior)
    cursor.execute(carga.CATALOGO['moneda'])
    monedas_vivo = [tuple(r) for r in cursor.fetchall()]
    monedas_destino = [tuple(r) for r in pg.execute(
        'SELECT codigo, numerico, nombre, decimales, activa FROM legado.moneda ORDER BY codigo').fetchall()]
    foto = foto_del_catalogo(vivo)
    cat = delta.catalogo(foto, monedas_destino, monedas_vivo)
    faltas += cat['faltas']
    secuencias = {}
    for t in ORDEN_INSERTAR:
        cursor.execute(carga.IDENT_CURRENT[t])
        secuencias[t] = int(cursor.fetchone()[0])
    cursor.execute(carga.CATALOGO['folio'])
    folios_vivo = {s.strip(): int(n) for s, n, _a in cursor.fetchall()}
    posteriores = _posteriores(cursor, tope)
    i_folio, i_fecha, i_sucursal = (TABLAS['operacion'].nombres.index(c)
                                    for c in ('folio', 'fecha_operacion', 'sucursal'))
    d = {
        'corte': dict(corte), 'congelamiento': dict(tope), 'seleccion': 'id', 'identidad': identidad,
        'rangos': {t: {'desde': corte[t], 'hasta': tope[t], 'filas': len(lotes[t])} for t in ORDEN_INSERTAR},
        'lotes': lotes,
        'huellas_origen': {**{t: carga.huella_de_filas(TABLAS[t], lotes[t]) for t in ORDEN_INSERTAR},
                           'actualizadas': carga.huella_de_filas(TABLAS['orden_pago'], actualizadas_origen)},
        'actualizar': actualizar, 'actualizadas_origen': actualizadas_origen,
        'cambios': cambios, 'catalogo': {'insertar': cat['insertar'], 'actualizar': cat['actualizar']},
        'catalogo_congelamiento': foto or [], 'catalogo_posteriores': cat['posteriores'],
        'secuencias': secuencias, 'folios_vivo': folios_vivo, 'posteriores': posteriores,
        'nombres': {'operacion': {f[0]: f'{f[i_folio]} · sucursal {f[i_sucursal]} · fecha {f[i_fecha]}'
                                  for f in lotes['operacion']}},
        'faltas': faltas,
    }
    d['sha'] = delta.plan_sha(d)
    d['segundos'] = round(time.monotonic() - t0, 2)
    return d


def _posteriores(cursor, tope: dict[str, int]) -> dict:
    """Lo escrito DESPUÉS del congelamiento: queda fuera del delta y va al barrido posterior al corte."""
    cursor.execute(delta.ORDENES_POSTERIORES, {'congelamiento': tope['orden_pago']})
    ordenes = [{'id': i, 'uetr': u.strip(), 'folio': f, 'fecha_registro': str(fr), 'estatus': e}
               for i, u, f, fr, e in cursor.fetchall()]
    cursor.execute(delta.OPERACIONES_POSTERIORES, {'congelamiento': tope['operacion']})
    operaciones = [{'id': i, 'folio': f, 'sucursal': s.strip(), 'fecha_operacion': str(fo)}
                   for i, f, s, fo in cursor.fetchall()]
    otras = {}
    for t, consulta in delta.POSTERIORES.items():
        cursor.execute(consulta, {'congelamiento': tope[t]})
        otras[t] = [int(i) for (i,) in cursor.fetchall()]
    return {'orden_pago': ordenes, 'operacion': operaciones, **otras}


def resumen_del_plan(d: dict) -> dict:
    return {'sha': d['sha'], 'seleccion': d['seleccion'], 'corte': d['corte'], 'congelamiento': d['congelamiento'],
            'rangos': d['rangos'], 'cambios': delta.resumen_de_cambios(d['cambios']),
            'actualizar': {'orden_pago': len(d['actualizar'])},
            'catalogo': {'insertar': [f[0] for f in d['catalogo']['insertar']],
                         'actualizar': d['catalogo']['actualizar'], 'posteriores': d['catalogo_posteriores']},
            'secuencias_del_legado': d['secuencias'], 'folios_del_legado': d['folios_vivo'],
            'posteriores': {t: len(v) for t, v in d['posteriores'].items()}, 'faltas': d['faltas'],
            'segundos': d.get('segundos')}


# ── lecturas del destino ────────────────────────────────────────────────────────────────────────────────────────

def _huella_hasta(pg, tabla: str, corte: int, excepto: list[int]) -> tuple[int, str]:
    filas, sha = pg.execute(_q_huella_hasta(tabla), (corte, excepto)).fetchone()
    return int(filas), sha


def _anteriores(pg, d: dict) -> dict:
    """Los valores PREVIOS (los del destino ahora) de lo que el delta actualiza: van a la reversa antes de escribir."""
    nombres = TABLAS['orden_pago'].nombres
    ordenes = {f[0]: {c: f[nombres.index(c)] for c in MUTABLES['orden_pago']}
               for f in presentes(pg, 'orden_pago', sorted(d['actualizar']))}
    faltan = sorted(set(d['actualizar']) - set(ordenes))
    if faltan:
        raise Negado(f'el destino no tiene las filas que el delta actualiza: {faltan[:MUESTRA]}')
    nombres = TABLAS['moneda'].nombres
    monedas = {f[0]: {c: f[nombres.index(c)] for c in MUTABLES['moneda']}
               for f in presentes(pg, 'moneda', sorted(d['catalogo']['actualizar']))}
    return {'orden_pago': ordenes, 'moneda': monedas}


def folios_en_destino(pg) -> dict[str, int | None]:
    return {serie: pg.execute(_q_max_folio(tabla), (f'^{serie}-[0-9]+$',)).fetchone()[0]
            for serie, tabla in carga.SERIES.items()}


def duplicados(pg) -> list[dict]:
    return [{'documento': u.strip(), 'sucursal': (s or '').strip(), 'ids': list(ids)}
            for u, s, ids in pg.execute(DUPLICADOS).fetchall()]


def registro(pg) -> dict[str, int]:
    """El segundo camino del corte del destino: hasta dónde llega cada tabla según los meses aplicados y, si lo hay,
    el delta aplicado. Con el delta adentro, `MAX(id)` y el registro vuelven a coincidir (en el congelamiento)."""
    resultado = runbook.registro(pg)
    fila = pg.execute("SELECT plan -> 'rangos' FROM corte.carga_delta WHERE estado = 'aplicado'").fetchone()
    for t, r in ((fila[0] if fila else None) or {}).items():
        if r['filas']:
            resultado[t] = max(resultado.get(t, 0), r['hasta'])
    return resultado


def _aplicado(pg) -> tuple | None:
    return pg.execute("SELECT id, plan_sha, aplicada_en FROM corte.carga_delta WHERE estado = 'aplicado' "
                      'ORDER BY id DESC LIMIT 1').fetchone()


def _ultimo_ensayo(pg, sha: str) -> tuple[bool, dict] | None:
    fila = pg.execute('SELECT verde, huella_previa FROM corte.ensayo_delta WHERE plan_sha = %s '
                      'ORDER BY id DESC LIMIT 1', (sha,)).fetchone()
    return None if fila is None else (fila[0], fila[1])


def _anotar_ensayo(pg, sha: str, previa: dict, verde: bool, resultado: dict) -> None:
    pg.execute('INSERT INTO corte.ensayo_delta (plan_sha, huella_previa, verde, resultado) VALUES (%s, %s, %s, %s)',
               (sha, _jsonb(previa), verde, _jsonb(json.loads(json.dumps(resultado, default=str)))))


# ── ensayo y aplicar ────────────────────────────────────────────────────────────────────────────────────────────

def cargar_delta(pg, d: dict, *, confirmar: bool, conciliar: bool = True, sin_guarda: bool = False,
                 trabajo: Path | None = None) -> dict:
    """El corazón de `ensayo` (confirmar=False: todo en una transacción que se revierte) y de `aplicar`.
    `conciliar=False` y `sin_guarda` existen sólo para los controles negativos: no se exponen en la línea de órdenes."""
    t0 = time.monotonic()
    verbo = 'aplicar' if confirmar else 'ensayo'
    elegidos = {t: d.get('seleccion_ids', {}).get(t, [f[0] for f in d['lotes'][t]]) for t in ORDEN_INSERTAR}
    seleccion = {t: delta.comparar_seleccion(d['identidad'][t], elegidos[t], d['nombres'].get(t))
                 for t in ORDEN_INSERTAR}
    malas = {t: s for t, s in seleccion.items() if not s['coincide']}
    if malas and not sin_guarda:
        detalle = '; '.join(f"{t}: faltan {s['faltan']} {s['muestra_faltan']} y sobran {s['sobran']} "
                            f"{s['muestra_sobran']}" for t, s in sorted(malas.items()))
        raise Negado(f"el delta por {d['seleccion']} no es el rango de la identidad (corte, congelamiento]: {detalle}")
    if d['faltas'] and not sin_guarda:
        raise Negado(f"el delta no se puede derivar: {d['faltas'][:5]}")
    previa = runbook.huella_destino(pg)
    if confirmar:
        prendidos = runbook.encendidos(pg)
        if prendidos:
            raise Negado(f'hay automatismos del TO-BE encendidos: {prendidos}; se apagan antes de aplicar')
        ya = _aplicado(pg)
        if ya is not None:
            raise Negado(f'el delta ya está aplicado (registro {ya[0]}, plan {ya[1][:12]}, {ya[2]}): repetirlo '
                         'duplicaría; para volver a aplicarlo primero se revierte')
    actual, faltas = carga.corte_del_destino(runbook.maximos(pg), registro(pg))
    if faltas:
        raise Negado(f'el corte del destino no coincide por sus dos caminos: {faltas}')
    faltas = delta.guarda_del_corte(actual, d['corte'])
    if faltas and not sin_guarda:
        raise Negado(f'sólo ids > corte: {faltas}')
    if confirmar:
        ensayado = _ultimo_ensayo(pg, d['sha'])
        if ensayado is None or not ensayado[0]:
            raise Negado(f"no hay un ensayo verde del delta con este plan ({d['sha'][:12]}): un choque en el ensayo "
                         'detiene el corte')
        cambios = delta.diferencias(ensayado[1], previa)
        if cambios:
            raise Negado(f'el destino cambió desde el ensayo: {cambios[:5]}')
    anteriores = _anteriores(pg, d)
    rev = delta.reversa(d, previa, anteriores)
    excepto = sorted(d['actualizar'])
    intactas = _huella_hasta(pg, 'orden_pago', d['corte']['orden_pago'], excepto)
    t1 = time.monotonic()
    registro_id = None
    if confirmar:
        registro_id = pg.execute(
            'INSERT INTO corte.carga_delta (plan_sha, estado, plan, reversa, huella_previa) '
            "VALUES (%s, 'reversa_generada', %s, %s, %s) RETURNING id",
            (d['sha'], _jsonb(json.loads(json.dumps(resumen_del_plan(d), default=str))), _jsonb(rev),
             _jsonb(rev['huella_previa']))).fetchone()[0]
        if trabajo is not None:
            trabajo.mkdir(parents=True, exist_ok=True)
            (trabajo / 'reversa_delta.json').write_text(json.dumps(rev, ensure_ascii=False, indent=1) + '\n',
                                                        encoding='utf-8')
    resultado: dict = {'verbo': verbo, 'plan_sha': d['sha'], 'conciliar': conciliar, 'previa': previa,
                       'insertadas': {'moneda': len(d['catalogo']['insertar']),
                                      **{t: len(d['lotes'][t]) for t in ORDEN_INSERTAR}},
                       'actualizadas': {'orden_pago': len(d['actualizar']) if conciliar else 0,
                                        'moneda': len(d['catalogo']['actualizar'])}}
    try:
        with pg.transaction(force_rollback=not confirmar):
            pg.execute(_q_rol(ROL_APLICA))
            txid = pg.execute('SELECT txid_current()').fetchone()[0]
            _escribir(pg, d, conciliar, previa)
            resultado['derivados'] = delta.rearmar(pg)
            verificacion = verificar(pg, d, previa, intactas)
            resultado['verificacion'] = verificacion
            resultado['secuencias'] = secuencias(pg)
            if verificacion['faltas']:
                raise NoCuadra(verificacion['faltas'], verificacion)
            if confirmar:
                pg.execute("UPDATE corte.carga_delta SET estado = 'aplicado', carga_txid = %s, verificacion = %s, "
                           'aplicada_en = clock_timestamp() WHERE id = %s',
                           (txid, _jsonb(json.loads(json.dumps(verificacion, default=str))), registro_id))
    except Exception as error:
        _restaurar_secuencias(pg, previa['secuencias'])
        if confirmar and registro_id is not None:
            pg.execute("UPDATE corte.carga_delta SET estado = 'fallido', detalle = %s WHERE id = %s",
                       (str(error)[:2000], registro_id))
        if not confirmar:
            _anotar_ensayo(pg, d['sha'], previa, False, {**_sin_previa(resultado), 'error': str(error)[:2000]})
        raise
    resultado['segundos'] = {'guardas_y_reversa': round(t1 - t0, 2), 'escribir_y_verificar': round(
        time.monotonic() - t1, 2)}
    if not confirmar:
        _restaurar_secuencias(pg, previa['secuencias'])
        _anotar_ensayo(pg, d['sha'], previa, True, _sin_previa(resultado))
    return resultado


def _sin_previa(resultado: dict) -> dict:
    return {k: v for k, v in resultado.items() if k != 'previa'}


def _escribir(pg, d: dict, conciliar: bool, previa: dict) -> None:
    """Dentro de la transacción y con el rol del delta: el catálogo primero, los lotes en el orden de las llaves
    foráneas, los UPDATE acotados, las secuencias por encima de lo que el legado ya usó (también después del
    congelamiento) y los folios, sólo hacia arriba."""
    if d['catalogo']['insertar']:
        with pg.cursor().copy(_q('copiar', 'moneda')) as copia:
            for fila in d['catalogo']['insertar']:
                copia.write_row(fila)
    for codigo_moneda, valores in sorted(d['catalogo']['actualizar'].items()):
        pg.execute(_q_actualizar('moneda'), (*[valores[c] for c in MUTABLES['moneda']], codigo_moneda))
    for t in ORDEN_INSERTAR:
        if d['lotes'][t]:
            with pg.cursor().copy(_q('copiar', t)) as copia:
                for fila in d['lotes'][t]:
                    copia.write_row(fila)
    if conciliar:
        for k, valores in sorted(d['actualizar'].items()):
            pg.execute(_q_actualizar('orden_pago'), (*[valores[c] for c in MUTABLES['orden_pago']], k))
    for t in ORDEN_INSERTAR:
        tope = max([previa['secuencias'][t]['last_value'], d['secuencias'][t], *(f[0] for f in d['lotes'][t])])
        pg.execute('SELECT setval(%s::regclass, %s, true)', (f'legado.{TABLAS[t].secuencia}', tope))
    for serie, valor in sorted(carga.folios_del_lote(d['lotes']).items()):
        pg.execute('UPDATE legado.folio SET siguiente = GREATEST(siguiente, %s) WHERE serie = %s', (valor, serie))


def secuencias(pg) -> dict[str, int]:
    return {t: pg.execute(runbook._q_secuencia(TABLAS[t])).fetchone()[0] for t in ORDEN_INSERTAR}


def verificar(pg, d: dict, previa: dict, intactas: tuple[int, str]) -> dict:
    """Dentro de la transacción, antes de confirmar. Vacío en `faltas` = cuadra."""
    faltas: list[str] = []
    lotes = {t: carga.huella_de_filas(TABLAS[t], pg.execute(_q('filas', t), (r['desde'], r['hasta'])).fetchall())
             for t, r in d['rangos'].items()}
    faltas += [f'lote {x}' for x in carga.comparar_mes({t: d['huellas_origen'][t] for t in ORDEN_INSERTAR}, lotes)]
    ids = sorted(d['actualizar'])
    filas = presentes(pg, 'orden_pago', ids)
    if carga.huella_de_filas(TABLAS['orden_pago'], filas) != d['huellas_origen']['actualizadas']:
        origen = {f[0]: f for f in d['actualizadas_origen']}
        distintas = [f[0] for f in filas if origen.get(f[0]) != tuple(f)]
        faltas.append(f'orden_pago: {len(distintas)} de las {len(ids)} filas del corte que la bitácora cambió no '
                      f'quedan como el origen al congelamiento: {distintas[:MUESTRA]}')
    ahora = _huella_hasta(pg, 'orden_pago', d['corte']['orden_pago'], ids)
    if ahora != intactas:
        faltas.append(f'orden_pago: el resto de las filas del corte cambió ({intactas[0]} filas, huella '
                      f'{intactas[1][:12]} → {ahora[0]} filas, huella {ahora[1][:12]})')
    for t in ORDEN_INSERTAR:
        if t == 'orden_pago':
            continue
        filas_corte, maximo = pg.execute(_q('hasta_el_corte', t), (d['corte'][t],)).fetchone()
        antes = previa['tablas'][t]
        if (filas_corte, maximo) != (antes['filas'], antes['max_id']):
            faltas.append(f"{t}: con id ≤ corte había {antes['filas']} filas y ahora {filas_corte}")
        mas_alla = pg.execute(_q('mas_alla', t), (d['congelamiento'][t],)).fetchone()[0]
        if mas_alla:
            faltas.append(f"{t}: {mas_alla} filas después del congelamiento ({d['congelamiento'][t]})")
    monedas = pg.execute('SELECT codigo, numerico, nombre, decimales, activa FROM legado.moneda').fetchall()
    if carga.huella_de_filas(TABLAS['moneda'], monedas) != carga.huella_de_filas(TABLAS['moneda'],
                                                                                 d['catalogo_congelamiento']):
        faltas.append(f"moneda: el catálogo del destino no es el del congelamiento "
                      f"({sorted(tuple(m) for m in monedas)} ≠ {sorted(d['catalogo_congelamiento'])})")
    dobles = duplicados(pg)
    if dobles:
        faltas.append(f'{len(dobles)} documentos con más de un registro vigente (uetr/sucursal): '
                      f"{['/'.join((x['documento'], x['sucursal'])) + ' ' + str(x['ids']) for x in dobles[:5]]}")
    siguiente = {s: n for s, n in pg.execute('SELECT serie, siguiente FROM legado.folio')}
    posteriores = {'OP': [o['folio'] for o in d['posteriores']['orden_pago']],
                   'FX': [o['folio'] for o in d['posteriores']['operacion']]}
    choques = delta.choques_de_folio(siguiente, d['folios_vivo'], folios_en_destino(pg), posteriores)
    faltas += choques
    return {'lotes': {t: {'filas': h['filas'], 'huella': h['huella']} for t, h in lotes.items()},
            'actualizadas': len(ids), 'duplicados': len(dobles), 'muestra_duplicados': dobles[:MUESTRA],
            'folios': {'siguiente_del_destino': siguiente, 'ya_usados_por_el_legado': {
                s: n - 1 for s, n in d['folios_vivo'].items()}, 'choques': choques},
            'faltas': faltas}


# ── reversa ─────────────────────────────────────────────────────────────────────────────────────────────────────

def revertir_delta(pg, *, omitir: int | None = None) -> dict:
    """Ejecuta la reversa GUARDADA del delta aplicado y confirma sólo si el destino vuelve a la huella previa.
    `omitir` existe sólo para el control negativo (una reversa plantada que no devuelve un valor previo)."""
    t0 = time.monotonic()
    punto = runbook.no_retorno(pg)
    if punto is not None:
        raise Negado(f"punto de no retorno registrado el {punto['instante']} ({punto['motivo']}: "
                     f"{punto['referencia']}): revertir el delta borraría lo capturado; sólo hacia adelante")
    fila = pg.execute("SELECT id, reversa FROM corte.carga_delta WHERE estado = 'aplicado' ORDER BY id DESC "
                      'LIMIT 1').fetchone()
    if fila is None:
        raise Negado('no hay un delta aplicado: no hay reversa que correr')
    registro_id, rev = fila
    antes = runbook.huella_destino(pg)['secuencias']
    borradas: dict[str, int] = {}
    try:
        with pg.transaction():
            pg.execute(_q_rol(ROL_REVIERTE))
            for t in ORDEN_BORRAR:
                if t in rev['borrar']:
                    r = rev['borrar'][t]
                    borradas[t] = pg.execute(_q('borrar', t), (r['desde'], r['hasta'])).rowcount
            restauradas = 0
            for k, valores in sorted(rev['restaurar']['orden_pago'].items(), key=lambda x: int(x[0])):
                if omitir is not None and int(k) == omitir:
                    continue
                pg.execute(_q_actualizar('orden_pago'), (*[delta.valor_de('orden_pago', c, valores[c])
                                                           for c in MUTABLES['orden_pago']], int(k)))
                restauradas += 1
            if rev['catalogo']['borrar']:
                borradas['moneda'] = pg.execute('DELETE FROM legado.moneda WHERE codigo = ANY(%s::text[])',
                                                (rev['catalogo']['borrar'],)).rowcount
            for codigo_moneda, valores in sorted(rev['catalogo']['restaurar'].items()):
                pg.execute(_q_actualizar('moneda'), (*[valores[c] for c in MUTABLES['moneda']], codigo_moneda))
            for t, s in sorted(rev['secuencias'].items()):
                pg.execute('SELECT setval(%s::regclass, %s, %s)', (f'legado.{TABLAS[t].secuencia}', s['last_value'],
                                                                    s['is_called']))
            for serie, valor in sorted(rev['folios'].items()):
                pg.execute('UPDATE legado.folio SET siguiente = %s WHERE serie = %s', (valor, serie))
            derivados = delta.rearmar(pg)
            ahora = runbook.huella_destino(pg)
            faltas = delta.diferencias(rev['huella_previa'], ahora)
            if faltas:
                raise NoCuadra(faltas)
            pg.execute("UPDATE corte.carga_delta SET estado = 'revertido', revertida_en = clock_timestamp() "
                       'WHERE id = %s', (registro_id,))
    except Exception:
        _restaurar_secuencias(pg, antes)
        raise
    return {'borradas': borradas, 'restauradas': {'orden_pago': restauradas,
                                                  'moneda': len(rev['catalogo']['restaurar'])},
            'derivados': derivados, 'huella': 'igual a la previa', 'ahora': ahora,
            'segundos': round(time.monotonic() - t0, 2)}


# ── cifras de control del destino (criterio 8) ──────────────────────────────────────────────────────────────────

def documentos_del_destino(pg, tope: dict[str, int]) -> list[cifras.Documento]:
    """Los documentos tal como están en el destino, con la MISMA forma canónica del paso 2 (`corte/cifras.py`). El
    destino ya está al congelamiento: no hay estatus que reconstruir."""
    congelamiento = {f'dbo.{t}': n for t, n in tope.items()}
    monedas = frozenset(c.rstrip(' ') for (c,) in pg.execute('SELECT codigo FROM legado.moneda'))
    documentos: list[cifras.Documento] = []
    operaciones: dict[int, tuple[str, str]] = {}
    for fila in pg.execute(_q('filas', 'operacion'), (0, tope['operacion'])):
        op = Operacion(*fila)
        operaciones[op.id] = (op.folio, op.sucursal.rstrip(' '))
        documentos.append(cifras.documento_de_operacion(op, congelamiento['dbo.operacion'], monedas))
    registros = [Registro(*f) for f in pg.execute(_q('filas', 'orden_pago'), (0, tope['orden_pago']))]
    vigentes = {r.id for r in registros if r.estatus != cifras.REEMPLAZADA}
    ctx = Contexto(operaciones, monedas, congelamiento)
    for fila in pg.execute(_q('filas', 'partida_liquidada'), (0, tope['partida_liquidada'])):
        p = Partida(*fila)
        if p.orden_id in vigentes:
            ctx.partidas_cliente.setdefault(p.orden_id, []).append(p)
    for fila in pg.execute(_q('filas', 'partida_solicitada'), (0, tope['partida_solicitada'])):
        p = Partida(*fila)
        ctx.partidas_corresponsal.setdefault(p.orden_id, []).append(p)
    return [*documentos, *cifras.documentos_de_orden(registros, ctx)]


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def cifras_del_destino(pg, tope: dict[str, int], paso_2: Path = CIFRAS_PASO_2, huella: Path = HUELLA_PASO_2) -> dict:
    """Cifras de control del destino contra las VERSIONADAS del paso 2 (su sha256 es el de `huella.json`): por tipo y
    por grupo tipo + estado + mes, lo del destino = lo cargado del paso 2 y destino + no viaja = origen."""
    t0 = time.monotonic()
    documentos = documentos_del_destino(pg, tope)
    t1 = time.monotonic()
    agregadas = cifras.agregar(documentos)
    sha = _sha256(paso_2)
    firmado = json.loads(huella.read_text(encoding='utf-8'))['archivos']['cifras-de-control.json']
    comparacion = delta.contra_el_paso_2(agregadas, json.loads(paso_2.read_text(encoding='utf-8'))['cifras'])
    dobles = cifras.duplicados_por_documento(documentos)
    no_cargados = [{'documento': '/'.join(x.llave), 'destino': x.destino, 'motivo': x.motivo}
                   for x in documentos if x.destino != cifras.CARGADO]
    faltas = list(comparacion['faltas'])
    if sha != firmado:
        faltas.insert(0, f'las cifras del paso 2 ({sha[:16]}…) no son las versionadas en huella.json ({firmado[:16]}…)')
    if dobles:
        faltas.append(f'duplicados por documento en el destino: {len(dobles)} ({dobles[:10]})')
    return {'paso_2': {'archivo': paso_2.name, 'sha256': sha, 'firmado': sha == firmado},
            'documentos_en_destino': len(documentos), 'por_tipo': comparacion['tipos'],
            'grupos_comparados': comparacion['grupos_comparados'], 'grupos_distintos': comparacion['grupos_distintos'],
            'duplicados_por_documento': dobles[:MUESTRA], 'no_clasifican_como_cargados': no_cargados[:MUESTRA],
            'faltas': faltas, 'cuadra': not faltas,
            'segundos': {'leer': round(t1 - t0, 1), 'comparar': round(time.monotonic() - t1, 1)}}


# ── evidencia: conciliación, altas fechadas hacia atrás y lo posterior ──────────────────────────────────────────

def conciliacion(pg, d: dict) -> dict:
    """Los re-registros del día de documentos del corte: el registro viejo SALE (REEMPLAZADA) y el vigente es el que
    entró en el delta, con el MISMO documento; 0 duplicados por documento."""
    reemplazadas = sorted(k for k, c in d['cambios']['al_corte'].items() if c[-1].nuevo == cifras.REEMPLAZADA)
    salen = pg.execute(SALEN, (d['corte']['orden_pago'], reemplazadas)).fetchall() if reemplazadas else []
    dobles = duplicados(pg)
    return {'re_registros_de_documentos_del_corte': len(reemplazadas), 'salen': len(salen),
            'muestra_salen': [{'viejo': v, 'nuevo': n} for v, n in salen[:MUESTRA]],
            'ids_que_salen': reemplazadas, 'duplicados_por_documento': len(dobles),
            'concilia': len(salen) == len(reemplazadas) and not dobles}


def presentes(pg, tabla: str, llaves: list) -> list[tuple]:
    """Las filas del destino con esas llaves (sin consulta si la lista está vacía)."""
    if not llaves:
        return []
    return [tuple(f) for f in pg.execute(_q_por_ids(tabla), (sorted(llaves),)).fetchall()]


def estado(pg) -> dict:
    filas = pg.execute('SELECT id, plan_sha, estado, generada_en, aplicada_en, revertida_en, detalle '
                       'FROM corte.carga_delta ORDER BY id').fetchall()
    return {'deltas': [{'id': i, 'plan_sha': s, 'estado': e, 'generada_en': str(g), 'aplicada_en': str(a),
                        'revertida_en': str(r), 'detalle': x} for i, s, e, g, a, r, x in filas],
            'no_retorno': runbook.no_retorno(pg), 'interruptores_encendidos': runbook.encendidos(pg),
            'huella': runbook.huella_destino(pg)}


# ── línea de órdenes ────────────────────────────────────────────────────────────────────────────────────────────

def ultimo(directorio: Path, patron: str) -> Path:
    candidatos = sorted(directorio.glob(patron))
    if not candidatos:
        raise SystemExit(f'falta {directorio}/{patron}: corre antes ./ciclo.sh')
    return candidatos[-1]


def contexto(manifiesto: Path | None, datos: Path = DATOS) -> tuple[dict, dict, dict]:
    """El corte (manifiesto = paso 2), el congelamiento (foto del vivo = paso 2) y la foto del vivo."""
    corte = runbook.cortes(manifiesto)
    vivo = json.loads(ultimo(datos, 'vivo_*.json').read_text(encoding='utf-8'))
    tope, faltas = delta.congelamiento(json.loads(runbook.CORTE_MEDIDO.read_text(encoding='utf-8')), vivo)
    if faltas:
        raise Negado(f'el congelamiento no es el medido en el paso 2: {faltas}')
    return corte, tope, vivo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.runbook_delta', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('verbo', choices=('preparar', 'ensayo', 'aplicar', 'reversa', 'cifras', 'estado'))
    parser.add_argument('--manifiesto', type=Path, default=None)
    parser.add_argument('--origen-base', default=os.environ.get('DECANT_DELTA_ORIGEN', ORIGEN_VIVO))
    parser.add_argument('--destino-base', default=os.environ.get('DECANT_CORTE_DESTINO', runbook.DESTINO_BASE))
    parser.add_argument('--trabajo', type=Path, default=TRABAJO)
    args = parser.parse_args(argv)
    try:
        with runbook.conectar_destino(args.destino_base) as pg:
            if args.verbo == 'preparar':
                salida = preparar(pg)
            elif args.verbo == 'estado':
                salida = estado(pg)
            elif args.verbo == 'reversa':
                salida = {k: v for k, v in revertir_delta(pg).items() if k != 'ahora'}
            else:
                corte, tope, vivo = contexto(args.manifiesto or runbook._ultimo_manifiesto())
                if args.verbo == 'cifras':
                    salida = cifras_del_destino(pg, tope)
                else:
                    with runbook.conectar_origen(args.origen_base) as ms:
                        d = leer_delta(pg, ms, corte, tope, vivo)
                    salida = _sin_previa(cargar_delta(pg, d, confirmar=args.verbo == 'aplicar', trabajo=args.trabajo))
        print(json.dumps(salida, ensure_ascii=False, indent=1, default=str))
        return 0
    except (Negado, NoCuadra) as error:
        print(f'{args.verbo}: {type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
