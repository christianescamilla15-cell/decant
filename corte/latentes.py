"""Las trampas LATENTES con el plan VARIADO (S3 paso 6; ADR 0011 y 0014; criterio 2 del plan). Sin base: los objetos y
sus universos, las variantes del plan, el parche del TO-BE, el lote suelto, la lectura del plan REAL, la comparación del
legado consigo mismo y contra el TO-BE, sus árbitros y la aceptación. Lo que toca las bases lo hace
`corte/latentes_ci.py` (job `latentes` de `carga.yml`).

- **Latente:** la salida depende de un orden que nada asegura (una variable asignada desde un SELECT que recorre varias
  filas: se queda con la ÚLTIMA que entregue el plan) y con el plan de hoy acierta. Sólo se ve si el plan cambia.
- **Dónde:** en la COPIA temporal del paso 5 (esquema `estado` del respaldo restaurado, verificada igual al original),
  nunca en el original. Cada variante es otra copia del objeto (con su pista en la sentencia), el mismo cuerpo como
  lote suelto, o la misma copia con sus estadísticas recalculadas y sus planes fuera de la caché: las estadísticas, la
  caché y las pistas son SÓLO de la copia. Cada corrida va en una transacción revertida con la guarda de
  `@@TRANCOUNT`.
- **Qué se exige:**
  - el legado coincide CONSIGO MISMO en todas las variantes; si no, la comparación falla NOMBRANDO la trampa (de los
    catálogos sellados, después de detectar) y queda como defecto del legado, pendiente de decisión de negocio;
  - cada variante se compara además contra el TO-BE, que fija el orden explícito;
  - una variante sólo «detecta» si el plan REAL cambió (`query_plan_hash` de la sentencia en
    `sys.dm_exec_query_stats`, con su showplan). Una variante con el mismo plan que dé otra salida no es del plan: se
    reporta como no determinista con el mismo plan;
  - con el parche del TO-BE aplicado en la copia, todas las variantes coinciden entre sí y con el TO-BE.
- **Honestidad:** una latente que no se manifiesta con ninguna variante natural NO cuenta como detectada. Se reporta con
  las cifras, con qué faltaría, y con las pistas que la fuerzan en la copia, declaradas como forzadas.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from corte.estado import ESQUEMA, NoSeCopia

MARCA = 'decant:latentes'          # comentario al inicio de cada lote suelto: lo encuentra en la caché de planes
MUESTRA = 10


@dataclass(frozen=True)
class Objeto:
    """Un objeto de lectura cuya salida depende del orden de las filas."""
    id: str
    parametro: str                       # el parámetro del procedimiento: en el lote suelto, una variable local
    tipo: str
    sentencia: str                       # la asignación desde varias filas, EXACTA como está en el código
    clave: str                           # el fragmento que la identifica en la caché de planes
    parche: str                          # la misma sentencia con la regla del TO-BE (el orden explícito)
    salida: tuple[tuple[str, str], ...]  # las columnas de su conjunto de resultados, con su tipo (para INSERT … EXEC)
    unidad: tuple[str, ...]              # con la entrada, lo que identifica un renglón de la salida
    alimenta: tuple[str, ...]            # las columnas de la salida que salen de las variables asignadas
    universo: str                        # las entradas: todas las de los datos donde el orden decide (sobre la copia)
    que: str
    cada: int                            # la muestra del PR para lo pesado: 1 de cada `cada` entradas, en orden
    fin: str | None = None               # dónde termina la sentencia (recibe la pista); None = la sentencia misma


R1_T1 = Objeto(
    id='dbo.sp_reporte_posicion', parametro='@fecha', tipo='date',
    sentencia=('SELECT @tc_cierre = tipo_cambio\n'
               '        FROM dbo.operacion\n'
               '        WHERE moneda = @moneda AND fecha_operacion >= @fecha '
               'AND fecha_operacion < DATEADD(day, 1, @fecha);'),
    clave='@tc_cierre = tipo_cambio',
    parche=('SELECT TOP (1) @tc_cierre = tipo_cambio\n'
            '        FROM dbo.operacion\n'
            '        WHERE moneda = @moneda AND fecha_operacion >= @fecha '
            'AND fecha_operacion < DATEADD(day, 1, @fecha)\n'
            '        ORDER BY fecha_operacion DESC, id DESC;'),
    salida=(('moneda', 'char(3)'), ('nombre', 'nvarchar(60)'), ('compras', 'decimal(18, 2)'),
            ('ventas', 'decimal(18, 2)'), ('posicion', 'decimal(19, 2)'), ('tc_cierre', 'decimal(18, 6)'),
            ('posicion_mxn', 'decimal(38, 8)')),
    unidad=('moneda',), alimenta=('tc_cierre', 'posicion_mxn'),
    universo=f'SELECT DISTINCT CAST(fecha_operacion AS date) FROM {ESQUEMA}.operacion ORDER BY 1',
    que='asigna @tc_cierre desde un SELECT sin TOP ni ORDER BY que recorre todas las operaciones del día en la moneda: '
        'queda el tipo de cambio de la última fila que entregue el plan',
    cada=10)

R2_T2 = Objeto(
    id='dbo.sp_constancia_operacion', parametro='@operacion_id', tipo='int',
    sentencia='LEFT JOIN dbo.orden_pago p ON p.operacion_id = o.id',
    clave='@estatus_orden = p.estatus',
    parche=("LEFT JOIN dbo.orden_pago p ON p.id = (SELECT TOP (1) q.id FROM dbo.orden_pago q "
            "WHERE q.operacion_id = o.id AND q.estatus <> 'REEMPLAZADA' ORDER BY q.id DESC)"),
    salida=(('folio', 'varchar(20)'), ('cliente', 'nvarchar(120)'), ('moneda', 'char(3)'),
            ('monto_divisa', 'decimal(18, 2)'), ('monto_mxn', 'decimal(18, 2)'), ('folio_orden', 'varchar(20)'),
            ('uetr', 'char(36)'), ('estatus_orden', 'varchar(12)'), ('fecha_envio', 'datetime')),
    unidad=(), alimenta=('folio_orden', 'uetr', 'estatus_orden', 'fecha_envio'),
    universo=(f'SELECT operacion_id FROM {ESQUEMA}.orden_pago GROUP BY operacion_id HAVING COUNT(*) > 1 '
              'ORDER BY operacion_id'),
    que='asigna variables desde un SELECT filtrado por la llave de la operación con un LEFT JOIN a orden_pago, que es '
        '1:N con ella (cada re-registro deja una fila REEMPLAZADA): queda la última orden que entregue el plan',
    cada=10, fin='WHERE o.id = @operacion_id;')

OBJETOS = (R1_T1, R2_T2)


@dataclass(frozen=True)
class Variante:
    id: str
    sufijo: str                  # el nombre de su copia: estado.<objeto>_<sufijo> ('' = la copia tal cual)
    que: str
    pista: str | None = None     # OPTION (…) agregado a la sentencia, sólo en la copia
    lote: bool = False           # el cuerpo como lote suelto, con el parámetro como variable local
    preparar: bool = False       # estadísticas recalculadas (FULLSCAN) de la copia y sus planes fuera de la caché
    forzada: bool = False        # una pista que nadie del legado usa: si detecta, se declara forzada
    pesada: bool = False         # en el PR corre sobre la muestra (de noche, sobre todo el universo)
    repite: bool = False         # la misma copia otra vez, con su plan en la caché
    cada: int = 0                # > 0: SIEMPRE sobre 1 de cada `cada` entradas (una forzada muy cara)


TAL_CUAL = Variante('tal cual', '', 'la copia tal cual: el plan que el optimizador elige hoy')
OTRA_VEZ = Variante('tal cual, otra vez', '', 'la misma copia con su plan en la caché (control: el mismo plan no '
                                             'puede «detectar»)', repite=True)
MAXDOP4 = Variante('MAXDOP 4', 'maxdop4', 'OPTION (MAXDOP 4) en la sentencia de la copia (los núcleos del runner)',
                   pista='MAXDOP 4')
MAXDOP1 = Variante('MAXDOP 1', 'maxdop1', 'OPTION (MAXDOP 1) en la sentencia de la copia (sin paralelismo)',
                   pista='MAXDOP 1')
LOTE = Variante('lote suelto', 'lote', 'el cuerpo del procedimiento como lote suelto, con el parámetro como variable '
                                       'local: el optimizador no conoce su valor al compilar', lote=True)
LOTE_MAXDOP1 = Variante('lote suelto, MAXDOP 1', 'lote_maxdop1', 'el mismo lote suelto con OPTION (MAXDOP 1) en la '
                        'sentencia: el recorrido sin paralelismo', pista='MAXDOP 1', lote=True, pesada=True)
# Va al final: recalcula las estadísticas de las tablas de la copia y todo lo que corre después ya las ve.
ESTADISTICAS = Variante('estadísticas y caché', '', 'estadísticas recalculadas con FULLSCAN en las tablas de la '
                                                    'copia y los planes de la copia fuera de la caché', preparar=True)
VARIANTES = {
    R1_T1.id: (TAL_CUAL, OTRA_VEZ, MAXDOP4, MAXDOP1, replace(LOTE, pesada=True), LOTE_MAXDOP1,
               Variante('OPTIMIZE FOR UNKNOWN', 'desconocido', 'la copia compilada sin olfatear el parámetro (pista '
                        'OPTIMIZE FOR UNKNOWN): lo que hace el lote suelto, dentro del procedimiento',
                        pista='OPTIMIZE FOR UNKNOWN', forzada=True, cada=10),
               ESTADISTICAS),
    # r2-T2 recorre 104,773 operaciones por variante: en el PR, lo que no es la copia tal cual va en muestra.
    R2_T2.id: (TAL_CUAL, *(replace(v, pesada=True) for v in (OTRA_VEZ, MAXDOP4, MAXDOP1, LOTE)),
               Variante('HASH JOIN', 'hash', 'pista HASH JOIN en la copia', pista='HASH JOIN', forzada=True),
               Variante('MERGE JOIN', 'merge', 'pista MERGE JOIN en la copia', pista='MERGE JOIN', forzada=True),
               Variante('recorrido paralelo', 'paralelo', 'orden_pago recorrida entera y en paralelo (pistas TABLE '
                        'HINT(p, INDEX(pk_orden_pago)) y ENABLE_PARALLEL_PLAN_PREFERENCE en la copia)',
                        pista="TABLE HINT(p, INDEX(pk_orden_pago)), USE HINT('ENABLE_PARALLEL_PLAN_PREFERENCE')",
                        forzada=True, cada=100),
               replace(ESTADISTICAS, pesada=True)),
}
# Una pista que el optimizador no puede cumplir (error 8622) no es una variante del plan: se reporta «no aplica».
NO_COMPILA = 8622


def con_parche(objeto: Objeto) -> tuple[Variante, ...]:
    """Con el parche del TO-BE corren las variantes que cambian algo (la de la caché repetida, no)."""
    return tuple(v for v in VARIANTES[objeto.id] if not v.repite)


def cada_cuanto(objeto: Objeto, v: Variante, completo: bool) -> int:
    """1 = todo el universo; n = 1 de cada n entradas (la muestra)."""
    if v.cada:
        return v.cada
    return objeto.cada if v.pesada and not completo else 1


def variante(objeto: Objeto, id_: str) -> Variante:
    return next(v for v in VARIANTES[objeto.id] if v.id == id_)


# ── el texto de cada copia ──────────────────────────────────────────────────────────────────────────────────────

def texto_de_variante(original: str, objeto: Objeto, v: Variante, parche: bool) -> tuple[str, list[tuple[str, str]]]:
    """El texto ORIGINAL con la sentencia de la variante: la del parche del TO-BE (si se pide) y la pista de la variante
    en su OPTION, al fin de la sentencia. Cada reemplazo es exacto y su texto tiene que aparecer UNA vez: si el código
    cambia, la copia se niega en vez de variar otra cosa. Devuelve también los reemplazos hechos."""
    reemplazos: list[tuple[str, str]] = []
    if parche:
        reemplazos.append((objeto.sentencia, objeto.parche))
    if v.pista is not None:
        fin = objeto.fin or (objeto.parche if parche else objeto.sentencia)
        if not fin.endswith(';'):
            raise NoSeCopia(f'{objeto.id}: la sentencia no termina en «;»')
        reemplazos.append((fin, f'{fin[:-1]} OPTION ({v.pista});'))
    texto = original
    for viejo, nuevo in reemplazos:
        if texto.count(viejo) != 1:
            raise NoSeCopia(f'{objeto.id}: el texto no aparece exactamente una vez: {viejo!r} ({texto.count(viejo)})')
        texto = texto.replace(viejo, nuevo)
    return texto, reemplazos


def nombre_de_copia(objeto: Objeto, v: Variante, parche: bool) -> str:
    partes = [objeto.id.split('.')[1]] + (['parche'] if parche else []) + ([v.sufijo] if v.sufijo else [])
    return f"{ESQUEMA}.{'_'.join(partes)}"


def renombrar(texto: str, nombre: str) -> str:
    """La copia de un procedimiento (ya en `estado`) con otro nombre."""
    nuevo, n = re.subn(rf'(CREATE\s+PROCEDURE\s+){ESQUEMA}\.\w+', rf'\g<1>{nombre}', texto, count=1)
    if n != 1:
        raise NoSeCopia(f'no se encontró la cabecera del procedimiento para llamarlo {nombre}')
    return nuevo


# El texto guardado empieza con los comentarios que preceden al CREATE en su lote (así lo guarda SQL Server).
_CABECERA = re.compile(rf'^(?:\s*--[^\n]*\n)*\s*CREATE\s+PROCEDURE\s+{ESQUEMA}\.\w+\s+(?P<parametros>.*?)\s+AS\s+'
                       r'BEGIN\b(?P<cuerpo>.*)\bEND\s*$', re.S | re.I)


def lote_suelto(copia: str, objeto: Objeto, v: Variante, parche: bool) -> str:
    """El cuerpo de la copia como lote suelto: el parámetro pasa a ser una variable LOCAL que toma su valor de la
    entrada (`@entrada`, parámetro de sp_executesql). El optimizador no conoce el valor de una variable local al
    compilar: es lo que hizo el catálogo («la MISMA sentencia en un lote suelto, con variables locales»)."""
    m = _CABECERA.match(copia)
    if not m or m.group('parametros').strip() != f'{objeto.parametro} {objeto.tipo}':
        raise NoSeCopia(f'{objeto.id}: el lote suelto espera un solo parámetro {objeto.parametro} {objeto.tipo}')
    marca = f"/* {MARCA}:{objeto.id}:{'parche:' if parche else ''}{v.sufijo} */"
    return f"{marca}\nDECLARE {objeto.parametro} {objeto.tipo} = @entrada;{m.group('cuerpo').rstrip()}\n"


def columnas_de_salida(objeto: Objeto) -> str:
    return ', '.join(f'[{c}] {t} NULL' for c, t in objeto.salida)


def conductor(objeto: Objeto, llamada: str, lote: bool = False) -> str:
    """El lote que corre la variante sobre TODAS sus entradas en el servidor (una llamada por entrada, como la haría el
    consumidor) y captura su conjunto de resultados con INSERT … EXEC. La guarda de @@TRANCOUNT corre en cada vuelta:
    si una llamada cambia la transacción, el lote se detiene y lo dice. `llamada` sale de las constantes de aquí; el
    texto del lote suelto (`lote`) entra como PARÁMETRO (%s), nunca pegado al texto."""
    columnas = ', '.join(f'[{c}]' for c, _t in objeto.salida)
    return (('DECLARE @lote nvarchar(max) = %s;\n' if lote else '') +
            f'SET NOCOUNT ON;\n'
            f'DECLARE @t0 int = @@TRANCOUNT, @i int = 1, @n int, @p {objeto.tipo}, @ultimo int = 0, @roto int = 0;\n'
            f'SELECT @n = COUNT(*) FROM #entradas;\n'
            f'WHILE @i <= @n\nBEGIN\n'
            f'    SELECT @p = valor FROM #entradas WHERE i = @i;\n'
            f'    INSERT INTO #salida ({columnas}) {llamada};\n'
            f'    IF @@TRANCOUNT <> @t0 BEGIN SET @roto = @i; BREAK; END;\n'
            f'    UPDATE #salida SET i = @i WHERE n > @ultimo;\n'
            f'    SELECT @ultimo = ISNULL(MAX(n), 0) FROM #salida;\n'
            f'    SET @i += 1;\nEND;\n'
            f'SELECT @t0, @@TRANCOUNT, @roto, @i - 1;')


def llamada_de(objeto: Objeto, v: Variante, parche: bool) -> str:
    if v.lote:
        return f"EXEC sp_executesql @lote, N'@entrada {objeto.tipo}', @entrada = @p"
    return f'EXEC {nombre_de_copia(objeto, v, parche)} {objeto.parametro} = @p'


def tablas_temporales(objeto: Objeto) -> str:
    return (f'CREATE TABLE #entradas (i int IDENTITY(1, 1) PRIMARY KEY, valor {objeto.tipo} NOT NULL); '
            f'CREATE TABLE #salida (n int IDENTITY(1, 1) PRIMARY KEY, i int NULL, {columnas_de_salida(objeto)});')


def cargar_entradas(objeto: Objeto) -> str:
    return ("INSERT INTO #entradas (valor) SELECT CAST(value AS " + objeto.tipo + ") FROM STRING_SPLIT(%s, ',', 1) "
            'ORDER BY ordinal')


def leer_salida(objeto: Objeto) -> str:
    columnas = ', '.join(f's.[{c}]' for c, _t in objeto.salida)
    return f'SELECT e.valor, {columnas} FROM #salida s JOIN #entradas e ON e.i = s.i ORDER BY s.n'


def muestra(entradas: list, cada: int) -> list:
    """1 de cada `cada` entradas, en orden (determinista): cubre todo el histórico."""
    return entradas[::cada]


# ── el plan real ────────────────────────────────────────────────────────────────────────────────────────────────

PLANES = """SELECT CONVERT(varchar(18), qs.query_plan_hash, 1), qs.execution_count, qs.last_dop, qs.max_dop,
       CONVERT(varchar(130), qs.plan_handle, 1),
       SUBSTRING(st.text, qs.statement_start_offset / 2 + 1,
                 (CASE qs.statement_end_offset WHEN -1 THEN DATALENGTH(st.text) ELSE qs.statement_end_offset END
                  - qs.statement_start_offset) / 2 + 1),
       tqp.query_plan
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
OUTER APPLY sys.dm_exec_text_query_plan(qs.plan_handle, qs.statement_start_offset, qs.statement_end_offset) tqp
WHERE (st.objectid = OBJECT_ID(%s) AND st.dbid = DB_ID()) OR (st.objectid IS NULL AND st.text LIKE %s)"""
# Los planes de la COPIA (sus procedimientos y sus lotes sueltos), para sacarlos de la caché uno por uno: la caché del
# original no se toca. La marca se arma por partes para que esta misma consulta no se encuentre a sí misma.
PLANES_DE_LA_COPIA = """SELECT DISTINCT CONVERT(varchar(130), cp.plan_handle, 1) FROM sys.dm_exec_cached_plans cp
CROSS APPLY sys.dm_exec_sql_text(cp.plan_handle) st
WHERE (st.dbid = DB_ID() AND OBJECT_SCHEMA_NAME(st.objectid, st.dbid) = N'estado')
   OR (st.objectid IS NULL AND st.text LIKE N'%%/* decant' + N':latentes:%%')"""
SACAR_PLAN = 'DECLARE @h varbinary(64) = CONVERT(varbinary(64), %s, 1); DBCC FREEPROCCACHE (@h) WITH NO_INFOMSGS;'
PARALELISMO = """SELECT (SELECT CAST(value_in_use AS int) FROM sys.configurations
        WHERE name = N'max degree of parallelism'),
       (SELECT CAST(value_in_use AS int) FROM sys.configurations WHERE name = N'cost threshold for parallelism'),
       (SELECT cpu_count FROM sys.dm_os_sys_info),
       (SELECT CAST(value AS int) FROM sys.database_scoped_configurations WHERE name = N'MAXDOP')"""

_OPERADOR = re.compile(r'<RelOp\b[^>]*\bPhysicalOp="([^"]+)"')
_ESTIMADAS = re.compile(r'<RelOp\b[^>]*\bEstimateRows="([^"]+)"')
_PARALELO = re.compile(r'<RelOp\b[^>]*\bParallel="(?:1|true)"')
_INDICE = re.compile(rf'Schema="\[{ESQUEMA}\]" Table="\[(\w+)\]" Index="\[(\w+)\]"')
_NESTED = re.compile(r'<NestedLoops\b([^>]*)>')
_COMPILADO = re.compile(r'\bParameterCompiledValue="([^"]*)"')
_NO_PARALELO = re.compile(r'\bNonParallelPlanReason="([^"]+)"')


def leer_showplan(xml: str | None) -> dict:
    """Lo que dice el showplan de la sentencia: sus operadores físicos en orden, los índices de la copia que recorre, si
    es paralelo, sus estimaciones, los atributos de sus Nested Loops (Optimized = orden por lotes de las búsquedas;
    WithUnorderedPrefetch) y el valor con el que se compiló. Se lee con expresiones (no se interpreta XML ajeno)."""
    if not xml:
        return {'operadores': [], 'indices': [], 'paralelo': None, 'estimaciones': [], 'nested_loops': [],
                'compilado_con': [], 'no_paralelo': None}
    razon = _NO_PARALELO.search(xml)
    return {'operadores': _OPERADOR.findall(xml), 'indices': sorted(set(f'{t}.{i}' for t, i in _INDICE.findall(xml))),
            'paralelo': bool(_PARALELO.search(xml)),
            'estimaciones': [round(float(e), 2) for e in _ESTIMADAS.findall(xml)],
            'nested_loops': [' '.join(a.split()) for a in _NESTED.findall(xml)],
            'compilado_con': _COMPILADO.findall(xml), 'no_paralelo': razon.group(1) if razon else None}


def huella_de_plan(query_plan_hash: str, showplan: dict) -> str:
    """La identidad del plan COMPILADO: su forma (query_plan_hash) y lo que la forma no dice y cambia lo que hace en la
    ejecución: las estimaciones (deciden el orden por lotes de un Nested Loops optimizado), los atributos de sus Nested
    Loops y el valor olfateado. Dos compilaciones con el mismo query_plan_hash y otras estimaciones son otro plan."""
    partes = [query_plan_hash, repr(showplan['estimaciones']), repr(showplan['nested_loops']),
              repr(showplan['compilado_con'])]
    return hashlib.sha256('|'.join(partes).encode('utf-8')).hexdigest()[:16]


def plan_de(filas: list[tuple], objeto: Objeto) -> dict:
    """El plan de la sentencia con la asignación (la que tiene la clave), de las filas de PLANES."""
    sentencias = [f for f in filas if objeto.clave in (f[5] or '')]
    if not sentencias:
        return {'visto': False, 'hashes': [], 'huellas': [], 'ejecuciones': 0, 'planes': 0}
    leidos = [(f, leer_showplan(f[6])) for f in sentencias]
    showplan = leidos[0][1]
    return {'visto': True, 'hashes': sorted({f[0] for f, _x in leidos}),
            'huellas': sorted({huella_de_plan(f[0], x) for f, x in leidos}),
            'ejecuciones': sum(int(f[1]) for f, _x in leidos),
            'last_dop': max(int(f[2] or 0) for f, _x in leidos), 'max_dop': max(int(f[3] or 0) for f, _x in leidos),
            'planes': len({f[4] for f, _x in leidos}), 'handles': sorted({f[4] for f, _x in leidos}),
            'sentencia': ' '.join((sentencias[0][5] or '').split())[:300], **showplan,
            '_xml': {f[0]: f[6] for f in sentencias if f[6]}}


def acceso(plan: dict) -> str:
    """El recorrido en una línea: operadores (sin los escalares), índices de la copia, estimación de la búsqueda, el
    orden por lotes si lo hay y el DOP de la última ejecución."""
    if not plan.get('visto'):
        return 'sin plan en la caché'
    ops = [o for o in plan['operadores'] if o not in ('Compute Scalar', 'Constant Scan', 'Concatenation',
                                                      'Merge Interval')]
    lotes = ' · orden por lotes (Nested Loops Optimized)' if any(
        'Optimized="1"' in n for n in plan['nested_loops']) else ''
    estimadas = max(plan['estimaciones'], default=0)
    return (f"{' · '.join(ops)} ({', '.join(plan['indices']) or 'sin índices de la copia'}){lotes}; "
            f"estimación {estimadas:g} filas; DOP {plan.get('last_dop')}")


def plan_cambio(plan: dict, base: dict) -> bool | None:
    """¿El plan compilado de la variante es otro que el de la base? None si alguno no se vio (no se puede afirmar)."""
    if not plan.get('visto') or not base.get('visto'):
        return None
    return set(plan['huellas']) != set(base['huellas'])


def que_cambio(plan: dict, base: dict) -> str | None:
    if not plan_cambio(plan, base):
        return None
    if set(plan['hashes']) != set(base['hashes']):
        return 'la forma (query_plan_hash)'
    return 'las estimaciones o el valor compilado (el mismo query_plan_hash)'


# ── la salida en forma comparable ───────────────────────────────────────────────────────────────────────────────

def canonico(valor):
    """Números por valor (la escala de un ROUND o de una resta es la de cada motor); fechas en ISO al milisegundo;
    el texto exacto (el relleno de un char(n) cuenta)."""
    if valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return '1' if valor else '0'
    if isinstance(valor, (int, float, Decimal)):
        try:
            return format(Decimal(str(valor)).normalize(), 'f')
        except InvalidOperation:
            return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat(sep=' ', timespec='milliseconds')
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def por_unidad(objeto: Objeto, filas) -> dict[tuple, tuple]:
    """(entrada, valor, columnas…) → {(entrada, unidad…): (columnas canónicas…)}. Una unidad repetida es un error."""
    nombres = [c for c, _t in objeto.salida]
    posiciones = [nombres.index(u) for u in objeto.unidad]
    resultado: dict[tuple, tuple] = {}
    for fila in filas:
        entrada, columnas = canonico(fila[0]), tuple(canonico(v) for v in fila[1:])
        llave = (entrada, *(columnas[p] for p in posiciones))
        if llave in resultado:
            raise NoSeCopia(f'{objeto.id}: la unidad {llave} sale dos veces')
        resultado[llave] = columnas
    return resultado


def comparar(objeto: Objeto, a: dict, b: dict, sobre: set | None = None) -> dict:
    """Unidades distintas entre dos salidas (sobre las entradas de `sobre`, si se da: la muestra). Una unidad que falta
    en un lado cuenta como distinta."""
    nombres = [c for c, _t in objeto.salida]
    llaves = {k for k in set(a) | set(b) if sobre is None or k[0] in sobre}
    distintas, columnas = [], Counter()
    for k in sorted(llaves, key=str):
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        distintas.append(k)
        if va is None or vb is None:
            columnas['(la unidad falta en un lado)'] += 1
        else:
            columnas[','.join(n for n, x, y in zip(nombres, va, vb) if x != y)] += 1
    return {'unidades': len(llaves), 'distintas': len(distintas), 'columnas': dict(columnas),
            'muestra': [{'unidad': list(k), 'a': dict(zip(nombres, a.get(k) or ())),
                         'b': dict(zip(nombres, b.get(k) or ()))} for k in distintas[:5]],
            '_llaves': distintas}


# ── árbitros: cada diferencia se AUDITA (ADR 0011) ──────────────────────────────────────────────────────────────

DEFECTO_LEGADO = 'defecto del legado (pendiente de decisión de negocio)'
DEFECTO_NUESTRO = 'defecto nuestro'


def arbitrar(objeto: Objeto, a: dict, b: dict, distintas: list[tuple], candidatos: dict[tuple, set]) -> dict:
    """Una diferencia se explica por la latente sólo si: las columnas distintas están entre las que alimentan las
    variables asignadas, y el valor de cada lado es el de OTRA fila del mismo grupo (`candidatos`: por entrada y unidad,
    los valores posibles de esas columnas en la copia). Lo que no se explica es defecto nuestro."""
    nombres = [c for c, _t in objeto.salida]
    alimenta = [nombres.index(c) for c in objeto.alimenta]
    explicadas, no = 0, []
    for k in distintas:
        va, vb = a.get(k), b.get(k)
        if va is None or vb is None:
            no.append(k)
            continue
        fuera = [n for n, x, y, i in zip(nombres, va, vb, range(len(nombres))) if x != y and i not in alimenta]
        posibles = candidatos.get(k, set())
        ok = (not fuera and _valor_de(objeto, va) in posibles and _valor_de(objeto, vb) in posibles
              and derivada_consistente(objeto, va) and derivada_consistente(objeto, vb))
        if ok:
            explicadas += 1
        else:
            no.append(k)
    return {'explicadas': explicadas, 'sin_explicar': len(no), 'muestra_sin_explicar': [list(k) for k in no[:5]],
            'clase': DEFECTO_LEGADO if not no else DEFECTO_NUESTRO}


def _valor_de(objeto: Objeto, fila: tuple) -> tuple:
    """Lo que la variable asignada tomó de su fila (sin lo que se deriva de ella: posicion_mxn sale de tc_cierre)."""
    nombres = [c for c, _t in objeto.salida]
    if objeto is R1_T1:
        return (fila[nombres.index('tc_cierre')],)
    return tuple(fila[nombres.index(c)] for c in objeto.alimenta)


def derivada_consistente(objeto: Objeto, fila: tuple) -> bool:
    """r1-T1: posicion_mxn = ROUND(posicion × tc_cierre, 2) en la misma fila (la derivada sigue a la variable). ROUND
    de SQL Server redondea la mitad hacia afuera del cero."""
    if objeto is not R1_T1:
        return True
    nombres = [c for c, _t in objeto.salida]
    pos, tc, mxn = (fila[nombres.index(c)] for c in ('posicion', 'tc_cierre', 'posicion_mxn'))
    if None in (pos, tc, mxn):
        return pos is None or tc is None
    return (Decimal(pos) * Decimal(tc)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) == Decimal(mxn)


CANDIDATOS_MS = {
    R1_T1.id: f'SELECT DISTINCT CAST(fecha_operacion AS date), moneda, tipo_cambio FROM {ESQUEMA}.operacion',
    R2_T2.id: (f'SELECT p.operacion_id, p.folio, p.uetr, p.estatus, p.fecha_envio FROM {ESQUEMA}.orden_pago p '
               f'WHERE p.operacion_id IN (SELECT operacion_id FROM {ESQUEMA}.orden_pago GROUP BY operacion_id '
               'HAVING COUNT(*) > 1)'),
}


def candidatos(objeto: Objeto, filas) -> dict[tuple, set]:
    """Por unidad, los valores que la variable asignada pudo tomar: los de TODAS las filas de su grupo en la copia."""
    resultado: dict[tuple, set] = {}
    for f in filas:
        if objeto is R1_T1:
            resultado.setdefault((canonico(f[0]), canonico(f[1])), set()).add((canonico(f[2]),))
        else:
            resultado.setdefault((canonico(f[0]),), set()).add(tuple(canonico(v) for v in f[1:]))
    return resultado


# ── el control del comparador por DATO (no por plan) ────────────────────────────────────────────────────────────
# Si ninguna variante del plan manifiesta la latente, falta saber si la comparación podría fallar. En la copia, dentro
# de una transacción revertida, la fila vigente deja de ser la de id mayor (lo que el catálogo dice que también la
# rompe): la copia tal cual y la copia con el parche del TO-BE tienen que diferir en TODAS las entradas tocadas. Es un
# dato, no un plan: no cuenta como detección de la latente.
CONTROL_DE_DATO = {
    R2_T2.id: ('la orden de id mayor de cada operación pasa a REEMPLAZADA y la anterior toma su estatus (la vigente '
               'deja de ser la última), en la copia y dentro de la transacción revertida',
               f"""WITH o AS (SELECT p.estatus, ROW_NUMBER() OVER (PARTITION BY p.operacion_id ORDER BY p.id DESC) AS n,
       FIRST_VALUE(p.estatus) OVER (PARTITION BY p.operacion_id ORDER BY p.id DESC) AS vigente
FROM {ESQUEMA}.orden_pago p WHERE p.operacion_id IN (SELECT valor FROM #entradas))
UPDATE o SET estatus = CASE n WHEN 1 THEN 'REEMPLAZADA' ELSE vigente END WHERE n IN (1, 2);"""),
}
CADA_CONTROL_DE_DATO = 100
RELOJ_DE_LA_COPIA = (f"DECLARE @r datetime = (SELECT MAX(fecha) FROM {ESQUEMA}.bitacora); "
                     "EXEC sp_set_session_context @key = N'decant.reloj', @value = @r;")


# ── el TO-BE: su consulta, para todas las entradas a la vez ─────────────────────────────────────────────────────

def tobe_para_todas(objeto: Objeto, consulta: str) -> str:
    """La consulta del TO-BE (`oraculo.TOBE`, por entrada) para un arreglo de entradas: el parámetro pasa a ser la
    columna de `unnest(%(entradas)s)`. Sólo reemplazos exactos; la prueba sin base y el CI (una muestra por entrada)
    comprueban que da lo mismo."""
    if objeto is R1_T1:
        if consulta.count('%(fecha)s') != 2:
            raise NoSeCopia('la consulta del TO-BE de la posición cambió: se esperaban 2 usos de %(fecha)s')
        return ('SELECT d.entrada, r.* FROM unnest(%(entradas)s::date[]) AS d(entrada) CROSS JOIN LATERAL ('
                + consulta.replace('%(fecha)s', 'd.entrada') + ') AS r ORDER BY d.entrada, r.moneda')
    viejo = 'FROM (SELECT 1) x '
    if consulta.count(viejo) != 1 or consulta.count('%(op)s') != 1 or not consulta.startswith('SELECT o.folio'):
        raise NoSeCopia('la consulta del TO-BE de la constancia cambió')
    return (consulta.replace('SELECT o.folio', 'SELECT x.entrada, o.folio', 1)
            .replace(viejo, 'FROM unnest(%(entradas)s::int[]) AS x(entrada) ')
            .replace('%(op)s', 'x.entrada') + ' ORDER BY x.entrada')


# Sólo para la corrida del TO-BE, dentro de una transacción que se revierte: los índices que el legado tiene y la base
# de referencia no (la base sólo lleva los únicos). No cambian el resultado del TO-BE (fija su orden); el CI lo prueba:
# la consulta por entrada SIN índice da lo mismo que la de todas las entradas CON índice.
INDICES_TOBE = ('CREATE INDEX ON legado.operacion (fecha_operacion)',
                'CREATE INDEX ON legado.orden_pago (operacion_id)')


# ── la aceptación ───────────────────────────────────────────────────────────────────────────────────────────────

def veredicto(objeto: Objeto, corridas: dict[str, dict], parche: dict[str, dict]) -> dict:
    """Por latente, con lo medido (`corridas[variante]` y `parche[variante]`, cada una con su plan, su comparación
    contra la copia tal cual y contra el TO-BE):
    - una variante MANIFIESTA la trampa si su plan REAL es otro que el de la copia tal cual y su salida también
      (el legado no coincide consigo mismo);
    - la latente queda DETECTADA si una variante natural la manifiesta y, con el parche del TO-BE, todas las variantes
      coinciden entre sí y con el TO-BE (falla con la trampa, pasa sin ella);
    - si sólo la manifiesta una variante forzada, queda «sólo forzada»; si ninguna, «no se manifiesta». En los dos
      casos NO cuenta como detectada.
    - control: una variante con el mismo plan no puede «detectar». La misma copia con su plan en la caché tiene que
      dar el mismo query_plan_hash, la misma entrada de la caché y 0 unidades distintas; una con el mismo plan y otra
      salida se reporta aparte (no determinista con el mismo plan), no como detección."""
    filas, naturales, forzadas, mismo_plan_distinto, no_aplican = [], [], [], [], []
    for v in VARIANTES[objeto.id]:
        c = corridas.get(v.id)
        if c is None:
            continue
        if c.get('no_compila'):
            no_aplican.append(v.id)
            filas.append({'variante': v.id, 'forzada': v.forzada, 'que': v.que, 'entradas': c['entradas'],
                          'cada': c['cada'], 'unidades': 0, 'plan_cambio': None, 'que_cambio': None,
                          'acceso': f'no aplica: el optimizador no puede cumplir la pista (error {NO_COMPILA})',
                          'hashes': [], 'contra_tal_cual': None, 'contra_tobe': None, 'columnas': {},
                          'arbitraje': None, 'segundos': c['segundos']})
            continue
        cambio = None if v is TAL_CUAL else c.get('plan_cambio')
        distinta = None if v is TAL_CUAL else c['contra_tal_cual']['distintas']
        if v is not TAL_CUAL and distinta:
            if cambio:
                (forzadas if v.forzada else naturales).append(v.id)
            else:
                mismo_plan_distinto.append(v.id)
        filas.append({'variante': v.id, 'forzada': v.forzada, 'que': v.que, 'entradas': c['entradas'],
                      'cada': c['cada'], 'unidades': c['contra_tobe']['unidades'], 'plan_cambio': cambio,
                      'que_cambio': c.get('que_cambio'), 'acceso': acceso(c['plan']),
                      'hashes': c['plan'].get('hashes', []),
                      'contra_tal_cual': distinta, 'contra_tobe': c['contra_tobe']['distintas'],
                      'columnas': (c['contra_tal_cual'] if v is not TAL_CUAL else c['contra_tobe'])['columnas'],
                      'arbitraje': c.get('arbitraje'), 'segundos': c['segundos']})
    otra = corridas.get(OTRA_VEZ.id)
    base = corridas.get(TAL_CUAL.id)
    mismo = bool(otra and base) and otra.get('plan_cambio') is False and \
        otra['plan'].get('handles') == base['plan'].get('handles') and otra['contra_tal_cual']['distintas'] == 0
    aplican = {k: p for k, p in parche.items() if not p.get('no_compila')}
    parche_ok = bool(aplican) and all(p['contra_tal_cual']['distintas'] == 0 and p['contra_tobe']['distintas'] == 0
                                      for p in aplican.values())
    controles = {
        'mismo_plan_no_detecta': {
            'que': 'la misma copia con su plan en la caché: el mismo query_plan_hash, la misma entrada de la caché y 0 '
                   'unidades distintas',
            'detectado': mismo,
            'variantes_con_el_mismo_plan': [f['variante'] for f in filas if f['plan_cambio'] is False],
            'con_el_mismo_plan_y_otra_salida': mismo_plan_distinto},
        'parche': {
            'que': 'con el parche del TO-BE en la copia: todas las variantes coinciden entre sí y con el TO-BE',
            'variantes': {k: {'contra_tal_cual': p['contra_tal_cual']['distintas'],
                              'contra_tobe': p['contra_tobe']['distintas'], 'acceso': acceso(p['plan']),
                              'plan_cambio': p.get('plan_cambio'), 'entradas': p['entradas'], 'cada': p['cada']}
                          for k, p in aplican.items()},
            'no_aplican': sorted(k for k, p in parche.items() if p.get('no_compila')),
            'detectado': parche_ok}}
    if naturales and parche_ok:
        estado = 'detectada con el plan variado'
    elif forzadas and parche_ok:
        estado = 'sólo forzada (pista en la copia)'
    elif naturales or forzadas:
        estado = 'no concluyente: con el parche las variantes no coinciden'
    else:
        estado = 'no se manifiesta'
    return {'objeto': objeto.id, 'que': objeto.que, 'estado': estado, 'detectada': bool(naturales) and parche_ok,
            'manifiestan': naturales, 'forzadas_que_manifiestan': forzadas, 'no_aplican': no_aplican,
            'tal_cual_contra_tobe': base['contra_tobe']['distintas'] if base else None,
            'plan_cambio_en': [f['variante'] for f in filas if f['plan_cambio']],
            'variantes': filas, 'controles': controles}


def faltas_de(objeto: Objeto, v: dict) -> list[str]:
    """Lo que deja el job en rojo: un control que no se cumple, una diferencia sin explicar (defecto nuestro) o una
    medición vacía (ninguna variante cambió el plan: no se midió nada). Que la latente no se manifieste NO es una
    falta: se reporta con sus cifras."""
    faltas = []
    for nombre, c in v['controles'].items():
        if not c['detectado']:
            faltas.append(f"{objeto.id}: el control «{nombre}» no se cumple ({c['que']})")
    if v['controles']['mismo_plan_no_detecta']['con_el_mismo_plan_y_otra_salida']:
        faltas.append(f"{objeto.id}: con el mismo plan la salida cambió en "
                      f"{v['controles']['mismo_plan_no_detecta']['con_el_mismo_plan_y_otra_salida']}: no es del plan")
    for f in v['variantes']:
        a = f.get('arbitraje') or {}
        for lado, x in a.items():
            if x and x['sin_explicar']:
                faltas.append(f"{objeto.id} · {f['variante']}: {x['sin_explicar']:,} unidades distintas {lado} sin "
                              f"explicar (defecto nuestro): {x['muestra_sin_explicar']}")
    if not v['plan_cambio_en']:
        faltas.append(f'{objeto.id}: ninguna variante cambió el plan; la medición no dice nada')
    return faltas
