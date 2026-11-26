"""La paridad de ESTADO de los que escriben y el ORÁCULO del corte para los que leen, en el CI (S3 paso 5; ADR 0014 y
0015; criterios 2 y 9 del plan).

    python -m corte.estado_ci --base corte/base --salida corte/estado-ci                     # restaura el volcado
    python -m corte.estado_ci --base corte/base --construir-base --salida corte/estado-ci    # sin volcado

Necesita `DECANT_ORACULO=1 ./ciclo.sh` (el oráculo se captura en el congelamiento del legado vivo), el legado arriba
(DECANT_SA_PASSWORD, DECANT_PUERTO) y PostgreSQL (DECANT_PG_PASSWORD, DECANT_PG_PUERTO). Pasos:
1. El respaldo de ESTA corrida como `BFN_DIVISAS_CORTE` (el estado inicial del legado).
2. La base de referencia: la base cerrada (volcado `destino-cerrado` de la nocturna, restaurado y verificado sin
   creerle, o construida) es el estado inicial del TO-BE; una copia suya recibe el delta del paso 4 y queda en el
   estado del congelamiento, contra el que el TO-BE re-corre el oráculo.
3. La copia temporal del legado en el esquema `estado` del respaldo: tablas con sus datos, índices y llaves, el
   disparador y los escritores con el reloj inyectado. Se verifica: catálogo igual al original, 0 diferencias de
   datos, el mismo código que el repositorio y ninguna dependencia de `dbo`.
4. Los escenarios (`corte/estado.py`) en el legado y en el TO-BE, cada uno en una transacción REVERTIDA, con la guarda
   de `@@TRANCOUNT` en cada llamada; el efecto de cada etapa por llave de negocio, arbitrado; el N de N con lo que dice
   el servidor (`sys.dm_exec_*_stats`).
5. Controles negativos (tienen que FALLAR donde se dice): un procedimiento con su propio ROLLBACK dispara la guarda (y
   sin ella el volcado saldría vacío); sin un escritor en la corrida, el N de N falla nombrándolo; cada trampa, sin
   ella (el parche del TO-BE aplicado a la copia) pasa y con ella falla nombrándola.
6. El oráculo: cada caso capturado en el congelamiento contra el TO-BE con el reloj inyectado, con su reloj propio y,
   donde los motores calculan distinto, con el SQL copiado tal cual.
Deja `estado.json` y, con `--resumen`, el resumen del job. Sale con 1 si algo no cuadra o un control no falla.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from corte import base, carga_ci, codigo, delta_ci, estado, oraculo, runbook, runbook_delta, trampas
from corte.carga import CON_IDENTIDAD, TABLAS
from corte.estado import ESQUEMA, ORDEN_TABLAS, Efecto, NoSeCopia, Refs
from corte.runbook import Negado, NoCuadra
from corte.runbook_delta import DATOS
from corte.sql import leer_scripts
from radiografia.veredictos import revertida

CDMX = ZoneInfo('America/Mexico_City')
DDL_TOBE = Path(__file__).with_name('estado_tobe.sql')
TABLAS_SQL = codigo.SQL / '02_tablas.sql'
MUESTRA = estado.MUESTRA
_MAXIMOS = ', '.join(f'(SELECT MAX(id) FROM {ESQUEMA}.{t.nombre})' for t in CON_IDENTIDAD)


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


def _lista(ids) -> str:
    return ','.join(str(int(i)) for i in sorted(ids))


# ── 3. la copia temporal del legado ─────────────────────────────────────────────────────────────────────────────

CATALOGO_COLUMNAS = """SELECT t.name, c.column_id, c.name, TYPE_NAME(c.user_type_id), c.max_length, c.precision,
       c.scale, c.is_nullable, c.is_identity, c.collation_name
FROM sys.columns c JOIN sys.tables t ON t.object_id = c.object_id
WHERE SCHEMA_NAME(t.schema_id) = %s ORDER BY t.name, c.column_id"""
CATALOGO_INDICES = """SELECT t.name, i.name, i.type_desc, i.is_unique, i.is_primary_key, ic.key_ordinal,
       COL_NAME(ic.object_id, ic.column_id), ic.is_descending_key
FROM sys.indexes i JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
WHERE SCHEMA_NAME(t.schema_id) = %s ORDER BY t.name, i.name, ic.key_ordinal, ic.column_id"""
CATALOGO_LLAVES = """SELECT OBJECT_NAME(fk.parent_object_id), fk.name, OBJECT_SCHEMA_NAME(fk.referenced_object_id),
       OBJECT_NAME(fk.referenced_object_id)
FROM sys.foreign_keys fk WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = %s ORDER BY 1, 2"""
DEPENDENCIAS = """SELECT OBJECT_NAME(d.referencing_id), d.referenced_database_name, d.referenced_schema_name,
       d.referenced_entity_name
FROM sys.sql_expression_dependencies d WHERE OBJECT_SCHEMA_NAME(d.referencing_id) = N'estado'"""
DISPARADORES = """SELECT tr.name, OBJECT_SCHEMA_NAME(tr.parent_id), OBJECT_NAME(tr.parent_id)
FROM sys.triggers tr WHERE OBJECT_SCHEMA_NAME(tr.object_id) = N'estado'"""
DEFINICION = 'SELECT OBJECT_DEFINITION(OBJECT_ID(%s))'
PASO_DEL_JOB = """SELECT s.command, s.subsystem, s.database_name FROM msdb.dbo.sysjobsteps s
JOIN msdb.dbo.sysjobs j ON j.job_id = s.job_id WHERE j.name = %s AND s.step_name = %s"""
ESTADISTICAS = """SELECT OBJECT_NAME(object_id, database_id), SUM(execution_count) FROM sys.dm_exec_procedure_stats
WHERE database_id = DB_ID() AND OBJECT_SCHEMA_NAME(object_id, database_id) = N'estado'
GROUP BY OBJECT_NAME(object_id, database_id)
UNION ALL
SELECT OBJECT_NAME(object_id, database_id), SUM(execution_count) FROM sys.dm_exec_trigger_stats
WHERE database_id = DB_ID() AND OBJECT_SCHEMA_NAME(object_id, database_id) = N'estado'
GROUP BY OBJECT_NAME(object_id, database_id)"""
HUELLA_ORIGINALES = {t.nombre: f'SELECT COUNT_BIG(*), CHECKSUM_AGG(BINARY_CHECKSUM(*)) FROM dbo.{t.nombre}'
                     for t in TABLAS.values()}
MODULOS_ORIGINALES = """SELECT o.name, HASHBYTES('SHA2_256', m.definition) FROM sys.sql_modules m
JOIN sys.objects o ON o.object_id = m.object_id WHERE SCHEMA_NAME(o.schema_id) = N'dbo' ORDER BY o.name"""
BORRAR_ESQUEMA = """DECLARE @sql nvarchar(max) = N'';
SELECT @sql += N'DROP TRIGGER estado.' + QUOTENAME(name) + N'; ' FROM sys.triggers
WHERE OBJECT_SCHEMA_NAME(object_id) = N'estado';
SELECT @sql += N'DROP PROCEDURE estado.' + QUOTENAME(name) + N'; ' FROM sys.procedures
WHERE SCHEMA_NAME(schema_id) = N'estado';
SELECT @sql += N'ALTER TABLE estado.' + QUOTENAME(OBJECT_NAME(parent_object_id)) + N' DROP CONSTRAINT '
             + QUOTENAME(name) + N'; ' FROM sys.foreign_keys WHERE OBJECT_SCHEMA_NAME(parent_object_id) = N'estado';
SELECT @sql += N'DROP TABLE estado.' + QUOTENAME(name) + N'; ' FROM sys.tables WHERE SCHEMA_NAME(schema_id) = N'estado';
EXEC sp_executesql @sql;
IF SCHEMA_ID(N'estado') IS NOT NULL DROP SCHEMA estado;"""
CONTROL_ROLLBACK = """CREATE PROCEDURE estado.sp_control_con_rollback AS
BEGIN
    SET NOCOUNT ON;
    UPDATE estado.folio SET siguiente = siguiente + 1 WHERE serie = 'FX';
    ROLLBACK TRANSACTION;
END"""


def normal_de_modulo(texto: str) -> str:
    """SQL Server guarda `CREATE OR ALTER` como `CREATE   ` (cambia «OR ALTER» por espacios): se comparan sin eso."""
    return re.sub(r'\bCREATE\s+(?:OR\s+ALTER\s+)?', 'CREATE ', texto.strip(), count=1)


def huella_de_originales(cursor) -> str:
    """Una huella barata de lo ORIGINAL (las 7 tablas y los módulos de dbo): la corrida no lo puede cambiar."""
    partes = []
    for t, consulta in sorted(HUELLA_ORIGINALES.items()):
        cursor.execute(consulta)
        partes.append(f'{t}:{cursor.fetchone()}')
    cursor.execute(MODULOS_ORIGINALES)
    partes += [f'{n}:{bytes(h).hex()}' for n, h in cursor.fetchall()]
    return hashlib.sha256('\n'.join(partes).encode('utf-8')).hexdigest()


def _catalogo(cursor, esquema: str) -> dict:
    resultado = {}
    for nombre, consulta in (('columnas', CATALOGO_COLUMNAS), ('indices', CATALOGO_INDICES),
                             ('llaves', CATALOGO_LLAVES)):
        cursor.execute(consulta, (esquema,))
        resultado[nombre] = [tuple(f) for f in cursor.fetchall() if f[0] in TABLAS]
    return resultado


def _ident(cursor, esquema: str) -> dict[str, int]:
    cursor.execute(estado.IDENT_MS[esquema])
    return {t.nombre: int(v) for t, v in zip(CON_IDENTIDAD, cursor.fetchone())}


def preparar_copia(ms, objetos: list[dict], escritores: list[str], efectos: dict) -> dict:
    """La copia temporal en `estado`: DDL del código (02_tablas.sql), datos del respaldo, el disparador y los escritores
    (definición del RESPALDO, que tiene que ser la del repositorio), cada uno transformado por `estado.copiar`."""
    from legado.conexion import lotes
    t0 = time.monotonic()
    cursor = ms.cursor()
    negados = sorted(e for e, d in efectos.items() if d['se_niega'])
    if negados:
        raise NoSeCopia(f'escritores con efectos fuera de la base que no se pueden neutralizar: {negados}')
    cursor.execute("SELECT SCHEMA_ID(N'estado')")
    if cursor.fetchone()[0] is not None:
        raise NoSeCopia('el respaldo ya trae un esquema `estado`: no es el respaldo limpio de esta corrida')
    originales = huella_de_originales(cursor)
    cursor.execute('CREATE SCHEMA estado')
    tablas = {f'dbo.{t}' for t in TABLAS}
    for ddl in estado.ddl_tablas(lotes(TABLAS_SQL.read_text(encoding='utf-8')), tablas):
        cursor.execute(ddl)
    cursor.execute(estado.EFECTO_EMULADO)
    for t in ORDEN_TABLAS:
        cursor.execute(estado.copiar_datos(TABLAS[t]))
    # la identidad de la copia sigue donde está la del original (un hueco al final la separaría de MAX(id))
    original, copia = _ident(cursor, 'dbo'), _ident(cursor, ESQUEMA)
    for t, n in original.items():
        if copia[t] != n:
            cursor.execute(estado.RESEMBRAR_MS[t], (n,))
    identidades = _ident(cursor, ESQUEMA)
    catalogo = {'dbo': _catalogo(cursor, 'dbo'), ESQUEMA: _catalogo(cursor, ESQUEMA)}
    faltas = []
    for parte in ('columnas', 'indices'):
        if catalogo['dbo'][parte] != catalogo[ESQUEMA][parte]:
            faltas.append(f'la copia no tiene el mismo catálogo que el original ({parte})')
    llaves_o = [(p, n, r) for p, n, _s, r in catalogo['dbo']['llaves']]
    llaves_c = [(p, n, r) for p, n, s, r in catalogo[ESQUEMA]['llaves'] if s == ESQUEMA]
    if llaves_o != llaves_c:
        faltas.append(f'llaves foráneas de la copia: {llaves_c} ≠ {llaves_o}')
    datos = volcar_legado(cursor)
    distintas = {t: len(e.despues) + len(e.borradas) for t, e in datos.items() if e.despues or e.borradas}
    if distintas:
        faltas.append(f'los datos de la copia no son los del respaldo: {distintas}')
    # los módulos: el código del respaldo, comparado con el del repositorio, y su copia
    conocidos = tablas | {e for e in escritores if '/paso:' not in e}
    del_codigo = {m.id: normal_de_modulo(m.texto) for m in leer_scripts(sorted(codigo.SQL.glob('*.sql')), codigo.RAIZ,
                                                               codigo.PRINCIPAL).modulos}
    modulos = {}
    for e in escritores:
        o = estado.unidad(objetos, e)
        if o['tipo'] not in ('procedimiento', 'trigger'):
            continue
        if o['sql_dinamico']:
            raise NoSeCopia(f'{e}: SQL dinámico en un escritor; la copia no puede reescribir sus nombres')
        cursor.execute(DEFINICION, (e,))
        texto = (cursor.fetchone()[0] or '').strip()
        c = estado.copiar(texto, conocidos)
        for emulado, parametros in c.emulados.items():
            cursor.execute(estado.emulador(ESQUEMA, emulado, parametros, e))
        cursor.execute(c.texto)
        cursor.execute(DEFINICION, (f'{ESQUEMA}.{e.split(".")[1]}',))
        guardado = (cursor.fetchone()[0] or '').strip()
        modulos[e] = {'igual_al_repositorio': normal_de_modulo(texto) == del_codigo.get(e), 'cambios': dict(c.cuenta),
                      'efectos_emulados': sorted(c.emulados), 'copia_igual_a_la_transformacion': guardado == c.texto,
                      'sha256_original': hashlib.sha256(texto.encode('utf-8')).hexdigest()}
        if not modulos[e]['igual_al_repositorio']:
            faltas.append(f'{e}: el respaldo no trae el mismo código que el repositorio')
        if not modulos[e]['copia_igual_a_la_transformacion']:
            faltas.append(f'{e}: la copia guardada no es la transformación del original')
    # los controles de las trampas: la copia con el parche del TO-BE, con otro nombre
    for e, (viejo, nuevo, _que) in estado.PARCHES.items():
        cursor.execute(DEFINICION, (e,))
        c = estado.copiar((cursor.fetchone()[0] or '').strip(), conocidos, parche=(viejo, nuevo))
        cursor.execute(re.sub(rf'(CREATE\s+PROCEDURE\s+{ESQUEMA}\.)(\w+)', r'\1\2_con_parche', c.texto, count=1))
    for sufijo, (e, viejo, nuevo, _que) in estado.VARIANTES_DE_PLAN.items():
        cursor.execute(DEFINICION, (e,))
        c = estado.copiar((cursor.fetchone()[0] or '').strip(), conocidos, parche=(viejo, nuevo))
        cursor.execute(re.sub(rf'(CREATE\s+PROCEDURE\s+{ESQUEMA}\.)(\w+)', rf'\1\2_{sufijo}', c.texto, count=1))
    cursor.execute(CONTROL_ROLLBACK)
    # el paso del job: su comando, de msdb (y el del código)
    job, paso = estado.JOB.removeprefix('job:').split('/paso:')
    cursor.execute(PASO_DEL_JOB, (job, paso))
    comando, subsistema, base_paso = cursor.fetchone()
    del_inventario = estado.unidad(objetos, estado.JOB)
    if comando.strip() != del_inventario['comando'].strip():
        faltas.append(f"el paso del job en msdb ({comando!r}) no es el del código ({del_inventario['comando']!r})")
    copia_paso = estado.copiar(comando, conocidos)
    # nadie de la copia puede depender del original
    cursor.execute(DEPENDENCIAS)
    nombres = {x.split('.')[1] for x in conocidos}
    malas = [list(f) for f in cursor.fetchall() if f[3] in nombres and (f[1] is not None or f[2] != ESQUEMA)]
    if malas:
        faltas.append(f'la copia depende de objetos fuera de `estado`: {malas[:MUESTRA]}')
    cursor.execute(DISPARADORES)
    disparadores = [list(f) for f in cursor.fetchall()]
    if any(f[1] != ESQUEMA for f in disparadores):
        faltas.append(f'un disparador de la copia vive en otra tabla: {disparadores}')
    if faltas:
        raise NoCuadra(faltas)
    return {'esquema': ESQUEMA, 'tablas': len(TABLAS), 'identidades': identidades, 'modulos': modulos,
            'paso_del_job': {'comando': comando, 'subsistema': subsistema, 'base': base_paso,
                             'copia': copia_paso.texto, 'inventario': del_inventario['fuente']},
            'datos': '0 diferencias con el respaldo en las 7 tablas', 'dependencias': 'ninguna fuera de `estado`',
            'disparadores': disparadores, 'originales': originales, 'segundos': round(time.monotonic() - t0, 1)}


# ── 4. el lado del legado ───────────────────────────────────────────────────────────────────────────────────────

def volcar_legado(cursor) -> dict[str, Efecto]:
    """El efecto acumulado: la copia contra el original, tabla por tabla (las dos diferencias de conjuntos)."""
    resultado = {}
    for t in ORDEN_TABLAS:
        cursor.execute(estado.DESPUES_MS[t])
        despues = cursor.fetchall()
        cursor.execute(estado.ANTES_MS[t])
        resultado[t] = estado.efecto_de(TABLAS[t], despues, cursor.fetchall())
    return resultado


def _ids_referidos(efecto: dict[str, Efecto]) -> tuple[set, set]:
    ordenes, operaciones = set(), set()
    i_op = TABLAS['orden_pago'].nombres.index('operacion_id')
    for k, fila in efecto['orden_pago'].despues.items():
        ordenes.add(k)
        operaciones.add(fila[i_op])
    ordenes |= efecto['orden_pago'].borradas
    for t in ('partida_solicitada', 'partida_liquidada'):
        ordenes |= {f[1] for f in efecto[t].despues.values()}
    ordenes |= {f[2] for f in efecto['bitacora'].despues.values() if f[1] == 'orden_pago'}
    return ordenes, operaciones


def refs_legado(cursor, ordenes: set, operaciones: set) -> Refs:
    refs = Refs()
    if ordenes:
        lista = _lista(ordenes)
        cursor.execute(estado.ORDENES_MS, (lista, lista))
        refs.orden = {int(i): (u, int(n)) for i, u, n in cursor.fetchall()}
    if operaciones:
        cursor.execute(estado.OPERACIONES_MS, (_lista(operaciones),))
        refs.operacion = {int(i): (f, s) for i, f, s in cursor.fetchall()}
    return refs


def _maximos(cursor) -> tuple:
    cursor.execute(estado.MAXIMOS_MS)
    return tuple(cursor.fetchone())


_RELOJ = 'EXEC sp_set_session_context @key = N\'decant.reloj\', @value = %(reloj)s;'
_FIN = f'SELECT @t0, @@TRANCOUNT, @id, {_MAXIMOS};'
LLAMADAS_MS = {
    'alta_moneda': (f"SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} "
                    f'INSERT INTO {ESQUEMA}.moneda (codigo, numerico, nombre, decimales, activa) '
                    f'VALUES (%(codigo)s, %(numerico)s, %(nombre)s, %(decimales)s, 1); {_FIN}'),
    'baja_moneda': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
                    f'UPDATE {ESQUEMA}.moneda SET activa = 0 WHERE codigo = %(codigo)s; {_FIN}'),
    'operacion': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
                  f'EXEC {ESQUEMA}.sp_registrar_operacion @fecha_operacion = %(fecha_operacion)s, '
                  '@sucursal = %(sucursal)s, @canal = %(canal)s, @cliente = %(cliente)s, '
                  '@cuenta_clabe = %(cuenta_clabe)s, '
                  '@tipo = %(tipo)s, @moneda = %(moneda)s, @monto_divisa = %(monto_divisa)s, '
                  '@tipo_cambio_referencia = %(tipo_cambio_referencia)s, @tipo_cambio = %(tipo_cambio)s, '
                  f'@id = @id OUTPUT; {_FIN}'),
    'orden': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
              f'EXEC {ESQUEMA}.sp_registrar_orden @operacion_id = %(operacion_id)s, @uetr = %(uetr)s, '
              '@referencia_mt103 = %(referencia_mt103)s, @fecha_registro = %(fecha_registro)s, '
              '@fecha_envio = %(fecha_envio)s, @fecha_valor = %(fecha_valor)s, '
              '@bic_corresponsal = %(bic_corresponsal)s, '
              '@bic_intermediario = %(bic_intermediario)s, @beneficiario = %(beneficiario)s, '
              '@cuenta_beneficiario = %(cuenta_beneficiario)s, @moneda = %(moneda)s, @monto = %(monto)s, '
              f'@gastos = %(gastos)s, @codigo_proposito = %(codigo_proposito)s, @id = @id OUTPUT; {_FIN}'),
    'liquidacion': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
                    f'EXEC {ESQUEMA}.sp_registrar_liquidacion @uetr = %(uetr)s, @referencia = %(referencia)s, '
                    f'@fecha_hora = %(fecha_hora)s, @abono = %(abono)s, @comision = %(comision)s; {_FIN}'),
    'reflejar': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
                 f'EXEC {ESQUEMA}.sp_reflejar_estatus_operacion{{sufijo}}; {_FIN}'),
    'alta_manual': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
                    f'EXEC {ESQUEMA}.sp_alta_manual_orden{{sufijo}} @operacion_id = %(operacion_id)s, '
                    '@uetr = %(uetr)s, '
                    '@referencia_mt103 = %(referencia_mt103)s, @fecha_envio = %(fecha_envio)s, '
                    '@fecha_valor = %(fecha_valor)s, @bic_corresponsal = %(bic_corresponsal)s, '
                    '@beneficiario = %(beneficiario)s, @cuenta_beneficiario = %(cuenta_beneficiario)s, '
                    f'@moneda = %(moneda)s, @monto = %(monto)s, @gastos = %(gastos)s, @id = @id OUTPUT; {_FIN}'),
    'control': (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} '
                f'EXEC {ESQUEMA}.sp_control_con_rollback; {_FIN}'),
}
for _accion in ('reflejar', 'alta_manual'):
    LLAMADAS_MS[f'{_accion}_con_parche'] = LLAMADAS_MS[_accion].replace('{sufijo}', '_con_parche')
    LLAMADAS_MS[_accion] = LLAMADAS_MS[_accion].replace('{sufijo}', '')


def llamar_legado(cursor, accion: str, args: dict, reloj: datetime, comando: str | None = None) -> dict:
    """Una llamada con la guarda: @@TRANCOUNT antes y después (también si el servidor la rechazó)."""
    import pymssql
    consulta = (f'SET NOCOUNT ON; DECLARE @t0 int = @@TRANCOUNT, @id int; {_RELOJ} {comando} {_FIN}'
                if comando else LLAMADAS_MS[accion])
    error = None
    try:
        cursor.execute(consulta, {**args, 'reloj': reloj.isoformat()})
        fila = cursor.fetchone()
    except pymssql.Error as e:
        error, fila = str(e)[:500], None
    if fila is None:
        cursor.execute('SELECT 1, @@TRANCOUNT')       # la transacción externa ya pudo haberse ido
        antes, despues = 1, cursor.fetchone()[1]
        return {'antes': antes, 'despues': despues, 'devuelto': None, 'maximos': None, 'error': error}
    return {'antes': fila[0], 'despues': fila[1], 'devuelto': fila[2], 'maximos': tuple(fila[3:]), 'error': error}


def _args_orden(a: dict, ids_operacion: dict) -> dict:
    operacion = a['operacion_id']
    return {**a, 'operacion_id': ids_operacion[operacion] if isinstance(operacion, str) else operacion}


def _entradas(guion: dict, objetos: list[dict]) -> dict[str, list[dict]]:
    """Las llamadas de cada etapa: el guion del día, la noche del corte, la mesa y la contingencia."""
    e = estado.llamadas(guion)
    noche = estado.noche_del_corte(guion, objetos)
    manual = estado.alta_manual(guion)
    orden = manual['orden']
    e['A4'] = [{'accion': 'job', 'args': {}, 'reloj': noche}]
    e['B1'] = [{'accion': 'reflejar', 'args': {}, 'reloj': noche}]
    e['C0'] = [manual['operacion']] if manual['operacion'] else []
    e['C1'] = [{'accion': 'alta_manual', 'reloj': orden['reloj'], 'ref': orden.get('ref'),
                'args': {k: orden['args'][k] for k in (
                    'operacion_id', 'uetr', 'referencia_mt103', 'fecha_envio', 'fecha_valor', 'bic_corresponsal',
                    'beneficiario', 'cuenta_beneficiario', 'moneda', 'monto', 'gastos')}}]
    return e


def correr_legado(ms, escenario: estado.Escenario, entradas: dict, comando_job: str, sufijo: str = '') -> dict:
    """Un escenario en la copia, dentro de UNA transacción revertida: cada etapa con sus llamadas (cada una con la
    guarda) y el efecto acumulado al terminarla. Después se regresan las identidades (no son transaccionales)."""
    t0 = time.monotonic()
    cursor = ms.cursor()
    identidades = _ident(cursor, ESQUEMA)
    resultado = {'etapas': {}, 'llamadas': [], 'faltas': [], 'guarda': None}
    ids_operacion: dict[str, int] = {}
    try:
        with revertida(cursor):
            maximos = _maximos(cursor)
            for etapa in escenario.etapas:
                for n, llamada in enumerate(entradas[etapa.id], 1):
                    accion = llamada['accion'] + (sufijo if llamada['accion'] in ('reflejar', 'alta_manual') else '')
                    args = (_args_orden(llamada['args'], ids_operacion) if accion in ('orden', 'alta_manual',
                                                                                       'alta_manual_con_parche')
                            else llamada['args'])
                    r = llamar_legado(cursor, accion, args, llamada['reloj'],
                                      comando=comando_job if accion == 'job' else None)
                    guarda = estado.guarda_trancount(etapa.escritor or 'DML del guion', r['antes'], r['despues'])
                    registro = {'etapa': etapa.id, 'escritor': etapa.escritor, 'n': n, 'accion': accion,
                                'devuelto': r['devuelto'], 'error': r['error'],
                                'insertadas': estado.inserciones(maximos, r['maximos']) if r['maximos'] else {}}
                    if guarda or r['error']:
                        resultado['guarda'] = guarda
                        resultado['faltas'].append(guarda or f"{etapa.id} llamada {n} ({accion}): {r['error']}")
                        resultado['llamadas'].append(registro)
                        resultado['etapas'][etapa.id] = _etapa_legado(cursor)
                        return resultado
                    if accion == 'operacion' and llamada.get('ref'):
                        ids_operacion[llamada['ref']] = r['devuelto']
                    maximos = r['maximos']
                    if accion in ('operacion', 'orden') or accion.startswith('alta_manual'):
                        resultado['llamadas'].append(registro)
                resultado['etapas'][etapa.id] = _etapa_legado(cursor)
    finally:
        cursor.execute("SELECT @@TRANCOUNT")
        resultado['trancount_al_salir'] = cursor.fetchone()[0]
        for t, n in identidades.items():
            cursor.execute(estado.RESEMBRAR_MS[t], (n,))
        resultado['segundos'] = round(time.monotonic() - t0, 1)
    return resultado


def _etapa_legado(cursor) -> dict:
    efecto = volcar_legado(cursor)
    ordenes, operaciones = _ids_referidos(efecto)
    cursor.execute('SELECT efecto, COUNT(*) FROM estado.efecto_emulado GROUP BY efecto')
    return {'efecto': efecto, 'refs': refs_legado(cursor, ordenes, operaciones),
            'efectos_emulados': {e: n for e, n in cursor.fetchall()}}


def estadisticas(cursor) -> dict[str, int]:
    cursor.execute(ESTADISTICAS)
    return {f'dbo.{n}': int(c) for n, c in cursor.fetchall()}


# ── 4. el lado del TO-BE (PostgreSQL, la base cerrada) ──────────────────────────────────────────────────────────

def _q_foto(t):
    from psycopg import sql
    return sql.SQL('CREATE TABLE {foto} AS SELECT t.{llave} AS k, md5(t::text) AS h FROM {tabla} AS t; '
                   'CREATE UNIQUE INDEX ON {foto} (k); ANALYZE {foto}').format(
        foto=sql.Identifier('paridad_estado', t.nombre), llave=sql.Identifier(t.nombres[0]),
        tabla=sql.Identifier('legado', t.nombre))


def _q_despues(t):
    from psycopg import sql
    return sql.SQL('SELECT {columnas} FROM {tabla} AS t LEFT JOIN {foto} AS a ON a.k = t.{llave} '
                   'WHERE a.k IS NULL OR a.h <> md5(t::text)').format(
        columnas=sql.SQL(', ').join(sql.Identifier('t', c) for c in t.nombres),
        tabla=sql.Identifier('legado', t.nombre), foto=sql.Identifier('paridad_estado', t.nombre),
        llave=sql.Identifier(t.nombres[0]))


def _q_borradas(t):
    from psycopg import sql
    return sql.SQL('SELECT a.k FROM {foto} AS a LEFT JOIN {tabla} AS t ON t.{llave} = a.k '
                   'WHERE t.{llave} IS NULL').format(
        foto=sql.Identifier('paridad_estado', t.nombre), tabla=sql.Identifier('legado', t.nombre),
        llave=sql.Identifier(t.nombres[0]))


ORDENES_PG = ('SELECT o.id, o.uetr, o.n FROM (SELECT id, uetr, row_number() OVER (PARTITION BY uetr ORDER BY id) AS n '
              'FROM legado.orden_pago WHERE uetr IN (SELECT uetr FROM legado.orden_pago WHERE id = ANY(%s))) o '
              'WHERE o.id = ANY(%s)')
OPERACIONES_PG = 'SELECT id, folio, sucursal FROM legado.operacion WHERE id = ANY(%s)'
LLAMADAS_PG = {
    'alta_moneda': ('INSERT INTO legado.moneda (codigo, numerico, nombre, decimales, activa) '
                    'VALUES (%(codigo)s, %(numerico)s, %(nombre)s, %(decimales)s, true)'),
    'baja_moneda': 'UPDATE legado.moneda SET activa = false WHERE codigo = %(codigo)s',
    'operacion': ('SELECT tobe_estado.registrar_operacion(%(fecha_operacion)s::timestamp, %(sucursal)s, %(canal)s, '
                  '%(cliente)s, %(cuenta_clabe)s, %(tipo)s, %(moneda)s, %(monto_divisa)s::numeric, '
                  '%(tipo_cambio_referencia)s::numeric, %(tipo_cambio)s::numeric)'),
    'orden': ('SELECT tobe_estado.registrar_orden(%(operacion_id)s::int, %(uetr)s, %(referencia_mt103)s, '
              '%(fecha_registro)s::timestamp, %(fecha_envio)s::timestamp, %(fecha_valor)s::date, %(bic_corresponsal)s, '
              '%(bic_intermediario)s, %(beneficiario)s, %(cuenta_beneficiario)s, %(moneda)s, %(monto)s::numeric, '
              '%(gastos)s, %(codigo_proposito)s)'),
    'liquidacion': ('SELECT tobe_estado.registrar_liquidacion(%(uetr)s, %(referencia)s, %(fecha_hora)s::timestamp, '
                    '%(abono)s::numeric, %(comision)s::numeric)'),
    'job': 'SELECT tobe_estado.conciliar()',
    'reflejar': 'SELECT tobe_estado.reflejar_estatus_operacion()',
    'alta_manual': ('SELECT tobe_estado.alta_manual_orden(%(operacion_id)s::int, %(uetr)s, %(referencia_mt103)s, '
                    '%(fecha_envio)s::timestamp, %(fecha_valor)s::date, %(bic_corresponsal)s, %(beneficiario)s, '
                    '%(cuenta_beneficiario)s, %(moneda)s, %(monto)s::numeric, %(gastos)s)'),
}


def preparar_tobe(pg, ms) -> dict:
    """La base cerrada como estado inicial del TO-BE: sus consumibles alineados a los del respaldo (la base los trae
    con margen) y la foto por fila (md5) contra la que se mide lo que cambia. Al final se regresa todo
    (`restaurar_tobe`) y la huella tiene que ser la de antes."""
    t0 = time.monotonic()
    huella = runbook.huella_destino(pg)
    cursor = ms.cursor()
    cursor.execute('SELECT serie, siguiente, actualizado FROM dbo.folio ORDER BY serie')
    del_respaldo = [(s, n, a) for s, n, a in cursor.fetchall()]
    with pg.transaction():
        for s, n, a in del_respaldo:
            pg.execute('UPDATE legado.folio SET siguiente = %s, actualizado = %s WHERE serie = %s', (n, a, s))
        pg.execute('CREATE SCHEMA paridad_estado')
        for t in ORDEN_TABLAS:
            pg.execute(_q_foto(TABLAS[t]))
    return {'huella': huella, 'folios_alineados': {s: n for s, n, _a in del_respaldo},
            'segundos': round(time.monotonic() - t0, 1)}


def restaurar_tobe(pg, preparado: dict) -> dict:
    with pg.transaction():
        for s, v in preparado['huella']['folios'].items():
            pg.execute('UPDATE legado.folio SET siguiente = %s, actualizado = %s WHERE serie = %s',
                       (v['siguiente'], v['actualizado'], s))
        pg.execute('DROP SCHEMA paridad_estado CASCADE')
    runbook._restaurar_secuencias(pg, preparado['huella']['secuencias'])
    ahora = runbook.huella_destino(pg)
    return {'huella_igual': ahora == preparado['huella'],
            'diferencias': base.delta.diferencias(preparado['huella'], ahora)}


def volcar_tobe(pg) -> dict[str, Efecto]:
    resultado = {}
    for t in ORDEN_TABLAS:
        tabla = TABLAS[t]
        despues = {f[0]: tuple(f) for f in pg.execute(_q_despues(tabla)).fetchall()}
        borradas = {k for (k,) in pg.execute(_q_borradas(tabla)).fetchall()}
        resultado[t] = Efecto(despues, borradas)
    return resultado


def refs_tobe(pg, ordenes: set, operaciones: set) -> Refs:
    refs = Refs()
    if ordenes:
        ids = sorted(int(i) for i in ordenes)
        refs.orden = {i: (u, n) for i, u, n in pg.execute(ORDENES_PG, (ids, ids)).fetchall()}
    if operaciones:
        refs.operacion = {i: (f, s) for i, f, s in pg.execute(OPERACIONES_PG, (sorted(operaciones),)).fetchall()}
    return refs


def correr_tobe(pg, escenario: estado.Escenario, entradas: dict, preparado: dict) -> dict:
    """El mismo escenario en el TO-BE: una transacción revertida con las funciones de `estado_tobe.sql`; después se
    regresan las secuencias (setval no es transaccional)."""
    t0 = time.monotonic()
    resultado = {'etapas': {}, 'llamadas': [], 'faltas': []}
    ids_operacion: dict[str, int] = {}
    try:
        with pg.transaction(force_rollback=True):
            pg.execute(DDL_TOBE.read_text(encoding='utf-8'))
            pg.execute("SELECT set_config('decant.usuario', %s, true)", (estado.USUARIO,))
            maximos = tuple(pg.execute(estado.MAXIMOS_PG).fetchone())
            for etapa in escenario.etapas:
                for n, llamada in enumerate(entradas[etapa.id], 1):
                    accion = llamada['accion']
                    args = (_args_orden(llamada['args'], ids_operacion) if accion in ('orden', 'alta_manual')
                            else llamada['args'])
                    pg.execute("SELECT set_config('decant.reloj', %s, true)", (llamada['reloj'].isoformat(),))
                    cursor = pg.execute(LLAMADAS_PG[accion], args)
                    devuelto = cursor.fetchone()[0] if cursor.description else None
                    nuevos = tuple(pg.execute(estado.MAXIMOS_PG).fetchone())
                    if accion == 'operacion' and llamada.get('ref'):
                        ids_operacion[llamada['ref']] = devuelto
                    if accion in ('operacion', 'orden', 'alta_manual'):
                        resultado['llamadas'].append({'etapa': etapa.id, 'escritor': etapa.escritor, 'n': n,
                                                      'accion': accion, 'devuelto': devuelto,
                                                      'insertadas': estado.inserciones(maximos, nuevos)})
                    maximos = nuevos
                efecto = volcar_tobe(pg)
                ordenes, operaciones = _ids_referidos(efecto)
                resultado['etapas'][etapa.id] = {'efecto': efecto, 'refs': refs_tobe(pg, ordenes, operaciones)}
    except Exception as error:      # el TO-BE rechazó una llamada: queda nombrada y el escenario no cuenta
        resultado['faltas'].append(f'TO-BE: {type(error).__name__}: {error}'[:1500])
    finally:
        runbook._restaurar_secuencias(pg, preparado['huella']['secuencias'])
        resultado['segundos'] = round(time.monotonic() - t0, 1)
    return resultado


# ── 4. la comparación por llave de negocio ──────────────────────────────────────────────────────────────────────

def iniciales(ms, corridas: list[dict]) -> dict[str, dict]:
    """El valor INICIAL (el respaldo, el mismo en los dos lados) de toda fila preexistente que tocó alguna corrida,
    leído del original por su llave. Una llave que el original no tiene es una fila nueva."""
    cursor = ms.cursor()
    resultado: dict[str, dict] = {t: {} for t in ORDEN_TABLAS}
    for corrida in corridas:
        for etapa in corrida['etapas'].values():
            for t, e in etapa['efecto'].items():
                resultado[t].update({k: None for k in set(e.despues) | e.borradas if k not in resultado[t]})
    for t, llaves in resultado.items():
        pendientes = [k for k, v in llaves.items() if v is None]
        encontradas = {}
        for i in range(0, len(pendientes), 20_000):
            cursor.execute(estado.POR_LLAVE_MS[t], (','.join(str(k) for k in pendientes[i:i + 20_000]),))
            encontradas.update({f[0]: tuple(f) for f in cursor.fetchall()})
        resultado[t] = {k: v for k, v in encontradas.items()}
    return resultado


def comparar_escenario(escenario: estado.Escenario, legado: dict, tobe: dict, inicial: dict) -> dict:
    """Etapa por etapa: lo que cambió en cada lado, por llave de negocio. Las referencias a filas preexistentes son las
    mismas en los dos lados (mismo estado inicial); las de filas nuevas, las de cada lado."""
    resultado = {}
    previo_l, previo_t = {}, {}
    for etapa in escenario.etapas:
        if etapa.id not in legado['etapas'] or etapa.id not in tobe['etapas']:
            resultado[etapa.id] = {'escritor': etapa.escritor, 'comparada': False}
            continue
        el, et = legado['etapas'][etapa.id], tobe['etapas'][etapa.id]
        refs_l, refs_t = Refs(), Refs()
        for r in (el['refs'], et['refs']):
            refs_l.orden.update({k: v for k, v in r.orden.items() if k in inicial['orden_pago']})
            refs_l.operacion.update({k: v for k, v in r.operacion.items() if k in inicial['operacion']})
        refs_t.unir(refs_l)
        refs_l.unir(el['refs'])
        refs_t.unir(et['refs'])
        _l, tocadas_l = estado.lado_de_etapa(previo_l, el['efecto'], inicial, refs_l)
        _t, tocadas_t = estado.lado_de_etapa(previo_t, et['efecto'], inicial, refs_t)
        cruce_l = {t: {k for k in ids if k in inicial[t]} for t, ids in tocadas_t.items()}
        cruce_t = {t: {k for k in ids if k in inicial[t]} for t, ids in tocadas_l.items()}
        lado_l, _ = estado.lado_de_etapa(previo_l, el['efecto'], inicial, refs_l, otras=cruce_l)
        lado_t, _ = estado.lado_de_etapa(previo_t, et['efecto'], inicial, refs_t, otras=cruce_t)
        diferencias = estado.comparar(lado_l, lado_t)
        resultado[etapa.id] = {
            'escritor': etapa.escritor, 'comparada': True, 'diferencias': diferencias,
            'tocadas': {t: {'legado': len(tocadas_l[t]), 'tobe': len(tocadas_t[t])} for t in ORDEN_TABLAS
                        if tocadas_l[t] or tocadas_t[t]}}
        previo_l, previo_t = el['efecto'], et['efecto']
    return resultado


CUENTA_1_N = """SELECT COUNT(*) FROM estado.operacion o
JOIN (SELECT operacion_id, estatus, ROW_NUMBER() OVER (PARTITION BY operacion_id ORDER BY id DESC) AS n
      FROM estado.orden_pago WHERE estatus <> 'REEMPLAZADA') v ON v.operacion_id = o.id AND v.n = 1
WHERE o.estatus <> CASE v.estatus WHEN 'CONCILIADA' THEN 'PAGADA' WHEN 'DIFERENCIA' THEN 'PAGADA'
                                  WHEN 'VENCIDA' THEN 'RECHAZADA' ELSE 'EN_PROCESO' END"""
REFLEJAR_MS = {'tal cual': 'EXEC estado.sp_reflejar_estatus_operacion',
               'maxdop1': 'EXEC estado.sp_reflejar_estatus_operacion_maxdop1'}


def variacion_de_plan(ms, repeticiones: int = 2) -> dict:
    """La cifra de r3-T1 contada en SQL (independiente de la comparación en Python): operaciones cuyo estatus quedó
    distinto del reflejo de su orden vigente, con la copia tal cual (otra vez) y con una variante del plan. Cada
    corrida en su transacción revertida, con la guarda."""
    cursor = ms.cursor()
    corridas = []
    for nombre in ['tal cual'] * repeticiones + [k for k in REFLEJAR_MS if k != 'tal cual']:
        t0 = time.monotonic()
        with revertida(cursor):
            cursor.execute('SELECT @@TRANCOUNT')
            antes = cursor.fetchone()[0]
            cursor.execute(REFLEJAR_MS[nombre])
            cursor.execute('SELECT @@TRANCOUNT')
            guarda = estado.guarda_trancount(REFLEJAR_MS[nombre], antes, cursor.fetchone()[0])
            cursor.execute(CUENTA_1_N)
            n = cursor.fetchone()[0]
        corridas.append({'variante': nombre, 'que': estado.VARIANTES_DE_PLAN.get(nombre, ('', '', '', 'la copia'))[3],
                         'operaciones_con_otro_estatus': n, 'guarda': guarda,
                         'segundos': round(time.monotonic() - t0, 1)})
    return {'corridas': corridas, 'distintas': sorted({c['operaciones_con_otro_estatus'] for c in corridas})}


def ordenes_por_operacion(ms) -> dict[tuple, list[tuple[int, str]]]:
    """Para el árbitro del 1:N: las órdenes de cada operación en el respaldo, por la llave de la operación."""
    cursor = ms.cursor()
    cursor.execute('SELECT o.folio, o.sucursal, p.id, p.estatus FROM dbo.orden_pago p '
                   'JOIN dbo.operacion o ON o.id = p.operacion_id')
    resultado: dict[tuple, list] = {}
    for folio, sucursal, i, e in cursor.fetchall():
        resultado.setdefault((folio, sucursal), []).append((int(i), e))
    return resultado


def uno_a_n(ms) -> dict:
    """Verificación fija: las escrituras con JOIN se miden con sus datos 1:N. Por cada UPDATE … FROM de los escritores,
    cuántas filas destino tienen varias filas fuente en el respaldo."""
    cursor = ms.cursor()
    cursor.execute('SELECT COUNT(*) FROM (SELECT operacion_id FROM dbo.orden_pago GROUP BY operacion_id '
                   'HAVING COUNT(*) > 1) x')
    reflejar = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM (SELECT orden_id FROM dbo.partida_liquidada WHERE concepto = 'PRINCIPAL' "
                   'GROUP BY orden_id HAVING COUNT(*) > 1) x')
    conciliar = cursor.fetchone()[0]
    return {'dbo.sp_reflejar_estatus_operacion': {
                'join': 'orden_pago p INNER JOIN operacion o ON o.id = p.operacion_id', 'destinos_con_varias_fuentes':
                reflejar, 'cubierto': reflejar > 0},
            'dbo.sp_conciliar': {
                'join': '#lote x, partida_solicitada agrupada por orden_id (1 por orden) y partida_liquidada PRINCIPAL',
                'destinos_con_varias_fuentes': conciliar,
                'cubierto': conciliar > 0,
                'nota': 'la agrupación hace 1:1 a partida_solicitada; PRINCIPAL es una por orden en estos datos: el '
                        '1:N no se puede probar con ellos (límite declarado)'}}


# ── 5 y 6. armar todo ───────────────────────────────────────────────────────────────────────────────────────────

def _resumen_etapa(c: dict) -> dict:
    if not c.get('comparada'):
        return {'escritor': c['escritor'], 'comparada': False}
    return {'escritor': c['escritor'], 'comparada': True, 'tocadas': c['tocadas'],
            'diferencias': estado.resumen_de_diferencias(c['diferencias'])}


def paridad_de_estado(ms, pg, objetos: list[dict], escritores: list[str], guion: dict, copia: dict,
                      informe: dict) -> dict:
    entradas = _entradas(guion, objetos)
    comando = copia['paso_del_job']['copia']
    cursor = ms.cursor()
    s = informe['segundos']
    preparado = preparar_tobe(pg, ms)
    s['tobe_preparar'] = preparado['segundos']
    evidencia_por_escenario, legado, tobe, comparacion = {}, {}, {}, {}
    base_stats = estadisticas(cursor)
    for escenario in estado.ESCENARIOS:
        legado[escenario.id] = correr_legado(ms, escenario, entradas, comando)
        evidencia_por_escenario[escenario.id] = estadisticas(cursor)
        tobe[escenario.id] = correr_tobe(pg, escenario, entradas, preparado)
        s[f'escenario_{escenario.id}'] = round(legado[escenario.id]['segundos'] + tobe[escenario.id]['segundos'], 1)
    # los controles de las trampas de r3: la copia con el parche del TO-BE
    con_parche = {}
    for escenario in estado.ESCENARIOS[1:]:
        con_parche[escenario.id] = correr_legado(ms, escenario, entradas, comando, sufijo='_con_parche')
    # el control de la guarda
    control = correr_legado(ms, estado.Escenario('D', 'control', (estado.Etapa('D1', 'estado.sp_control_con_rollback',
                                                                                'su propio ROLLBACK'),)),
                            {'D1': [{'accion': 'control', 'args': {}, 'reloj': entradas['B1'][0]['reloj']}]}, comando)
    t = time.monotonic()
    inicial = iniciales(ms, [*legado.values(), *con_parche.values(), *tobe.values()])
    ordenes = ordenes_por_operacion(ms)
    for escenario in estado.ESCENARIOS:
        comparacion[escenario.id] = comparar_escenario(escenario, legado[escenario.id], tobe[escenario.id], inicial)
    parches = {e: comparar_escenario(estado.ESCENARIOS[i + 1], con_parche[e], tobe[e], inicial)
               for i, e in enumerate(con_parche)}
    for c in [*comparacion.values(), *parches.values()]:
        for etapa in c.values():
            if etapa.get('comparada'):
                estado.arbitrar_1_n(etapa['diferencias'], ordenes)
    identidad = {'con_trampa': _identidades(legado['C'], tobe['C']), 'con_parche': _identidades(con_parche['C'],
                                                                                                tobe['C'])}
    identidad['todas_las_llamadas'] = [x for e in legado.values() for x in _revisar(e)]
    s['comparar'] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    plan = variacion_de_plan(ms)
    s['variacion_de_plan'] = round(time.monotonic() - t, 1)
    restaurado = restaurar_tobe(pg, preparado)
    # el N de N con lo que dice el servidor
    evidencia = _evidencia(base_stats, evidencia_por_escenario['C'], legado)
    sin_c = _evidencia(base_stats, evidencia_por_escenario['B'], {k: v for k, v in legado.items() if k != 'C'})
    nn = estado.n_de_n(escritores, evidencia)
    control_nn = estado.n_de_n(escritores, sin_c)
    return {
        'escritores': escritores, 'n_de_n': nn, 'evidencia': evidencia,
        'escenarios': {e.id: {'titulo': e.titulo, 'legado': _resumen_lado(legado[e.id]),
                              'tobe': _resumen_lado(tobe[e.id]),
                              'etapas': {k: _resumen_etapa(v) for k, v in comparacion[e.id].items()}}
                       for e in estado.ESCENARIOS},
        'con_parche': {e: {'que': estado.PARCHES[estado.ESCENARIOS[i + 1].etapas[-1].escritor][2],
                           'etapas': {k: _resumen_etapa(v) for k, v in parches[e].items()}}
                       for i, e in enumerate(parches)},
        'identidad': identidad, 'uno_a_n': uno_a_n(ms), 'variacion_de_plan_r3_t1': plan,
        'controles': {
            'guarda_trancount': _control_guarda(control),
            'n_de_n_sin_un_escritor': {
                'quitado': 'el escenario C (dbo.sp_alta_manual_orden): la evidencia del servidor ANTES de correrlo',
                'resultado': control_nn['faltas'], 'detectado': control_nn['faltas'] == [
                    'dbo.sp_alta_manual_orden: tiene escenario (C1) y el servidor no lo vio correr']}},
        'tobe_restaurado': restaurado, 'entradas': {k: len(v) for k, v in entradas.items()},
        'alta_manual': {'ref': entradas['C1'][0].get('ref'), 'reloj': entradas['C1'][0]['reloj'].isoformat(),
                        'operacion_del_dia': bool(entradas['C0'])},
        'noche': entradas['A4'][0]['reloj'].isoformat(),
        '_comparacion': comparacion, '_parches': parches}


def _resumen_lado(r: dict) -> dict:
    return {'faltas': r['faltas'], 'segundos': r['segundos'], 'llamadas': len(r['llamadas']),
            **({'efectos_emulados': {k: v['efectos_emulados'] for k, v in r['etapas'].items()
                                     if v.get('efectos_emulados')}} if any(
                v.get('efectos_emulados') for v in r['etapas'].values()) else {})}


def _revisar(lado: dict) -> list[dict]:
    resultado = []
    for llamada in lado['llamadas']:
        escritor = llamada['escritor']
        if escritor in estado.DEVUELVE:
            falla = estado.revisar_identidad(llamada, estado.DEVUELVE[escritor])
            if falla:
                resultado.append(falla)
    return resultado


def _identidades(legado: dict, tobe: dict) -> dict:
    """El id devuelto por la contingencia, en los dos lados, y la verificación fija en cada uno."""
    del_legado = next((x for x in legado['llamadas'] if x['etapa'] == 'C1'), None)
    del_tobe = next((x for x in tobe['llamadas'] if x['etapa'] == 'C1'), None)
    if del_legado is None or del_tobe is None:
        return {'comparada': False}
    return {'comparada': True, 'legado_devolvio': del_legado['devuelto'], 'legado_inserto': del_legado['insertadas'],
            'tobe_devolvio': del_tobe['devuelto'], 'tobe_inserto': del_tobe['insertadas'],
            'verificacion_legado': estado.revisar_identidad(del_legado, 'orden_pago'),
            'verificacion_tobe': estado.revisar_identidad(del_tobe, 'orden_pago'),
            'mismo_id': del_legado['devuelto'] == del_tobe['devuelto']}


def _evidencia(base: dict, despues: dict, legado: dict) -> dict:
    """Por escritor, cuántas veces lo ejecutó el servidor (estadísticas de la copia) entre el inicio y `despues`. El
    paso del job: su comando corrió sin error y el procedimiento que llama se ejecutó en esa etapa."""
    resultado = {}
    for nombre, n in despues.items():
        resultado[nombre] = {'ejecuciones': n - base.get(nombre, 0), 'fuente': 'sys.dm_exec_*_stats de la copia'}
    job_ok = 'A4' in legado.get('A', {}).get('etapas', {}) and not legado['A']['faltas']
    resultado[estado.JOB] = {'ejecuciones': 1 if job_ok and resultado.get('dbo.sp_conciliar', {}).get(
        'ejecuciones', 0) else 0, 'fuente': 'su comando de msdb corrió en A4 y el servidor vio a dbo.sp_conciliar'}
    return resultado


def _control_guarda(control: dict) -> dict:
    efecto = control['etapas'].get('D1', {}).get('efecto', {})
    cambios = sum(len(e.despues) + len(e.borradas) for e in efecto.values())
    return {'procedimiento': f'{ESQUEMA}.sp_control_con_rollback (UPDATE de un folio y su propio ROLLBACK)',
            'guarda': control['guarda'], 'error_del_servidor': next((x['error'] for x in control['llamadas']), None),
            'trancount_al_salir': control.get('trancount_al_salir'), 'cambios_en_el_volcado': cambios,
            'detectado': bool(control['guarda']) and cambios == 0,
            'lectura': 'la guarda lo detiene; sin ella, el volcado saldría vacío (0 cambios) aunque el procedimiento '
                       'escribió: la transacción externa se fue con su ROLLBACK'}


def borrar_copia(ms) -> dict:
    cursor = ms.cursor()
    cursor.execute(BORRAR_ESQUEMA)
    while cursor.nextset():
        pass
    cursor.execute("SELECT SCHEMA_ID(N'estado')")
    return {'esquema_borrado': cursor.fetchone()[0] is None, 'originales': huella_de_originales(cursor)}


# ── 6. el oráculo ───────────────────────────────────────────────────────────────────────────────────────────────

def reloj_propio(guion: dict) -> datetime:
    """El reloj PROPIO del TO-BE en el CI: el instante de negocio del congelamiento, en hora local. El del servidor del
    legado es el del runner (otro año): un TO-BE que no inyecta el del oráculo cae del otro lado de los datos."""
    instante = datetime.fromisoformat(guion['congelamiento_utc'])
    return instante.astimezone(CDMX).replace(tzinfo=None)


def _tobe_de_caso(pg, caso: oraculo.Caso, args: dict, reloj: datetime) -> list[dict]:
    if caso.objeto == oraculo.PANTALLA:
        return oraculo.pantalla_tobe(pg, caso, args, reloj)
    return oraculo.correr_tobe(pg, oraculo.TOBE[caso.objeto], args, reloj)


def comparar_oraculo(pg, capturado: dict, objetos: list[dict], guion: dict) -> dict:
    t0 = time.monotonic()
    lectores = [o['id'] for o in objetos if o['acceso'] == 'lee']
    nn = oraculo.n_de_n(lectores)
    definiciones = {c.id: c for c in oraculo.todos()}
    propio = reloj_propio(guion)
    casos = []
    for x in capturado['casos']:
        caso = definiciones[x['id']]
        args, servidor = x['argumentos'], datetime.fromisoformat(x['servidor'])
        con_reloj, con_propio = (_tobe_de_caso(pg, caso, args, servidor), _tobe_de_caso(pg, caso, args, propio))
        r = {'id': caso.id, 'objeto': caso.objeto, 'borde': caso.borde, 'argumentos': args,
             'servidor': x['servidor'], 'filas': [len(c['filas']) for c in x['conjuntos']],
             'inyectado': oraculo.comparar_conjuntos(x['conjuntos'], con_reloj),
             'propio': oraculo.comparar_conjuntos(x['conjuntos'], con_propio)}
        r['depende_del_reloj'] = oraculo.comparar_conjuntos(con_reloj, con_propio)['coincide'] is False
        if caso.objeto in oraculo.LITERAL:
            r['literal'] = oraculo.comparar_conjuntos(x['conjuntos'], oraculo.correr_tobe(
                pg, oraculo.LITERAL[caso.objeto], args, servidor))
        if caso.orden:
            r['orden'] = {'prometido': caso.de_donde, 'legado': oraculo.orden_incumplido(x['conjuntos'][0], caso.orden),
                          'tobe': oraculo.orden_incumplido(con_reloj[0], caso.orden)}
        if not r['inyectado']['coincide'] and (caso.objeto == 'dbo.sp_lista_operaciones' or (
                caso.objeto == oraculo.PANTALLA and caso.legado == '/')):
            r['arbitraje'] = _subconjunto(pg, caso, args, servidor, x['conjuntos'], con_reloj)
        casos.append(r)
    return {'n_de_n': nn, 'reloj_propio': propio.isoformat(), 'parametros': capturado['parametros'],
            'servidor_al_empezar': capturado['servidor_al_empezar'], 'casos': casos,
            'captura_segundos': capturado.get('segundos'), 'segundos': round(time.monotonic() - t0, 1)}


def _subconjunto(pg, caso, args: dict, reloj: datetime, legado: list[dict], tobe: list[dict]) -> dict:
    """La lista del día es `TOP (@maximo)` SIN ORDER BY (T1 del catálogo original): si el legado entregó otras filas, se
    audita que sean un subconjunto del día y del tamaño del TOP; si no, es defecto nuestro."""
    universo_args = {**args, 'maximo': None}
    if caso.objeto == oraculo.PANTALLA:
        universo = oraculo.pantalla_tobe(pg, caso, universo_args, reloj)
    else:
        universo = oraculo.correr_tobe(pg, oraculo.TOBE['dbo.sp_lista_operaciones'], universo_args, reloj)
    fallas = []
    for i, (a, b, u) in enumerate(zip(legado, tobe, universo)):
        if oraculo.comparar_conjunto(a, b)['coincide']:
            continue
        clases = [x or y for x, y in zip(a['clases'], u['clases'])]
        dentro = not (oraculo._filas(a, clases) - oraculo._filas(u, clases))
        tamano = len(a['filas']) == min(int(args.get('maximo') or 200), len(u['filas']))
        if not (dentro and tamano):
            fallas.append(i)
    explicada = not fallas
    return {'clase': estado.DEFECTO_LEGADO if explicada else estado.DEFECTO_NUESTRO,
            'explicacion': ('TOP sin ORDER BY: el legado entregó otro subconjunto del día, del tamaño del TOP '
                            '(T1 del catálogo original; el TO-BE ordena por fecha e id)') if explicada else
                           f'los conjuntos {fallas} no son un subconjunto del día'}


# ── 7. las trampas ──────────────────────────────────────────────────────────────────────────────────────────────

def _verificaciones_de_objeto(objeto: str, estado_r: dict, oraculo_r: dict) -> tuple[list[dict], list[dict]]:
    """Las comparaciones de un objeto que FALLAN con la trampa y las que PASAN sin ella (el parche del TO-BE)."""
    fallan, pasan = [], []
    for c in oraculo_r['casos']:
        if c['objeto'] != objeto:
            continue
        if c['inyectado']['coincide']:
            pasan.append({'comparacion': f"{c['id']}: TO-BE con el reloj del oráculo", 'cifra': 'coincide'})
        if c['depende_del_reloj'] and not c['propio']['coincide']:
            p = c['propio']['conjuntos'][0] if 'conjuntos' in c['propio'] else c['propio']
            fallan.append({'comparacion': f"{c['id']}: TO-BE con su reloj propio ({oraculo_r['reloj_propio']})",
                           'cifra': f"{p.get('solo_legado')} filas del oráculo faltan y {p.get('solo_tobe')} sobran "
                                    f"({p.get('filas_legado')} contra {p.get('filas_tobe')})"})
        if c.get('literal') and not c['literal']['coincide']:
            p = c['literal']['conjuntos'][0]
            fallan.append({'comparacion': f"{c['id']}: el SQL del legado copiado tal cual a PostgreSQL",
                           'cifra': f"{p.get('solo_legado')} de {p.get('filas_legado')} renglones distintos"})
        o = c.get('orden')
        if o and o['legado']['incumplidos']:
            fallan.append({'comparacion': f"{c['id']}: el orden prometido ({o['prometido']}) en la salida del legado",
                           'cifra': f"{o['legado']['incumplidos']:,} de {o['legado']['pares']:,} pares contiguos al "
                                    'revés'})
        if o and not o['tobe']['incumplidos'] and c['inyectado']['coincide']:
            pasan.append({'comparacion': f"{c['id']}: el orden prometido en la salida del TO-BE",
                          'cifra': f"0 de {o['tobe']['pares']:,} pares al revés"})
    for e, escenario in estado_r['escenarios'].items():
        for etapa_id, etapa in escenario['etapas'].items():
            if etapa.get('escritor') != objeto or not etapa.get('comparada'):
                continue
            d = etapa['diferencias']
            legado = d['por_clase'].get(estado.DEFECTO_LEGADO, 0)
            if legado:
                fallan.append({'comparacion': f'{etapa_id}: el efecto del legado contra el del TO-BE, por llave',
                               'cifra': f'{legado:,} diferencias, arbitradas como {estado.DEFECTO_LEGADO}'})
            elif d['total'] == 0:
                pasan.append({'comparacion': f'{etapa_id}: el efecto del legado contra el del TO-BE, por llave',
                              'cifra': '0 diferencias'})
            parche = estado_r['con_parche'].get(e, {}).get('etapas', {}).get(etapa_id)
            if parche and parche.get('comparada') and parche['diferencias']['total'] == 0:
                pasan.append({'comparacion': f'{etapa_id} con el parche del TO-BE en la copia del legado',
                              'cifra': '0 diferencias'})
    ident = estado_r['identidad']
    if objeto == 'dbo.sp_alta_manual_orden' and ident['con_trampa'].get('comparada'):
        v = ident['con_trampa']['verificacion_legado']
        if v and v['clase'] == estado.DEFECTO_LEGADO:
            fallan.append({'comparacion': 'C1: el id devuelto contra la fila insertada (verificación fija) y '
                                          'contra el id del TO-BE',
                           'cifra': f"devolvió {v['devuelto']:,} (de {', '.join(v['el_id_es_de'])}); la orden quedó "
                                    f"con {v['insertada_en']['orden_pago'][0]:,}; el TO-BE devolvió "
                                    f"{ident['con_trampa']['tobe_devolvio']:,}"})
        p = ident['con_parche']
        if p.get('comparada') and p['verificacion_legado'] is None and p['mismo_id']:
            pasan.append({'comparacion': 'C1 con el parche: el id devuelto contra la fila insertada y el del TO-BE',
                          'cifra': f"{p['legado_devolvio']:,} = la fila insertada = el del TO-BE"})
    return fallan, pasan


def aceptacion(estado_r: dict, oraculo_r: dict, cat: dict) -> dict:
    """Las 6 trampas observables: detectada si una comparación de su objeto FALLA (con nombre) y la misma comparación
    sin la trampa (el parche del TO-BE) PASA. Las latentes y la de S2 se reportan, no se exigen aquí."""
    por_obj = trampas.por_objeto(cat)
    filas = []
    for id_ in (*trampas.OBSERVABLES, *trampas.LATENTES):
        t = cat[id_]
        objetos = [o for o in t['objetos'] if o in {c['objeto'] for c in oraculo_r['casos']} or any(
            e.get('escritor') == o for s in estado_r['escenarios'].values() for e in s['etapas'].values())]
        # la trampa de la vista también la ve el procedimiento que la lee
        if id_ == 'r2-T1':
            objetos.append('dbo.sp_liquidaciones_recientes')
        fallan, pasan = [], []
        for o in objetos:
            f, p = _verificaciones_de_objeto(o, estado_r, oraculo_r)
            fallan += [{**x, 'objeto': o, 'nombre': trampas.nombrar(o, cat) or [id_]} for x in f]
            pasan += [{**x, 'objeto': o} for x in p]
        filas.append({'trampa': id_, 'titulo': t['titulo'], 'objetos': objetos,
                      'tipo': 'observable' if id_ in trampas.OBSERVABLES else 'latente (paso 6, plan variado)',
                      'detectada': bool(fallan) and bool(pasan), 'falla_con_la_trampa': fallan,
                      'pasa_sin_la_trampa': pasan, 'otros_en_el_objeto': [x for o in objetos
                                                                          for x in por_obj.get(o, []) if x != id_]})
    detectadas = [f['trampa'] for f in filas if f['tipo'] == 'observable' and f['detectada']]
    return {'observables': len(trampas.OBSERVABLES), 'detectadas': len(detectadas),
            'no_detectadas': [x for x in trampas.OBSERVABLES if x not in detectadas],
            'latentes_vistas_hoy': [f['trampa'] for f in filas
                                    if f['tipo'] != 'observable' and f['falla_con_la_trampa']],
            'filas': filas}


# ── el resumen ──────────────────────────────────────────────────────────────────────────────────────────────────

def tabla_de_escritores(estado_r: dict, objetos: list[dict]) -> list[dict]:
    """Por escritor: dónde corrió, cuántas veces según el servidor, qué tablas escribe (inventario), cuántas filas tocó
    en cada lado en SUS etapas (los anidados, en las de quien los llama) y qué diferencias quedaron, por clase."""
    donde = estado.cubiertos()
    etapas_de: dict[str, list[tuple[str, dict]]] = {}
    for x in estado_r['escenarios'].values():
        for k, v in x['etapas'].items():
            if v.get('escritor'):
                etapas_de.setdefault(v['escritor'], []).append((k, v))
            for anidado, ids in estado.ANIDADOS_EN.items():
                if k in ids:
                    etapas_de.setdefault(anidado, []).append((k, v))
    identidad = estado_r['identidad']['todas_las_llamadas']
    filas = []
    for e in estado_r['escritores']:
        tablas = sorted(t.removeprefix('dbo.') for t in estado.unidad(objetos, e)['efectivo']['escribe'])
        sus = etapas_de.get(e, [])
        tocadas: dict[str, dict] = {}
        clases: Counter = Counter()
        for _k, v in sus:
            for tabla in tablas:
                x = v.get('tocadas', {}).get(tabla)
                if x:
                    acumulado = tocadas.setdefault(tabla, {'legado': 0, 'tobe': 0})
                    acumulado['legado'] += x['legado']
                    acumulado['tobe'] += x['tobe']
            for d in v.get('diferencias', {}).get('por_tabla_y_columna', []):
                if d['tabla'] in tablas:
                    clases[d['clase']] += d['n']
        fallas = [f for f in identidad if f['escritor'] == e]
        partes = [f'{n:,} diferencias ({c})' for c, n in sorted(clases.items())] or ['efecto igual en las tablas']
        partes += [f"id devuelto {f['devuelto']:,} ≠ fila {f['insertada_en'][estado.DEVUELVE[e]]} ({f['clase']})"
                   for f in fallas]
        if e in estado.DEVUELVE and not fallas:
            partes.append('id devuelto = fila insertada en cada llamada')
        filas.append({'escritor': e, 'donde': ', '.join(k for k, _v in sus) or donde.get(e, '–'),
                      'como': donde.get(e) if e in estado.ANIDADOS else 'llamado por el arnés',
                      'ejecuciones': estado_r['evidencia'].get(e, {}).get('ejecuciones'),
                      'escribe': tablas, 'filas': tocadas, 'resultado': '; '.join(partes)})
    return filas


def resumen(informe: dict) -> str:
    lineas = [f"## Paridad de estado y oráculo del corte ({'verde' if informe.get('verde') else 'ROJO'})", '']
    b = informe.get('base', {})
    if b:
        v = b.get('verificacion', {})
        lineas.append(f"**Base de referencia:** {b.get('modo')} ({b.get('fuente') or 'sin fuente'}) · verificación "
                      f"{'verde' if v.get('verde') else 'ROJA'}; congelamiento: la copia con el delta del paso 4 "
                      f"({informe.get('delta', {}).get('insertadas')}).")
    e = informe.get('estado')
    if e:
        nn = e['n_de_n']
        lineas += ['', f"**Escritores: {nn['corridos']} de {nn['escritores']}** (del inventario del código; el "
                       'servidor los vio correr en la copia, en transacciones revertidas).', '',
                   '| escritor | dónde | ejecuciones | escribe | filas legado / TO-BE | resultado |',
                   '|---|---|---|---|---|---|']
        for f in informe.get('escritores', []):
            filas = '; '.join(f"{t} {x.get('legado', 0):,}/{x.get('tobe', 0):,}" for t, x in f['filas'].items() if x)
            lineas.append(f"| {f['escritor']} | {f['donde']} | {f['ejecuciones']} | {', '.join(f['escribe'])} | "
                          f"{filas or '–'} | {f['resultado']} |")
        c = e['controles']
        lineas += ['', '| control negativo | detectado | cómo |', '|---|---|---|',
                   f"| procedimiento con su propio ROLLBACK | {'sí' if c['guarda_trancount']['detectado'] else 'NO'} | "
                   f"{str(c['guarda_trancount']['guarda'])[:200]} · volcado: "
                   f"{c['guarda_trancount']['cambios_en_el_volcado']} cambios |",
                   f"| sin un escritor en la corrida | {'sí' if c['n_de_n_sin_un_escritor']['detectado'] else 'NO'} | "
                   f"{'; '.join(c['n_de_n_sin_un_escritor']['resultado'])[:200]} |"]
        v = e.get('variacion_de_plan_r3_t1')
        if v:
            lineas += ['', '**r3-T1 contado en SQL** (operaciones con un estatus distinto del reflejo de su orden '
                           'vigente): ' + ' · '.join(f"{x['variante']} {x['operaciones_con_otro_estatus']:,}"
                                                    for x in v['corridas']) + '.']
    a = informe.get('aceptacion')
    if a:
        lineas += ['', f"**Trampas con efecto observable: {a['detectadas']} de {a['observables']} detectadas.**", '',
                   '| trampa | objeto | falla con la trampa (cifra) | pasa sin ella |', '|---|---|---|---|']
        for f in a['filas']:
            falla = '; '.join(f"{x['comparacion']}: {x['cifra']}" for x in f['falla_con_la_trampa'][:2]) or '–'
            pasa = '; '.join(f"{x['comparacion']}: {x['cifra']}" for x in f['pasa_sin_la_trampa'][:1]) or '–'
            lineas.append(f"| {f['trampa']} ({f['tipo']}) | {', '.join(f['objetos'])} | {falla[:400]} | {pasa[:200]} |")
    o = informe.get('oraculo')
    if o:
        lineas += ['', f"**Oráculo:** {o['n_de_n']['con_caso']} de {o['n_de_n']['lectores']} objetos de lectura, "
                       f"{len(o['casos'])} casos ({sum(1 for c in o['casos'] if c['borde'])} en el borde del cierre de "
                       f"mes); reloj del servidor {o['servidor_al_empezar']}, reloj propio del TO-BE "
                       f"{o['reloj_propio']}."]
    lineas += ['', 'Tiempos: ' + ' · '.join(f'{k} {v} s' for k, v in informe['segundos'].items()) + '.']
    lineas += [f'- ✘ {f}' for f in informe.get('faltas', [])]
    return '\n'.join(lineas) + '\n'


def faltas_de(informe: dict) -> list[str]:
    faltas = list(informe.get('faltas', []))
    v = informe.get('base', {}).get('verificacion', {})
    faltas += [f'base: {f}' for f in v.get('faltas', [])]
    e = informe.get('estado')
    if e:
        faltas += [f'N de N: {f}' for f in e['n_de_n']['faltas']]
        for s, x in e['escenarios'].items():
            faltas += [f'escenario {s} (legado): {f}' for f in x['legado']['faltas']]
            faltas += [f'escenario {s} (TO-BE): {f}' for f in x['tobe']['faltas']]
            for k, etapa in x['etapas'].items():
                if not etapa.get('comparada'):
                    faltas.append(f'{k}: la etapa no se comparó')
                    continue
                n = etapa['diferencias']['por_clase'].get(estado.DEFECTO_NUESTRO, 0)
                if n:
                    muestra = json.dumps(etapa['diferencias']['muestra'][:2], ensure_ascii=False, default=str)
                    faltas.append(f"{k} ({etapa['escritor']}): {n:,} diferencias sin explicar (defecto nuestro): "
                                  f'{muestra[:600]}')
        for x in e['con_parche'].values():
            for k, etapa in x['etapas'].items():
                if etapa.get('comparada') and etapa['diferencias']['total']:
                    faltas.append(f"{k} con el parche: {etapa['diferencias']['total']:,} diferencias "
                                  '(tenían que ser 0)')
        for falla in e['identidad']['todas_las_llamadas']:
            if falla['clase'] == estado.DEFECTO_NUESTRO:
                faltas.append(f"identidad: {falla['explicacion']}")
        for nombre, c in e['controles'].items():
            if not c['detectado']:
                faltas.append(f'control {nombre} no detectado')
        faltas += [f"variación de plan: {c['guarda']}" for c in e['variacion_de_plan_r3_t1']['corridas']
                   if c['guarda']]
        if not e['tobe_restaurado']['huella_igual']:
            faltas.append(f"la base del TO-BE no volvió a su huella: {e['tobe_restaurado']['diferencias'][:5]}")
    o = informe.get('oraculo')
    if o:
        faltas += [f'oráculo: {f}' for f in o['n_de_n']['faltas']]
        for c in o['casos']:
            if not c['inyectado']['coincide'] and c.get('arbitraje', {}).get('clase') != estado.DEFECTO_LEGADO:
                faltas.append(f"oráculo {c['id']}: el TO-BE con el reloj del oráculo no coincide "
                              f"{json.dumps(c['inyectado'], ensure_ascii=False, default=str)[:600]}")
            if c.get('orden') and c['orden']['tobe']['incumplidos']:
                faltas.append(f"oráculo {c['id']}: el TO-BE incumple el orden prometido")
    a = informe.get('aceptacion')
    if a and a['no_detectadas']:
        faltas.append(f"trampas no detectadas: {a['no_detectadas']} ({a['detectadas']} de {a['observables']})")
    if 'aceptacion' not in informe and 'error' not in informe:
        faltas.append('la corrida no llegó a la aceptación de las trampas')
    if informe.get('copia', {}).get('al_terminar') and not informe['copia']['al_terminar']['esquema_borrado']:
        faltas.append('la copia temporal no se borró')
    if informe.get('copia', {}).get('originales') and \
            informe['copia']['al_terminar']['originales'] != informe['copia']['originales']:
        faltas.append('los originales del respaldo cambiaron durante la corrida')
    return faltas


# ── el conductor ────────────────────────────────────────────────────────────────────────────────────────────────

def _q_copiar_base(nueva: str, plantilla: str):
    from psycopg import sql
    return sql.SQL('CREATE DATABASE {} TEMPLATE {}').format(sql.Identifier(base._nombre(nueva)),
                                                            sql.Identifier(base._nombre(plantilla)))


def preparar_bases(args, ms_corte, p: dict, corte: dict) -> dict:
    """La base cerrada (restaurada o construida) y su copia, donde se aplica el delta: el estado del congelamiento."""
    resultado = delta_ci.preparar_base(args, ms_corte, p, corte)
    if resultado['verificacion']['verde']:
        import psycopg

        from paridad.tobe import parametros
        with psycopg.connect(dbname='postgres', autocommit=True, **parametros()) as admin:
            admin.execute(base._q_borrar_base(args.oraculo_base))
            admin.execute(_q_copiar_base(args.oraculo_base, args.destino_base))
    return resultado


def aplicar_delta(pg, ms_vivo, corte: dict, tope: dict, vivo: dict) -> dict:
    t0 = time.monotonic()
    runbook_delta.preparar(pg)
    d = runbook_delta.leer_delta(pg, ms_vivo, corte, tope, vivo)
    runbook_delta.cargar_delta(pg, d, confirmar=False)
    aplicado = runbook_delta.cargar_delta(pg, d, confirmar=True)
    return {'insertadas': aplicado['insertadas'], 'actualizadas': aplicado['actualizadas'],
            'segundos': round(time.monotonic() - t0, 1)}


def _sin_internos(valor):
    if isinstance(valor, dict):
        return {k: _sin_internos(v) for k, v in valor.items() if not str(k).startswith('_')}
    if isinstance(valor, list):
        return [_sin_internos(v) for v in valor]
    return valor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.estado_ci', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', type=Path, default=Path('corte/base'), help='carpeta con destino.dump y destino.json')
    parser.add_argument('--construir-base', action='store_true', help='sin volcado: cargar los 36 meses y cerrar')
    parser.add_argument('--fuente', default='', help='de dónde vino el volcado (para el resumen)')
    parser.add_argument('--contenedor', default='decant-pg-estado')
    parser.add_argument('--destino-base', default='decant_corte_estado')
    parser.add_argument('--oraculo-base', default='decant_corte_oraculo')
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--manifiesto', type=Path, default=None)
    parser.add_argument('--resumen', type=Path, default=None)
    parser.add_argument('--margen-folios', type=int, default=10_000)
    args = parser.parse_args(argv)
    t0 = time.monotonic()
    args.salida.mkdir(parents=True, exist_ok=True)
    informe: dict = {'version': 1, 'segundos': {}, 'faltas': []}
    s = informe['segundos']
    try:
        manifiesto = args.manifiesto or runbook._ultimo_manifiesto()
        if manifiesto is None:
            raise SystemExit('falta el manifiesto del respaldo: corre antes ./ciclo.sh')
        inventario = codigo.inventario()
        objetos, escritores = inventario['objetos'], inventario['escritores']
        guion = _json(runbook_delta.ultimo(DATOS, 'delta_*.json'))
        capturado = _json(runbook_delta.ultimo(DATOS, 'oraculo_*.json'))
        cat = trampas.catalogo()
        t = time.monotonic()
        informe['origen'] = carga_ci.restaurar_corte(manifiesto)
        corte, tope, vivo = runbook_delta.contexto(manifiesto)
        s['respaldo'] = round(time.monotonic() - t, 1)
        t = time.monotonic()
        with runbook.conectar_origen() as ms_corte:
            p = runbook.leer_plan(ms_corte, corte)
            informe['base'] = preparar_bases(args, ms_corte, p, corte)
        s['base'] = round(time.monotonic() - t, 1)
        if informe['base']['verificacion']['verde']:
            t = time.monotonic()
            with runbook.conectar_destino(args.oraculo_base) as pg_o, \
                    runbook.conectar_origen(runbook_delta.ORIGEN_VIVO) as ms_vivo:
                informe['delta'] = aplicar_delta(pg_o, ms_vivo, corte, tope, vivo)
                s['delta'] = round(time.monotonic() - t, 1)
                t = time.monotonic()
                informe['oraculo'] = comparar_oraculo(pg_o, capturado, objetos, guion)
                s['oraculo'] = round(time.monotonic() - t, 1)
            efectos = estado.efectos_declarados(objetos, escritores)
            informe['efectos_fuera_de_la_base'] = efectos
            with runbook.conectar_origen() as ms, runbook.conectar_destino(args.destino_base) as pg:
                t = time.monotonic()
                try:
                    informe['copia'] = preparar_copia(ms, objetos, escritores, efectos)
                    s['copia'] = round(time.monotonic() - t, 1)
                    informe['estado'] = paridad_de_estado(ms, pg, objetos, escritores, guion, informe['copia'], informe)
                finally:
                    informe.setdefault('copia', {})['al_terminar'] = borrar_copia(ms)
            informe['escritores'] = tabla_de_escritores(informe['estado'], objetos)
            informe['aceptacion'] = aceptacion(informe['estado'], informe['oraculo'], cat)
    except (Negado, NoCuadra, NoSeCopia) as error:
        informe['faltas'].append(f'{type(error).__name__}: {error}'[:3000])
        informe['error'] = traceback.format_exc()
    except Exception as error:      # cualquier otra: el informe y el resumen salen igual, y el job en rojo
        informe['faltas'].append(f'{type(error).__name__}: {error}'[:3000])
        informe['error'] = traceback.format_exc()
    s['total'] = round(time.monotonic() - t0, 1)
    informe['faltas'] = faltas_de(informe)
    informe['verde'] = not informe['faltas']
    (args.salida / 'estado.json').write_text(
        json.dumps(_sin_internos(informe), ensure_ascii=False, indent=1, default=str) + '\n', encoding='utf-8')
    texto = resumen(informe)
    print(texto)
    if informe.get('error'):
        print(informe['error'], file=sys.stderr)
    if args.resumen:
        with args.resumen.open('a', encoding='utf-8') as salida:
            salida.write(texto)
    return 0 if informe['verde'] else 1


if __name__ == '__main__':
    sys.exit(main())

