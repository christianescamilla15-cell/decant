"""Oráculo capturado EN el corte (S3 paso 5, ADR 0014; criterio 2 del plan): la salida de cada objeto de LECTURA del
legado (procedimientos de lectura, vistas y la pantalla) con parámetros representativos, incluido el borde del cierre
de mes, y el instante del servidor al correrla. El TO-BE la re-corre sobre la base de referencia del congelamiento (la
base cerrada con el delta del paso 4) con ESE reloj inyectado.

- **Captura:** dentro del legado vivo, en el congelamiento (después de la foto y antes de lo posterior), cuando lo
  pide `DECANT_ORACULO=1` (`legado/vivo`). Sólo en el job del corte: el job `legado`, que observa el ciclo para la
  puerta, no lo enciende; lo que ejecuta el arnés no es un consumidor.
- **Comparación por caso:** cada conjunto de resultados como multiconjunto de filas (los empates y el orden que no es
  contrato no cuentan); los decimales por valor (la escala de un ROUND es la de cada motor). Además:
  - **orden prometido:** si el objeto (o la vista que lee) promete un ORDER BY, se cuentan los pares contiguos que lo
    incumplen, en el legado y en el TO-BE. Un legado que incumple lo que promete es un defecto del legado;
  - **reloj:** el TO-BE corre con el instante del servidor del oráculo y con su reloj PROPIO (el de negocio del
    congelamiento). Si con el propio no coincide, el objeto depende del reloj: un TO-BE que no lo inyecte falla, con
    nombre;
  - **SQL copiado tal cual:** donde los dos motores calculan distinto el mismo texto, se re-corre también la copia
    literal en PostgreSQL. Si difiere, el TO-BE tiene que replicar al legado (o negocio decide corregirlo).
- **N de N:** todo objeto de lectura del inventario tiene al menos un caso; si no, el oráculo falla nombrándolo.
"""
from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

PANTALLA = 'pantalla:legado/pantalla'
MUESTRA = 5


@dataclass(frozen=True)
class Caso:
    objeto: str
    nombre: str
    legado: str                              # la llamada al legado (literal, con %(parámetro)s)
    argumentos: dict = field(default_factory=dict)   # valor literal o '$representativo'
    borde: bool = False                      # el borde del cierre de mes
    orden: tuple = ()                        # ((columna, 'asc'|'desc'), …) prometido por el objeto o su vista
    de_donde: str = ''                       # de dónde sale el orden prometido

    @property
    def id(self) -> str:
        return f'{self.objeto} · {self.nombre}'


# Parámetros representativos que salen de los DATOS en el congelamiento (sólo lectura).
REPRESENTATIVOS = {
    'op_reregistrada': 'SELECT MAX(operacion_id) FROM (SELECT operacion_id FROM dbo.orden_pago '
                       'GROUP BY operacion_id HAVING COUNT(*) > 1) x',
    'op_sin_orden': 'SELECT MAX(o.id) FROM dbo.operacion o WHERE NOT EXISTS '
                    '(SELECT 1 FROM dbo.orden_pago p WHERE p.operacion_id = o.id)',
    'op_reciente': 'SELECT MAX(id) FROM dbo.operacion',
    'bic_enviadas': "SELECT TOP 1 bic_corresponsal FROM dbo.orden_pago WHERE estatus = 'ENVIADA' "
                    'GROUP BY bic_corresponsal ORDER BY COUNT(*) DESC, bic_corresponsal',
}

_LIQ = ('folio', 'uetr', 'bic_corresponsal', 'moneda', 'monto', 'fecha_hora', 'referencia')
_REP = ('folio', 'uetr', 'referencia_mt103', 'fecha_envio', 'fecha_valor', 'bic_corresponsal', 'beneficiario',
        'moneda', 'monto', 'gastos', 'estatus', 'concepto', 'monto_partida', 'fecha_partida')
_VISTA_LIQ = 'ORDER BY s.fecha_hora DESC de dbo.vw_liquidaciones_recientes (TOP 100 PERCENT)'

CASOS = (
    Caso('dbo.sp_antiguedad_ordenes', 'por omisión (3 días)', 'EXEC dbo.sp_antiguedad_ordenes @dias = %(dias)s',
         {'dias': 3, 'bic': None}, orden=(('fecha_envio', 'asc'), ('folio', 'asc')),
         de_donde='ORDER BY fecha_envio, folio'),
    Caso('dbo.sp_antiguedad_ordenes', 'un corresponsal', 'EXEC dbo.sp_antiguedad_ordenes @dias = %(dias)s, '
         '@bic_corresponsal = %(bic)s', {'dias': 3, 'bic': '$bic_enviadas'},
         orden=(('fecha_envio', 'asc'), ('folio', 'asc')), de_donde='ORDER BY fecha_envio, folio'),
    Caso('dbo.sp_ordenes_por_vencer', 'sin parámetros', 'EXEC dbo.sp_ordenes_por_vencer',
         orden=(('fecha_envio', 'asc'), ('folio', 'asc')), de_donde='ORDER BY fecha_envio, folio'),
    Caso('dbo.sp_constancia_operacion', 'operación re-registrada',
         'EXEC dbo.sp_constancia_operacion @operacion_id = %(op)s', {'op': '$op_reregistrada'}),
    Caso('dbo.sp_constancia_operacion', 'operación sin orden',
         'EXEC dbo.sp_constancia_operacion @operacion_id = %(op)s', {'op': '$op_sin_orden'}),
    Caso('dbo.sp_detalle_operacion', 'operación re-registrada',
         'EXEC dbo.sp_detalle_operacion @operacion_id = %(op)s', {'op': '$op_reregistrada'}),
    Caso('dbo.sp_detalle_operacion', 'la más reciente (del delta)',
         'EXEC dbo.sp_detalle_operacion @operacion_id = %(op)s', {'op': '$op_reciente'}),
    Caso('dbo.sp_liquidaciones_recientes', 'desde el inicio del mes', 'EXEC dbo.sp_liquidaciones_recientes '
         '@desde = %(desde)s', {'desde': '$inicio_mes'}, borde=True, orden=(('fecha_hora', 'desc'),),
         de_donde=_VISTA_LIQ),
    Caso('dbo.sp_liquidaciones_recientes', 'desde el día del corte', 'EXEC dbo.sp_liquidaciones_recientes '
         '@desde = %(desde)s', {'desde': '$dia_corte'}, orden=(('fecha_hora', 'desc'),), de_donde=_VISTA_LIQ),
    Caso('dbo.sp_lista_operaciones', 'el día (por omisión)', 'EXEC dbo.sp_lista_operaciones', {'fecha': None,
                                                                                               'maximo': 200}),
    Caso('dbo.sp_lista_operaciones', 'último día del mes anterior', 'EXEC dbo.sp_lista_operaciones @fecha = %(fecha)s',
         {'fecha': '$fin_mes_anterior', 'maximo': 200}, borde=True),
    Caso('dbo.sp_reporte_ordenes', 'el mes del corte', 'EXEC dbo.sp_reporte_ordenes @desde = %(desde)s, '
         '@hasta = %(hasta)s', {'desde': '$inicio_mes', 'hasta': '$dia_corte'},
         orden=(('fecha_valor', 'asc'),), de_donde='ORDER BY fecha_valor'),
    Caso('dbo.sp_reporte_ordenes', 'cruce del cierre de mes', 'EXEC dbo.sp_reporte_ordenes @desde = %(desde)s, '
         '@hasta = %(hasta)s', {'desde': '$fin_mes_anterior', 'hasta': '$inicio_mes'}, borde=True,
         orden=(('fecha_valor', 'asc'),), de_donde='ORDER BY fecha_valor'),
    Caso('dbo.sp_reporte_posicion', 'el día del corte', 'EXEC dbo.sp_reporte_posicion @fecha = %(fecha)s',
         {'fecha': '$dia_corte'}, orden=(('moneda', 'asc'),), de_donde='ORDER BY p.moneda'),
    Caso('dbo.sp_reporte_posicion', 'último día del mes anterior', 'EXEC dbo.sp_reporte_posicion @fecha = %(fecha)s',
         {'fecha': '$fin_mes_anterior'}, borde=True, orden=(('moneda', 'asc'),), de_donde='ORDER BY p.moneda'),
    Caso('dbo.sp_tablero_corresponsales', 'el mes cerrado anterior', 'EXEC dbo.sp_tablero_corresponsales '
         '@desde = %(desde)s, @hasta = %(hasta)s', {'desde': '$inicio_mes_anterior', 'hasta': '$fin_mes_anterior'},
         borde=True, orden=(('bic_corresponsal', 'asc'),), de_donde='ORDER BY p.bic_corresponsal'),
    Caso('dbo.sp_tablero_corresponsales', 'el mes del corte', 'EXEC dbo.sp_tablero_corresponsales '
         '@desde = %(desde)s, @hasta = %(hasta)s', {'desde': '$inicio_mes', 'hasta': '$dia_corte'},
         orden=(('bic_corresponsal', 'asc'),), de_donde='ORDER BY p.bic_corresponsal'),
    Caso('dbo.vw_liquidaciones_recientes', 'lectura directa desde el inicio del mes',
         f"SELECT {', '.join(_LIQ)} FROM dbo.vw_liquidaciones_recientes WHERE fecha_hora >= %(desde)s",
         {'desde': '$inicio_mes'}, borde=True, orden=(('fecha_hora', 'desc'),), de_donde=_VISTA_LIQ),
    Caso('dbo.vw_reporte_ordenes', 'lectura directa del cruce del cierre de mes',
         f"SELECT id, {', '.join(_REP)} FROM dbo.vw_reporte_ordenes WHERE fecha_valor BETWEEN %(desde)s AND %(hasta)s",
         {'desde': '$fin_mes_anterior', 'hasta': '$inicio_mes'}, borde=True),
)
# La pantalla: un caso (lista del día y el detalle de una operación re-registrada), lo que permite «Si aprieta».
CASOS_PANTALLA = (
    Caso(PANTALLA, 'lista del día', '/', {'fecha': None, 'maximo': 200}),
    Caso(PANTALLA, 'detalle de una operación re-registrada', '/operacion/%(op)s', {'op': '$op_reregistrada'}),
)


def todos() -> tuple[Caso, ...]:
    return CASOS + CASOS_PANTALLA


def n_de_n(lectores: list[str]) -> dict:
    """Cada objeto de lectura del inventario tiene al menos un caso."""
    con = {c.objeto for c in todos()}
    faltan = sorted(o for o in lectores if o not in con)
    return {'lectores': len(lectores), 'con_caso': len(lectores) - len(faltan), 'faltan': faltan,
            'faltas': [f'{o}: objeto de lectura sin caso en el oráculo' for o in faltan], 'verde': not faltan}


# ── la forma de los valores ─────────────────────────────────────────────────────────────────────────────────────

def texto(valor) -> str | None:
    if valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return '1' if valor else '0'
    if isinstance(valor, Decimal):
        return format(valor, 'f')
    if isinstance(valor, datetime):
        return valor.isoformat(sep=' ', timespec='milliseconds')
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


def clase(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return 'bit'
    if isinstance(valor, (int, Decimal, float)):
        return 'numero'
    if isinstance(valor, (datetime, date)):
        return 'fecha'
    return 'texto'


def conjunto(columnas: list[str], filas: list[tuple]) -> dict:
    """Un conjunto de resultados en forma comparable: columnas, la clase de cada una y las filas como texto."""
    clases = []
    for i in range(len(columnas)):
        clases.append(next((clase(f[i]) for f in filas if f[i] is not None), None))
    return {'columnas': [c.lower() for c in columnas], 'clases': clases,
            'filas': [[texto(v) for v in f] for f in filas]}


def _normal(v: str | None, k: str | None):
    if v is None or k != 'numero':
        return v
    try:
        return format(Decimal(v).normalize(), 'f')
    except InvalidOperation:
        return v


def _filas(c: dict, clases: list) -> Counter:
    return Counter(tuple(_normal(v, k) for v, k in zip(f, clases)) for f in c['filas'])


def comparar_conjunto(legado: dict, tobe: dict) -> dict:
    """Dos conjuntos como multiconjuntos de filas. Los números por valor; lo demás, texto exacto (el relleno de un
    char(n), las mayúsculas y los espacios finales cuentan)."""
    if legado['columnas'] != tobe['columnas']:
        return {'coincide': False, 'columnas': {'legado': legado['columnas'], 'tobe': tobe['columnas']},
                'filas_legado': len(legado['filas']), 'filas_tobe': len(tobe['filas'])}
    clases = [a or b for a, b in zip(legado['clases'], tobe['clases'])]
    a, b = _filas(legado, clases), _filas(tobe, clases)
    faltan, sobran = a - b, b - a
    return {'coincide': not faltan and not sobran, 'filas_legado': sum(a.values()), 'filas_tobe': sum(b.values()),
            'solo_legado': sum(faltan.values()), 'solo_tobe': sum(sobran.values()),
            'muestra_solo_legado': [list(f) for f in list(faltan.elements())[:MUESTRA]],
            'muestra_solo_tobe': [list(f) for f in list(sobran.elements())[:MUESTRA]]}


def comparar_conjuntos(legado: list[dict], tobe: list[dict]) -> dict:
    if len(legado) != len(tobe):
        return {'coincide': False, 'conjuntos': {'legado': len(legado), 'tobe': len(tobe)}}
    partes = [comparar_conjunto(a, b) for a, b in zip(legado, tobe)]
    return {'coincide': all(p['coincide'] for p in partes), 'conjuntos': partes}


def _clave_de_orden(v: str | None, k: str | None):
    if v is None:
        return (0, '')
    if k == 'numero':
        return (1, Decimal(v))
    return (1, v.casefold() if k == 'texto' else v)


def orden_incumplido(c: dict, orden: tuple) -> dict:
    """Pares contiguos que incumplen el orden prometido (los empates no cuentan)."""
    if not orden:
        return {'pares': 0, 'incumplidos': 0}
    posiciones = [(c['columnas'].index(col), d) for col, d in orden]
    incumplidos, primero = 0, None
    for i in range(1, len(c['filas'])):
        a, b = c['filas'][i - 1], c['filas'][i]
        for p, d in posiciones:
            x, y = _clave_de_orden(a[p], c['clases'][p]), _clave_de_orden(b[p], c['clases'][p])
            if x == y:
                continue
            if (x > y) if d == 'asc' else (x < y):
                incumplidos += 1
                if primero is None:
                    primero = {'par': i, 'antes': a, 'despues': b}
            break
    return {'pares': max(len(c['filas']) - 1, 0), 'incumplidos': incumplidos, 'primero': primero}


# ── la captura (legado vivo, en el congelamiento) ───────────────────────────────────────────────────────────────

def instante_servidor(cursor) -> str:
    cursor.execute('SELECT CONVERT(varchar(23), GETDATE(), 121)')
    return cursor.fetchone()[0]


def fechas(guion: dict) -> dict:
    """Las fechas representativas: el día del corte, su mes y el mes anterior (el borde del cierre)."""
    dia = date.fromisoformat(guion['fecha_negocio'])
    inicio = dia.replace(day=1)
    fin_anterior = inicio - timedelta(days=1)
    return {'dia_corte': dia.isoformat(), 'inicio_mes': inicio.isoformat(),
            'fin_mes_anterior': fin_anterior.isoformat(),
            'inicio_mes_anterior': fin_anterior.replace(day=1).isoformat()}


def parametros(cursor, guion: dict) -> dict:
    resultado = fechas(guion)
    for nombre, consulta in REPRESENTATIVOS.items():
        cursor.execute(consulta)
        valor = cursor.fetchone()[0]
        resultado[nombre] = valor if not isinstance(valor, Decimal) else int(valor)
    return resultado


def argumentos(caso: Caso, p: dict) -> dict:
    return {k: (p[v[1:]] if isinstance(v, str) and v.startswith('$') else v) for k, v in caso.argumentos.items()}


def leer_conjuntos(cursor) -> list[dict]:
    resultado = []
    while True:
        if cursor.description:
            resultado.append(conjunto([d[0] for d in cursor.description], cursor.fetchall()))
        if not cursor.nextset():
            return resultado


def capturar(cursor, guion: dict, pantalla: str | None) -> dict:
    """El oráculo en el congelamiento: cada caso con el instante del servidor justo antes de correrlo."""
    t0 = time.monotonic()
    p = parametros(cursor, guion)
    al_empezar = instante_servidor(cursor)
    casos = []
    for caso in CASOS:
        args = argumentos(caso, p)
        servidor = instante_servidor(cursor)
        cursor.execute(caso.legado, args)
        casos.append({'id': caso.id, 'objeto': caso.objeto, 'argumentos': args, 'servidor': servidor,
                      'conjuntos': leer_conjuntos(cursor)})
    if pantalla:
        for caso in CASOS_PANTALLA:
            args = argumentos(caso, p)
            servidor = instante_servidor(cursor)
            casos.append({'id': caso.id, 'objeto': caso.objeto, 'argumentos': args, 'servidor': servidor,
                          'conjuntos': leer_pantalla(pantalla, caso.legado % args)})
    return {'version': 1, 'que_es': 'oráculo del corte: la salida de cada objeto de lectura en el congelamiento, con '
                                    'el instante del servidor (corte/oraculo.py)',
            'fecha_negocio': guion['fecha_negocio'], 'congelamiento_utc': guion['congelamiento_utc'],
            'parametros': p, 'servidor_al_empezar': al_empezar, 'servidor_al_terminar': instante_servidor(cursor),
            'casos': casos, 'segundos': round(time.monotonic() - t0, 1)}


_TOTALES = re.compile(r'data-total-(operaciones|ordenes)="(\d+)"')


def leer_pantalla(url: str, ruta: str) -> list[dict]:
    """Lo que la pantalla muestra, como conjuntos de texto: los totales del encabezado (lista) y cada tabla."""
    from legado.extraer_pantalla import _get
    return pantalla_en_conjuntos(_get(url, ruta))


def pantalla_en_conjuntos(html: str) -> list[dict]:
    from legado.extraer_pantalla import _Tablas
    p = _Tablas()
    p.feed(html)
    resultado = []
    totales = _TOTALES.findall(html)
    if totales:
        resultado.append({'columnas': [f'total_{n}' for n, _v in totales], 'clases': ['numero'] * len(totales),
                          'filas': [[v for _n, v in totales]]})
    for t in p.tablas:
        renglones = t['renglones']
        if t['id'] is None and renglones and all(len(r) == 2 for r in renglones) and not totales:
            resultado.append({'columnas': ['campo', 'valor'], 'clases': ['texto', 'texto'],
                              'filas': [list(r) for r in renglones]})
            continue
        titulos, *filas = renglones
        resultado.append({'columnas': [x.lower() for x in titulos], 'clases': ['texto'] * len(titulos),
                          'filas': [list(f) for f in filas]})
    return resultado


def escribir(oraculo: dict, ruta: Path) -> None:
    ruta.write_text(json.dumps(oraculo, ensure_ascii=False, indent=1, default=str) + '\n', encoding='utf-8')


# ── el TO-BE: la re-corrida sobre la base de referencia del congelamiento (PostgreSQL, esquema `legado`) ──────────
# Cada objeto, con los parches del TO-BE: el reloj ENTRA (%(reloj)s), la orden vigente se elige explícitamente, el
# orden prometido va en la consulta final y, mientras negocio no decida (ADR 0006), se replica el truncado del legado.
# `literal`: el mismo texto del legado copiado a PostgreSQL, donde los motores calculan distinto (control de r2-T3).

_MINUTOS = ("(extract(epoch FROM date_trunc('minute', p.fecha_envio) - date_trunc('minute', o.fecha_operacion))"
            ' / 60)::bigint')
_VIGENTE = ("(SELECT id FROM legado.orden_pago WHERE operacion_id = %(op)s AND estatus <> 'REEMPLAZADA' "
            'ORDER BY id DESC LIMIT 1)')
_DIA_LISTA = "coalesce(%(fecha)s::date, (SELECT max(fecha_operacion)::date FROM legado.operacion))"
_TABLERO = ("SELECT p.bic_corresponsal, count(*)::int AS ordenes, "
            "(sum(CASE WHEN p.estatus = 'CONCILIADA' THEN 1 ELSE 0 END) * 100 / count(*))::int AS pct_conciliadas, "
            "{horas} AS horas_promedio_envio "
            'FROM legado.orden_pago p JOIN legado.operacion o ON o.id = p.operacion_id '
            "WHERE p.estatus <> 'REEMPLAZADA' AND p.fecha_envio >= %(desde)s::date "
            'AND p.fecha_envio < %(hasta)s::date + 1 GROUP BY p.bic_corresponsal ORDER BY p.bic_corresponsal')
_LIQUIDACIONES = ('SELECT p.folio, p.uetr, p.bic_corresponsal, p.moneda, s.monto, s.fecha_hora, s.referencia '
                  'FROM legado.partida_solicitada s JOIN legado.orden_pago p ON p.id = s.orden_id '
                  "WHERE s.concepto = 'ABONO' AND s.fecha_hora >= %(desde)s::timestamp "
                  'ORDER BY s.fecha_hora DESC, p.folio')
_REPORTE = ('SELECT {id}o.folio, o.uetr, o.referencia_mt103, o.fecha_envio, o.fecha_valor, o.bic_corresponsal, '
            'o.beneficiario, o.moneda, o.monto, o.gastos, o.estatus, p.concepto, p.monto AS monto_partida, '
            'p.fecha_hora AS fecha_partida FROM legado.orden_pago o '
            'JOIN legado.partida_solicitada p ON p.orden_id = o.id '
            "WHERE o.estatus <> 'REEMPLAZADA' AND o.fecha_valor BETWEEN %(desde)s::date AND %(hasta)s::date "
            'ORDER BY o.fecha_valor, o.folio, p.renglon')
_LISTA = ('SELECT id, folio, fecha_operacion, sucursal, canal, cliente, tipo, moneda, monto_divisa, tipo_cambio, '
          f'monto_mxn, estatus FROM legado.operacion WHERE fecha_operacion >= {_DIA_LISTA} '
          f"AND fecha_operacion < {_DIA_LISTA} + 1 ORDER BY fecha_operacion, id")
_DETALLE = (
    'SELECT o.id, o.folio, o.fecha_operacion, o.sucursal, o.canal, o.cliente, o.cuenta_clabe, o.tipo, o.moneda, '
    'm.nombre AS nombre_moneda, m.decimales, o.monto_divisa, o.tipo_cambio, o.tipo_cambio_referencia, o.monto_mxn, '
    'o.estatus, p.id AS orden_id, p.folio AS folio_orden, p.uetr, p.referencia_mt103, p.fecha_registro, '
    'p.fecha_envio, p.fecha_valor, p.bic_corresponsal, p.bic_intermediario, p.beneficiario, p.cuenta_beneficiario, '
    'p.monto AS monto_orden, p.gastos, p.estatus AS estatus_orden, p.horas_liquidacion '
    'FROM legado.operacion o LEFT JOIN legado.moneda m ON m.codigo = o.moneda '
    f'LEFT JOIN legado.orden_pago p ON p.id = {_VIGENTE} WHERE o.id = %(op)s',
    'SELECT renglon, concepto, moneda, monto, fecha_hora, referencia FROM legado.partida_solicitada '
    f'WHERE orden_id = {_VIGENTE} ORDER BY renglon',
    'SELECT renglon, concepto, moneda, monto, fecha_hora, referencia FROM legado.partida_liquidada '
    f'WHERE orden_id = {_VIGENTE} ORDER BY renglon')

TOBE: dict[str, tuple[str, ...]] = {
    'dbo.sp_antiguedad_ordenes': (
        'SELECT folio, uetr, bic_corresponsal, moneda, monto, fecha_envio FROM legado.orden_pago '
        "WHERE estatus = 'ENVIADA' AND fecha_envio < %(reloj)s::timestamp - make_interval(days => %(dias)s::int) "
        'AND (%(bic)s::text IS NULL OR bic_corresponsal = %(bic)s::char(11)) ORDER BY fecha_envio, folio',),
    'dbo.sp_ordenes_por_vencer': (
        'SELECT folio, uetr, fecha_envio, bic_corresponsal, beneficiario, moneda, monto, '
        "CASE WHEN fecha_envio < %(reloj)s::timestamp - interval '3 days' THEN 'VENCE HOY' ELSE 'VENCE MANANA' END "
        "AS aviso FROM legado.orden_pago WHERE estatus = 'ENVIADA' "
        "AND fecha_envio < %(reloj)s::timestamp - interval '2 days' ORDER BY fecha_envio, folio",),
    'dbo.sp_constancia_operacion': (
        'SELECT o.folio, o.cliente, o.moneda, o.monto_divisa, o.monto_mxn, p.folio AS folio_orden, p.uetr, '
        'p.estatus AS estatus_orden, p.fecha_envio FROM (SELECT 1) x '
        'LEFT JOIN legado.operacion o ON o.id = %(op)s '
        'LEFT JOIN LATERAL (SELECT q.folio, q.uetr, q.estatus, q.fecha_envio FROM legado.orden_pago q '
        "WHERE q.operacion_id = o.id AND q.estatus <> 'REEMPLAZADA' ORDER BY q.id DESC LIMIT 1) p ON true",),
    'dbo.sp_detalle_operacion': _DETALLE,
    'dbo.sp_liquidaciones_recientes': (_LIQUIDACIONES,),
    'dbo.sp_lista_operaciones': (
        'SELECT count(*)::int AS total_operaciones, '
        '(SELECT count(DISTINCT uetr) FROM legado.orden_pago)::int AS total_ordenes FROM legado.operacion',
        _LISTA + ' LIMIT %(maximo)s'),
    'dbo.sp_reporte_ordenes': (_REPORTE.format(id=''),),
    'dbo.sp_reporte_posicion': (
        'WITH dia AS (SELECT * FROM legado.operacion WHERE fecha_operacion >= %(fecha)s::date '
        'AND fecha_operacion < %(fecha)s::date + 1), '
        "pos AS (SELECT moneda, sum(CASE WHEN tipo = 'C' THEN monto_divisa ELSE 0 END)::numeric(18, 2) AS compras, "
        "sum(CASE WHEN tipo = 'V' THEN monto_divisa ELSE 0 END)::numeric(18, 2) AS ventas FROM dia GROUP BY moneda), "
        'cierre AS (SELECT DISTINCT ON (moneda) moneda, tipo_cambio FROM dia '
        'ORDER BY moneda, fecha_operacion DESC, id DESC) '
        'SELECT p.moneda, m.nombre, p.compras, p.ventas, p.compras - p.ventas AS posicion, '
        'c.tipo_cambio AS tc_cierre, round((p.compras - p.ventas) * c.tipo_cambio, 2) AS posicion_mxn FROM pos p '
        'LEFT JOIN cierre c ON c.moneda = p.moneda LEFT JOIN legado.moneda m ON m.codigo = p.moneda '
        'ORDER BY p.moneda',),
    'dbo.sp_tablero_corresponsales': (_TABLERO.format(horas=f'(trunc(avg({_MINUTOS}))::bigint / 60)::int'),),
    'dbo.vw_liquidaciones_recientes': (_LIQUIDACIONES,),
    'dbo.vw_reporte_ordenes': (_REPORTE.format(id='o.id, '),),
}
# El SQL del legado copiado tal cual: AVG de un entero en PostgreSQL es numeric (no trunca).
LITERAL: dict[str, tuple[str, ...]] = {
    'dbo.sp_tablero_corresponsales': (_TABLERO.format(horas=f'avg({_MINUTOS}) / 60'),),
}


def correr_tobe(pg, consultas: tuple[str, ...], args: dict, reloj: datetime) -> list[dict]:
    resultado = []
    for consulta in consultas:
        cursor = pg.execute(consulta, {**args, 'reloj': reloj})
        resultado.append(conjunto([d.name for d in cursor.description], cursor.fetchall()))
    return resultado


def pantalla_tobe(pg, caso: Caso, args: dict, reloj: datetime) -> list[dict]:
    """La pantalla con los datos del TO-BE: las mismas rejillas y los mismos encabezados que pinta el legado (su
    binding, `legado/pantalla/app.py`), para comparar lo que ve el usuario."""
    from legado.pantalla import app
    if caso.legado == '/':
        total, filas = correr_tobe_crudo(pg, TOBE['dbo.sp_lista_operaciones'], args, reloj)
        n, ordenes = total[0]['total_operaciones'], total[0]['total_ordenes']

        def celda(fila: dict, columna: str) -> str:
            if columna == 'folio':
                return f'<a href="/operacion/{int(fila["id"])}">{app._e(fila["folio"])}</a>'
            return app._e(fila.get(columna))
        cuerpo = (f'<p class="total" data-total-operaciones="{int(n)}">x</p>'
                  f'<p class="total" data-total-ordenes="{int(ordenes)}">x</p>'
                  f'{app._tabla(filas, app.COLUMNAS_LISTA, celda=celda)}')
        return pantalla_en_conjuntos(cuerpo)
    encabezado, solicitada, liquidada = correr_tobe_crudo(pg, TOBE['dbo.sp_detalle_operacion'], args, reloj)
    conjuntos = {1: solicitada, 2: liquidada}
    cuerpo = '<table>' + ''.join(f'<tr><th>{app._e(k)}</th><td>{app._e(v)}</td></tr>'
                                 for k, v in encabezado[0].items()) + '</table>'
    for rejilla in app.REJILLAS:
        cuerpo += app._tabla(conjuntos[rejilla['conjunto']], app.COLUMNAS_PARTIDA, rejilla['id'])
    return pantalla_en_conjuntos(cuerpo)


def correr_tobe_crudo(pg, consultas: tuple[str, ...], args: dict, reloj: datetime) -> list[list[dict]]:
    resultado = []
    for consulta in consultas:
        cursor = pg.execute(consulta, {**args, 'reloj': reloj})
        nombres = [d.name for d in cursor.description]
        resultado.append([dict(zip(nombres, f)) for f in cursor.fetchall()])
    return resultado
