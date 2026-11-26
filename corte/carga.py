"""Carga histórica POR MES del corte (S3 paso 3, ADR 0013, criterios 4, 5, 6 y 12). Sin base: aquí están la
especificación de las 7 tablas, el plan por mes, la huella de un mes, la reversa y las guardas; la lectura y la
escritura las hace `corte/runbook.py`.

- **Destino:** las 7 tablas del legado copiadas fila por fila CON sus ids y sus valores CRUDOS al esquema `legado`
  de PostgreSQL (`corte/destino.sql`): `char(n)` con su relleno, los centinelas tal cual, las horas locales sin zona.
  Los parches del ADR 0007 se aplican después, de `legado` al TO-BE (como ya los aplica y mide S2): si se aplicaran al
  cargar, la huella del mes no podría ser igual en los dos lados.
- **Partición:** cada mes es un rango CONTIGUO de ids por tabla. El mes de una fila sale de su SELLO (la hora local
  con la que el legado la escribió); el plan agrupa por ese mes en el origen y comprueba que los rangos no se
  enciman: si una fila de un mes cayera entre las de otro, no hay plan y el corte no avanza.
- **Sólo INSERT y sólo ids > corte:** el corte de un mes es lo que el destino ya tiene, medido por dos caminos
  (`MAX(id)` en el destino y el registro de meses aplicados). El mes sólo inserta ids mayores y, al terminar, las
  filas con id ≤ ese corte son las mismas, con la misma huella.
- **Huella del mes:** por tabla, sha256 de las líneas `id|huella de la fila` (la forma canónica de
  `corte/cifras.py`). En el origen se toman las filas por su SELLO (el mes de verdad); en el destino, por el RANGO
  del plan. Si el plan partiera mal el mes (la grieta UTC), los dos lados no cuadran.
- **Reversa:** se GENERA antes de aplicar: los rangos de ids, el valor previo de cada secuencia y del consumible, y la
  huella previa del destino (las 7 tablas, las secuencias y los folios).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from corte import cifras
from paridad.zonas import CDMX

MESES = tuple(f'{a}-{m:02d}' for a in (2021, 2022, 2023) for m in range(1, 13))
# Los del PR: el primero, el de la grieta y el último. La grieta va en octubre de 2022: es el mes cuya última noche
# mueve más filas al pasar a UTC (682, medido sobre el generador) y el del último cambio de horario de la Ciudad de
# México (30-oct-2022).
GRIETA = '2022-10'
MESES_PR = ('2021-01', GRIETA, '2023-12')
MUESTRA = 20


# ── las 7 tablas ────────────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Columna:
    nombre: str
    tipo: str                    # el del legado, como está en legado/sql/02_tablas.sql
    nula: bool                   # en el legado (y en el destino: es la misma columna)


@dataclass(frozen=True)
class Tabla:
    nombre: str                  # sin esquema: operacion
    columnas: tuple[Columna, ...]
    identidad: bool
    sello: str = ''              # qué hora decide el mes de la fila (sólo las que tienen identidad)
    monto: str | None = None     # la columna que suman los totales del plan

    @property
    def origen(self) -> str:
        return f'dbo.{self.nombre}'

    @property
    def destino(self) -> str:
        return f'legado.{self.nombre}'

    @property
    def nombres(self) -> tuple[str, ...]:
        return tuple(c.nombre for c in self.columnas)

    @property
    def secuencia(self) -> str | None:
        return f'{self.nombre}_id_seq' if self.identidad else None


def _c(nombre: str, tipo: str, nula: bool = False) -> Columna:
    return Columna(nombre, tipo, nula)


_PARTIDA = (_c('id', 'int'), _c('orden_id', 'int'), _c('renglon', 'smallint'), _c('concepto', 'varchar(24)'),
            _c('moneda', 'char(3)'), _c('monto', 'decimal(18,2)'), _c('fecha_hora', 'datetime'),
            _c('referencia', 'varchar(35)'))

TABLAS: dict[str, Tabla] = {t.nombre: t for t in (
    Tabla('moneda', (_c('codigo', 'char(3)'), _c('numerico', 'char(3)'), _c('nombre', 'nvarchar(60)'),
                     _c('decimales', 'tinyint'), _c('activa', 'bit')), identidad=False),
    Tabla('folio', (_c('serie', 'varchar(10)'), _c('siguiente', 'int'), _c('actualizado', 'datetime')),
          identidad=False),
    Tabla('operacion', (
        _c('id', 'int'), _c('folio', 'varchar(20)'), _c('fecha_operacion', 'smalldatetime'), _c('sucursal', 'char(4)'),
        _c('canal', 'varchar(10)'), _c('cliente', 'nvarchar(120)'),
        _c('cuenta_clabe', 'varchar(18)'), _c('tipo', 'char(1)'), _c('moneda', 'char(3)'),
        _c('monto_divisa', 'decimal(18,2)'), _c('tipo_cambio', 'decimal(18,6)'),
        _c('tipo_cambio_referencia', 'decimal(18,6)'), _c('monto_mxn', 'decimal(18,2)'),
        _c('estatus', 'varchar(12)')), identidad=True,
        sello='fecha_operacion (fecha de negocio local)', monto='monto_mxn'),
    Tabla('orden_pago', (
        _c('id', 'int'), _c('operacion_id', 'int'), _c('folio', 'varchar(20)'), _c('uetr', 'char(36)'),
        _c('referencia_mt103', 'varchar(16)'), _c('fecha_registro', 'datetime'), _c('fecha_envio', 'datetime'),
        _c('fecha_valor', 'date'), _c('bic_corresponsal', 'char(11)'),
        _c('bic_intermediario', 'char(11)'), _c('beneficiario', 'nvarchar(120)'),
        _c('cuenta_beneficiario', 'varchar(34)'), _c('moneda', 'char(3)'), _c('monto', 'decimal(18,2)'),
        _c('gastos', 'char(3)'), _c('codigo_proposito', 'char(4)', nula=True), _c('estatus', 'varchar(12)'),
        _c('horas_liquidacion', 'decimal(9,2)', nula=True)), identidad=True,
        sello='fecha_registro (hora local con la que la interfaz la registra)', monto='monto'),
    Tabla('partida_solicitada', _PARTIDA, identidad=True,
          sello='la bitácora «U → LIQUIDADA» de su orden (hora del servidor): la escribe la misma llamada',
          monto='monto'),
    Tabla('partida_liquidada', _PARTIDA, identidad=True,
          sello='fecha_hora (= la fecha_registro de su orden, hora local)', monto='monto'),
    Tabla('bitacora', (
        _c('id', 'bigint'), _c('tabla', 'sysname'), _c('llave', 'int'), _c('accion', 'char(1)'),
        _c('estatus_anterior', 'varchar(12)', nula=True), _c('estatus_nuevo', 'varchar(12)', nula=True),
        _c('usuario', 'sysname'), _c('fecha', 'datetime')), identidad=True,
        sello='fecha (GETDATE() del servidor en el disparador)'),
)}
CON_IDENTIDAD = tuple(t for t in TABLAS.values() if t.identidad)
SERIES = {'FX': 'operacion', 'OP': 'orden_pago'}     # el consumible y la tabla que lo usa


# ── consultas al ORIGEN (SQL Server). Literales: una por tabla y por uso ────────────────────────────────────────
# El mes del plan: CONVERT(char(7), sello, 126) = 'aaaa-mm' en hora local. La ventana [%(grieta_desde)s,
# %(grieta_hasta)s) manda sus filas a %(grieta_mes)s: vacía en el plan bueno; en el control de la grieta es la última
# noche de octubre vista en UTC. Se suma el monto para los totales del plan.

PLAN: dict[str, str] = {
    'operacion': """SELECT m.mes, MIN(m.id), MAX(m.id), COUNT_BIG(*), SUM(m.monto)
FROM (SELECT id, monto_mxn AS monto,
             CASE WHEN fecha_operacion >= %(grieta_desde)s AND fecha_operacion < %(grieta_hasta)s
                  THEN %(grieta_mes)s ELSE CONVERT(char(7), fecha_operacion, 126) END AS mes
      FROM dbo.operacion WHERE id <= %(corte)s) m
GROUP BY m.mes""",
    'orden_pago': """SELECT m.mes, MIN(m.id), MAX(m.id), COUNT_BIG(*), SUM(m.monto)
FROM (SELECT id, monto,
             CASE WHEN fecha_registro >= %(grieta_desde)s AND fecha_registro < %(grieta_hasta)s
                  THEN %(grieta_mes)s ELSE CONVERT(char(7), fecha_registro, 126) END AS mes
      FROM dbo.orden_pago WHERE id <= %(corte)s) m
GROUP BY m.mes""",
    'partida_solicitada': """SELECT m.mes, MIN(m.id), MAX(m.id), COUNT_BIG(*), SUM(m.monto)
FROM (SELECT s.id, s.monto,
             CASE WHEN b.fecha >= %(grieta_desde)s AND b.fecha < %(grieta_hasta)s
                  THEN %(grieta_mes)s ELSE CONVERT(char(7), b.fecha, 126) END AS mes
      FROM dbo.partida_solicitada s
      JOIN dbo.bitacora b ON b.tabla = N'orden_pago' AND b.accion = 'U' AND b.estatus_nuevo = 'LIQUIDADA'
           AND b.llave = s.orden_id
      WHERE s.id <= %(corte)s) m
GROUP BY m.mes""",
    'partida_liquidada': """SELECT m.mes, MIN(m.id), MAX(m.id), COUNT_BIG(*), SUM(m.monto)
FROM (SELECT id, monto,
             CASE WHEN fecha_hora >= %(grieta_desde)s AND fecha_hora < %(grieta_hasta)s
                  THEN %(grieta_mes)s ELSE CONVERT(char(7), fecha_hora, 126) END AS mes
      FROM dbo.partida_liquidada WHERE id <= %(corte)s) m
GROUP BY m.mes""",
    'bitacora': """SELECT m.mes, MIN(m.id), MAX(m.id), COUNT_BIG(*), NULL
FROM (SELECT id,
             CASE WHEN fecha >= %(grieta_desde)s AND fecha < %(grieta_hasta)s
                  THEN %(grieta_mes)s ELSE CONVERT(char(7), fecha, 126) END AS mes
      FROM dbo.bitacora WHERE id <= %(corte)s) m
GROUP BY m.mes""",
}

# Totales del origen hasta el corte (para el cuadre del plan y del cierre), por tabla.
TOTALES: dict[str, str] = {
    'operacion': 'SELECT COUNT_BIG(*), MAX(id), SUM(monto_mxn) FROM dbo.operacion WHERE id <= %(corte)s',
    'orden_pago': 'SELECT COUNT_BIG(*), MAX(id), SUM(monto) FROM dbo.orden_pago WHERE id <= %(corte)s',
    'partida_solicitada': 'SELECT COUNT_BIG(*), MAX(id), SUM(monto) FROM dbo.partida_solicitada '
                          'WHERE id <= %(corte)s',
    'partida_liquidada': 'SELECT COUNT_BIG(*), MAX(id), SUM(monto) FROM dbo.partida_liquidada '
                         'WHERE id <= %(corte)s',
    'bitacora': 'SELECT COUNT_BIG(*), MAX(id), NULL FROM dbo.bitacora WHERE id <= %(corte)s',
}

# setval al cierre: desde IDENT_CURRENT, no desde MAX(id) (una inserción revertida al final los separa).
IDENT_CURRENT: dict[str, str] = {
    'operacion': "SELECT IDENT_CURRENT(N'dbo.operacion')",
    'orden_pago': "SELECT IDENT_CURRENT(N'dbo.orden_pago')",
    'partida_solicitada': "SELECT IDENT_CURRENT(N'dbo.partida_solicitada')",
    'partida_liquidada': "SELECT IDENT_CURRENT(N'dbo.partida_liquidada')",
    'bitacora': "SELECT IDENT_CURRENT(N'dbo.bitacora')",
}

# Las filas de un RANGO de ids: lo que se carga.
POR_RANGO: dict[str, str] = {
    'operacion': """SELECT id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda,
       monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus
FROM dbo.operacion WHERE id > %(desde)s AND id <= %(hasta)s ORDER BY id""",
    'orden_pago': """SELECT id, operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio, fecha_valor,
       bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, gastos, codigo_proposito,
       estatus, horas_liquidacion
FROM dbo.orden_pago WHERE id > %(desde)s AND id <= %(hasta)s ORDER BY id""",
    'partida_solicitada': """SELECT id, orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia
FROM dbo.partida_solicitada WHERE id > %(desde)s AND id <= %(hasta)s ORDER BY id""",
    'partida_liquidada': """SELECT id, orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia
FROM dbo.partida_liquidada WHERE id > %(desde)s AND id <= %(hasta)s ORDER BY id""",
    'bitacora': """SELECT id, tabla, llave, accion, estatus_anterior, estatus_nuevo, usuario, fecha
FROM dbo.bitacora WHERE id > %(desde)s AND id <= %(hasta)s ORDER BY id""",
}

# Las filas de un MES por su sello (el mes de verdad, sin el plan): la huella del origen.
POR_SELLO: dict[str, str] = {
    'operacion': """SELECT id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda,
       monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus
FROM dbo.operacion WHERE fecha_operacion >= %(inicio)s AND fecha_operacion < %(fin)s AND id <= %(corte)s""",
    'orden_pago': """SELECT id, operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio, fecha_valor,
       bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, gastos, codigo_proposito,
       estatus, horas_liquidacion
FROM dbo.orden_pago WHERE fecha_registro >= %(inicio)s AND fecha_registro < %(fin)s AND id <= %(corte)s""",
    'partida_solicitada': """SELECT s.id, s.orden_id, s.renglon, s.concepto, s.moneda, s.monto, s.fecha_hora,
       s.referencia
FROM dbo.partida_solicitada s
JOIN dbo.bitacora b ON b.tabla = N'orden_pago' AND b.accion = 'U' AND b.estatus_nuevo = 'LIQUIDADA'
     AND b.llave = s.orden_id
WHERE b.fecha >= %(inicio)s AND b.fecha < %(fin)s AND s.id <= %(corte)s""",
    'partida_liquidada': """SELECT id, orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia
FROM dbo.partida_liquidada WHERE fecha_hora >= %(inicio)s AND fecha_hora < %(fin)s AND id <= %(corte)s""",
    'bitacora': """SELECT id, tabla, llave, accion, estatus_anterior, estatus_nuevo, usuario, fecha
FROM dbo.bitacora WHERE fecha >= %(inicio)s AND fecha < %(fin)s AND id <= %(corte)s""",
}

CATALOGO: dict[str, str] = {
    'moneda': 'SELECT codigo, numerico, nombre, decimales, activa FROM dbo.moneda ORDER BY codigo',
    'folio': 'SELECT serie, siguiente, actualizado FROM dbo.folio ORDER BY serie',
}

# Los índices ÚNICOS del origen, con sus columnas en orden: el destino debe tener los mismos.
INDICES_UNICOS_ORIGEN = """SELECT t.name, i.name, c.name, ic.key_ordinal
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE s.name = N'dbo' AND i.is_unique = 1 AND ic.key_ordinal > 0 AND t.is_ms_shipped = 0
ORDER BY t.name, i.name, ic.key_ordinal"""


def indices_unicos(filas: Iterable[tuple[str, str, str, int]]) -> dict[str, list[list[str]]]:
    """(tabla, índice, columna, posición) → por tabla, la lista ordenada de las columnas de cada índice único. El
    nombre del índice no cuenta: cuentan la tabla y sus columnas."""
    por_indice: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for tabla, indice, columna, posicion in filas:
        por_indice.setdefault((tabla, indice), []).append((int(posicion), columna))
    resultado: dict[str, list[list[str]]] = {}
    for (tabla, _indice), columnas in por_indice.items():
        resultado.setdefault(tabla, []).append([c for _p, c in sorted(columnas)])
    return {t: sorted(v) for t, v in sorted(resultado.items())}


# ── el mes y sus fronteras ──────────────────────────────────────────────────────────────────────────────────────

def frontera(mes: str) -> tuple[datetime, datetime]:
    """[inicio, fin) del mes en hora local (sin zona, como la guarda el legado)."""
    anio, numero = (int(x) for x in mes.split('-'))
    inicio = datetime(anio, numero, 1)
    fin = datetime(anio + numero // 12, numero % 12 + 1, 1)
    return inicio, fin


def siguiente(mes: str) -> str:
    _inicio, fin = frontera(mes)
    return f'{fin.year:04d}-{fin.month:02d}'


def ventana_grieta(mes: str | None) -> dict:
    """Los parámetros de la ventana del plan. Sin grieta, vacía. Con grieta: el fin del mes calculado en UTC, es decir,
    las filas de la última noche desde la hora local en que en UTC ya es el mes siguiente."""
    if mes is None:
        cero = datetime(1900, 1, 1)
        return {'grieta_desde': cero, 'grieta_hasta': cero, 'grieta_mes': '0000-00'}
    _inicio, fin = frontera(mes)
    en_utc = fin.replace(tzinfo=timezone.utc).astimezone(CDMX).replace(tzinfo=None)
    return {'grieta_desde': en_utc, 'grieta_hasta': fin, 'grieta_mes': siguiente(mes)}


# ── el plan ─────────────────────────────────────────────────────────────────────────────────────────────────────

def plan(agregados: dict[str, Iterable[tuple]], totales: dict[str, tuple], cortes: dict[str, int],
         meses: tuple[str, ...] = MESES, grieta: str | None = None) -> dict:
    """Del GROUP BY por mes del origen (`agregados[tabla]` = (mes, MIN(id), MAX(id), filas, monto)) al plan: por tabla
    y mes el rango (desde, hasta] que se carga. Falla nombrando lo que impide partir por rangos contiguos."""
    faltas: list[str] = []
    tablas: dict[str, dict] = {}
    for t in CON_IDENTIDAD:
        filas = sorted((str(m), int(lo), int(hi), int(n), Decimal(s or 0)) for m, lo, hi, n, s in agregados[t.nombre])
        fuera = [m for m, *_ in filas if m not in meses]
        if fuera:
            faltas.append(f'{t.nombre}: filas fuera de los {len(meses)} meses: {fuera[:MUESTRA]}')
        por_mes = {m: (lo, hi, n, s) for m, lo, hi, n, s in filas if m in meses}
        rangos: dict[str, dict] = {}
        anterior_mes, desde = None, 0
        for mes in meses:
            if mes not in por_mes:
                rangos[mes] = {'desde': desde, 'hasta': desde, 'filas': 0, 'monto': '0'}
                continue
            lo, hi, n, s = por_mes[mes]
            if lo <= desde:
                faltas.append(f'{t.nombre}: {mes} empieza en el id {lo}, que no es mayor que el fin de '
                              f'{anterior_mes} ({desde}): los meses se enciman, no hay rangos contiguos')
            rangos[mes] = {'desde': desde, 'hasta': hi, 'filas': n, 'monto': format(s, 'f')}
            anterior_mes, desde = mes, max(desde, hi)
        total_filas, total_max, total_monto = totales[t.nombre]
        suma = sum(r['filas'] for r in rangos.values())
        if suma != int(total_filas):
            faltas.append(f'{t.nombre}: los meses suman {suma:,} filas y el origen hasta el corte tiene '
                          f'{int(total_filas):,} (una fila sin sello o con dos)')
        if desde > cortes[t.nombre]:
            faltas.append(f'{t.nombre}: el último mes termina en {desde}, después del corte {cortes[t.nombre]}')
        tablas[t.nombre] = {'corte': cortes[t.nombre], 'origen': {
            'filas': int(total_filas), 'max_id': None if total_max is None else int(total_max),
            'monto': format(Decimal(total_monto or 0), 'f')}, 'meses': rangos}
    resultado = {'meses': list(meses), 'grieta': grieta, 'tablas': tablas, 'faltas': faltas}
    resultado['sha'] = plan_sha(resultado)
    return resultado


def plan_sha(p: dict) -> str:
    return hashlib.sha256(json.dumps({'meses': p['meses'], 'grieta': p['grieta'], 'tablas': p['tablas']},
                                     sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def rangos(p: dict, mes: str) -> dict[str, dict]:
    return {t: d['meses'][mes] for t, d in p['tablas'].items()}


def totales_del_plan(p: dict) -> dict[str, dict]:
    """Los totales GLOBALES que deja el plan: suma de filas y montos de los meses, y si los rangos cubren del primer
    id al último sin hueco ni encime. No ven en qué mes cae cada fila."""
    resultado = {}
    for t, d in p['tablas'].items():
        meses = [d['meses'][m] for m in p['meses']]
        cubre = all(meses[i]['desde'] == (meses[i - 1]['hasta'] if i else 0) for i in range(len(meses)))
        resultado[t] = {'filas': sum(m['filas'] for m in meses),
                        'monto': format(sum(Decimal(m['monto']) for m in meses), 'f'),
                        'hasta': meses[-1]['hasta'] if meses else 0, 'cubre_sin_huecos': cubre}
    return resultado


# ── huellas ─────────────────────────────────────────────────────────────────────────────────────────────────────

def huella_de_filas(tabla: Tabla, filas: Iterable[tuple]) -> dict:
    """Huella de un conjunto de filas: sha256 de las líneas `llave|huella de la fila`, ordenadas por llave. La huella
    de cada fila es la forma canónica de `corte/cifras.py` (`cifras.huella`) sobre los valores CRUDOS, sin normalizar
    nada: ni el relleno de los char(n) ni los centinelas. Dos lados con las mismas filas y los mismos valores, y sólo
    así, dan la misma huella."""
    lineas = sorted((fila[0], cifras.huella(dict(zip(tabla.nombres, fila)))) for fila in filas)
    texto = '\n'.join(f'{llave}|{h}' for llave, h in lineas)
    return {'filas': len(lineas), 'huella': hashlib.sha256(texto.encode('utf-8')).hexdigest(),
            'primero': lineas[0][0] if lineas else None, 'ultimo': lineas[-1][0] if lineas else None}


def comparar_mes(origen: dict[str, dict], destino: dict[str, dict]) -> list[str]:
    """Huella del mes por tabla: origen (por sello) contra destino (por rango). Vacío = cuadra."""
    faltas = []
    for t in sorted(set(origen) | set(destino)):
        a, b = origen.get(t), destino.get(t)
        if a is None or b is None or a['huella'] != b['huella']:
            faltas.append(f"{t}: origen {(a or {}).get('filas')} filas · huella {str((a or {}).get('huella'))[:12]} ≠ "
                          f"destino {(b or {}).get('filas')} filas · huella {str((b or {}).get('huella'))[:12]}")
    return faltas


def diferencias_de_huella(previa: dict, ahora: dict) -> list[str]:
    """Qué cambió entre dos huellas del destino (tablas, secuencias): vacío = es la misma."""
    faltas = []
    for grupo in ('tablas', 'secuencias'):
        a, b = previa.get(grupo, {}), ahora.get(grupo, {})
        for nombre in sorted(set(a) | set(b)):
            if a.get(nombre) != b.get(nombre):
                faltas.append(f'{grupo[:-1]} {nombre}: {a.get(nombre)} → {b.get(nombre)}')
    return faltas


# ── guardas y consumibles ───────────────────────────────────────────────────────────────────────────────────────

def corte_del_destino(maximos: dict[str, int | None], registro: dict[str, int]) -> tuple[dict[str, int], list[str]]:
    """El corte del destino por dos caminos: `MAX(id)` de cada tabla y el registro de meses aplicados. Si no coinciden,
    hay filas que el registro no explica (o al revés) y no se carga nada."""
    corte, faltas = {}, []
    for t in CON_IDENTIDAD:
        por_id, por_registro = maximos.get(t.nombre) or 0, registro.get(t.nombre, 0)
        if por_id != por_registro:
            faltas.append(f'{t.nombre}: MAX(id) del destino {por_id} ≠ el del registro de meses {por_registro}')
        corte[t.nombre] = max(por_id, por_registro)
    return corte, faltas


def guarda_de_rangos(rango: dict[str, dict], corte: dict[str, int]) -> list[str]:
    """Sólo ids > corte: el mes no puede empezar antes de lo que el destino ya tiene."""
    return [f"{t}: el mes empieza después del id {r['desde']} y el destino ya llega a {corte[t]}: cargaría ids ≤ corte"
            for t, r in sorted(rango.items()) if r['filas'] and r['desde'] < corte[t]]


def ids_fuera(ids: Iterable[int], desde: int, hasta: int, corte: int) -> list[int]:
    """Ids del lote que no son > max(desde, corte) o que pasan de `hasta`: no se insertan."""
    piso = max(desde, corte)
    return sorted(i for i in ids if i <= piso or i > hasta)


def numero_de_folio(folio: str, serie: str) -> int | None:
    prefijo = f'{serie}-'
    if folio.startswith(prefijo) and folio[len(prefijo):].isdigit():
        return int(folio[len(prefijo):])
    return None


def folios_del_lote(filas: dict[str, list[tuple]]) -> dict[str, int]:
    """El siguiente folio que deja cada serie después del lote: el mayor usado + 1 (FX en la operación, OP en la
    orden)."""
    resultado = {}
    for serie, tabla in SERIES.items():
        columna = TABLAS[tabla].nombres.index('folio')
        numeros = [n for f in filas.get(tabla, []) if (n := numero_de_folio(f[columna], serie)) is not None]
        if numeros:
            resultado[serie] = max(numeros) + 1
    return resultado


def reversa(mes: str, p: dict, previa: dict) -> dict:
    """La reversa de un mes, generada ANTES de aplicarlo: los rangos que se borran, el valor previo de cada secuencia
    y del consumible y la huella previa con la que debe quedar el destino."""
    return {
        'version': 1, 'mes': mes, 'plan_sha': p['sha'], 'generada_utc': datetime.now(timezone.utc).isoformat(),
        'borrar': {t: {'desde': r['desde'], 'hasta': r['hasta']} for t, r in rangos(p, mes).items() if r['filas']},
        'secuencias': previa['secuencias'],
        'folios': {s: v['siguiente'] for s, v in previa['folios'].items()},
        'huella_previa': {'tablas': previa['tablas'], 'secuencias': previa['secuencias']},
    }
