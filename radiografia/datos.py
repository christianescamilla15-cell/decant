"""Detectores sobre los DATOS restaurados: centinelas por distribución, texto con mojibake y llaves naturales con
duplicados (re-registro). Todo por consultas de sólo lectura; los nombres de objeto van siempre por QUOTENAME.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pymssql

TEXTO = frozenset(('char', 'varchar', 'nchar', 'nvarchar'))
NUMERICO = frozenset(('int', 'bigint', 'smallint', 'tinyint', 'decimal', 'numeric', 'money', 'smallmoney', 'float',
                      'real'))
FECHA = frozenset(('date', 'datetime', 'datetime2', 'smalldatetime', 'datetimeoffset'))

SENTINELAS_TEXTO = frozenset(('NA', 'N/A', 'N.A.', 'N/D', 'ND', 'NULL', 'NONE', 'NINGUNO', 'SIN DATO', 'S/D', 'SD',
                              '-', '--', '.', 'X', 'XX', 'XXX', 'XXXX', '?', '0', '00', '000', '0000', 'TBD',
                              'PENDIENTE', 'DESCONOCIDO', 'UNKNOWN'))
# 9 y 99 no: son códigos legítimos demasiado comunes (el control público tenía un id de empaque 9).
SENTINELAS_NUMERO = frozenset(Decimal(v) for v in ('0', '-1', '999', '9999', '99999', '999999', '9999999', '-999',
                                                     '-9999'))
SENTINELAS_FECHA = frozenset((date(1900, 1, 1), date(1753, 1, 1), date(9999, 12, 31), date(2079, 6, 6),
                              date(1, 1, 1), date(2099, 12, 31)))

# El nombre de la tabla y de la columna nunca se interpolan en Python: se arman en el servidor con QUOTENAME.
_DINAMICA = ("DECLARE @t nvarchar(300) = QUOTENAME(%s) + N'.' + QUOTENAME(%s), @c nvarchar(300) = QUOTENAME(%s); "
             "DECLARE @sql nvarchar(max) = REPLACE(REPLACE(%s, N'{t}', @t), N'{c}', @c); "
             "EXEC sp_executesql @sql, N'@v sql_variant', @v = %s")


def consultar(cursor, plantilla: str, esquema: str, tabla: str, columna: str = '', valor=None) -> list[tuple]:
    cursor.execute(_DINAMICA, (esquema, tabla, columna, plantilla, valor))
    return cursor.fetchall() if cursor.description else []


def _base(valor):
    if isinstance(valor, str):
        return valor.strip()
    if isinstance(valor, datetime):
        return valor.date() if valor.time() == datetime.min.time() else valor
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return Decimal(str(valor))
    return valor


def clasificar_centinela(tipo: str, valor, frecuencia: float, otros: dict) -> str | None:
    """¿Es `valor` un centinela? Regla genérica, sin conocer la columna.

    otros: {'largo_dominante', 'pct_largo_dominante', 'minimo', 'maximo'} calculados sobre los DEMÁS valores.
    """
    v = _base(valor)
    if tipo in TEXTO:
        if v.upper() in SENTINELAS_TEXTO:
            return f"valor de relleno típico ('{v}')"
        largo, pct = otros.get('largo_dominante'), otros.get('pct_largo_dominante') or 0
        if largo and pct >= 0.9 and len(v) != largo and len(v) <= max(3, largo // 3):
            return f"forma ajena a la columna ('{v}' mide {len(v)}; el {pct:.0%} de los demás mide {largo})"
        return None
    if tipo in NUMERICO:
        minimo, maximo = otros.get('minimo'), otros.get('maximo')
        if v in SENTINELAS_NUMERO and minimo is not None and (v < _base(minimo) or v > _base(maximo)):
            return f'{v} queda fuera del rango del resto de la columna ({minimo} … {maximo})'
        return None
    if tipo in FECHA:
        dia = v.date() if isinstance(v, datetime) else v
        if dia in SENTINELAS_FECHA:
            return f'fecha de relleno típica ({dia})'
        minimo, maximo = otros.get('minimo'), otros.get('maximo')
        if minimo is not None and isinstance(dia, date):
            lo = minimo.date() if isinstance(minimo, datetime) else minimo
            hi = maximo.date() if isinstance(maximo, datetime) else maximo
            if (lo - dia).days > 3650 or (dia - hi).days > 3650:
                return f'{dia} queda a más de 10 años del resto ({lo} … {hi})'
    return None


def centinelas(cursor, columnas: list[dict]) -> list[dict]:
    hallazgos = []
    for col in columnas:
        if col['tipo'] not in TEXTO | NUMERICO | FECHA or col['es_identidad'] or col['es_pk'] or col['es_fk'] \
                or col['es_calculada'] or col['filas'] < 100:
            continue
        esq, tab, nombre = col['esquema'], col['tabla'], col['columna']
        total, no_nulos, distintos = consultar(
            cursor, 'SELECT COUNT_BIG(*), COUNT_BIG({c}), COUNT_BIG(DISTINCT {c}) FROM {t}', esq, tab, nombre)[0]
        if distintos < 3:
            continue
        top = consultar(cursor, 'SELECT TOP (5) {c}, COUNT_BIG(*) AS n FROM {t} WHERE {c} IS NOT NULL '
                                'GROUP BY {c} ORDER BY n DESC', esq, tab, nombre)
        minimo_filas = max(10, total // 1000)
        for valor, n in top:
            if n < minimo_filas:
                break
            otros = _otros(cursor, col, valor)
            razon = clasificar_centinela(col['tipo'], valor, n / total, otros)
            if razon:
                nulos = total - no_nulos
                hallazgos.append({
                    'categoria': 'centinela', 'objeto': f'{esq}.{tab}.{nombre}'.lower(), 'tipo_objeto': 'COLUMNA',
                    'linea': None, 'fragmento': '',
                    'detalle': f"{n:,} filas ({n / total:.1%}) con {repr(_base(valor))}: {razon}"
                               + ('; la columna no usa NULL' if nulos == 0 else f'; además tiene {nulos:,} NULL'),
                    'valor': str(_base(valor)), 'filas': n, 'total': total, 'usa_null': nulos > 0})
    return hallazgos


def _otros(cursor, col: dict, valor) -> dict:
    esq, tab, nombre = col['esquema'], col['tabla'], col['columna']
    if col['tipo'] in TEXTO:
        filas = consultar(cursor, 'SELECT TOP (1) LEN({c}), COUNT_BIG(*) AS n, SUM(COUNT_BIG(*)) OVER () FROM {t} '
                                  'WHERE {c} IS NOT NULL AND {c} <> CAST(@v AS nvarchar(4000)) GROUP BY LEN({c}) '
                                  'ORDER BY n DESC', esq, tab, nombre, valor)
        if not filas:
            return {}
        largo, n, total = filas[0]
        return {'largo_dominante': largo, 'pct_largo_dominante': n / total if total else 0}
    # el valor viaja como sql_variant: se convierte explícito para comparar por valor y no por familia de tipo
    conversion = 'float' if col['tipo'] in NUMERICO else 'datetime2'
    filas = consultar(cursor, f'SELECT MIN({{c}}), MAX({{c}}) FROM {{t}} WHERE {{c}} <> CAST(@v AS {conversion})',
                      esq, tab, nombre, valor)
    return {'minimo': filas[0][0], 'maximo': filas[0][1]} if filas else {}


def es_mojibake(texto: str) -> bool:
    """UTF-8 leído como latin-1/cp1252: si al revertirlo sale otro texto válido en UTF-8, estaba dañado.

    Se revierte carácter por carácter con cp1252 y, para lo que cp1252 no define (0x81, 0x8D, 0x8F, 0x90, 0x9D),
    con latin-1: así lo deja Windows al decodificar, y así sale de una interfaz que leyó latin-1.
    """
    crudo = bytearray()
    for caracter in texto:
        try:
            crudo += caracter.encode('cp1252')
        except UnicodeEncodeError:
            if ord(caracter) > 0xFF:
                return False
            crudo.append(ord(caracter))
    try:
        return bytes(crudo).decode('utf-8') != texto
    except UnicodeDecodeError:
        return False


# Siempre con intercalación binaria: en las intercalaciones CI algunos caracteres (U+FFFD) no pesan y el LIKE
# casaría con cualquier texto.
_SOSPECHA = ("{c} COLLATE Latin1_General_BIN LIKE N'%[ÃÂ]%' OR {c} COLLATE Latin1_General_BIN LIKE N'%â€%' "
             "OR {c} COLLATE Latin1_General_BIN LIKE N'%' + NCHAR(65533) + N'%'")


def mojibake(cursor, columnas: list[dict]) -> list[dict]:
    hallazgos = []
    for col in columnas:
        if col['tipo'] not in TEXTO or col['filas'] == 0:
            continue
        esq, tab, nombre = col['esquema'], col['tabla'], col['columna']
        sospechosas = consultar(cursor, f'SELECT COUNT_BIG(*) FROM {{t}} WHERE {_SOSPECHA}', esq, tab, nombre)[0][0]
        if not sospechosas:
            continue
        muestra = [fila[0] for fila in consultar(
            cursor, f'SELECT DISTINCT TOP (400) {{c}} FROM {{t}} WHERE {_SOSPECHA}', esq, tab, nombre)]
        dañados = [t for t in muestra if es_mojibake(t)]
        if not dañados:
            continue
        hallazgos.append({
            'categoria': 'mojibake', 'objeto': f'{esq}.{tab}.{nombre}'.lower(), 'tipo_objeto': 'COLUMNA',
            'linea': None, 'fragmento': '',
            'detalle': f'{sospechosas:,} filas con secuencias de UTF-8 leído como latin-1; en la muestra, '
                       f'{len(dañados)} de {len(muestra)} valores distintos se reparan al revertir la decodificación',
            'filas': sospechosas, 'ejemplos': [ascii(t) for t in dañados[:3]]})
    return hallazgos


def similitud_base(cursor, esquema: str, tabla: str, indices: list[int]) -> float:
    """Cuánto se parecen dos filas CUALESQUIERA de la tabla (pares de una muestra fija por CHECKSUM).

    Banderas y NULL hacen que filas sin relación compartan columnas; el re-registro se mide como lo que las filas
    repetidas se parecen POR ENCIMA de esta base.
    """
    try:
        filas = consultar(cursor, 'SELECT TOP (200) * FROM {t} ORDER BY CHECKSUM(*)', esquema, tabla)
    except pymssql.Error:      # tipos no comparables (xml, geography…): muestra sin orden
        filas = consultar(cursor, 'SELECT TOP (200) * FROM {t}', esquema, tabla)
    pares = list(zip(filas[0::2], filas[1::2]))
    if not pares or not indices:
        return 0.0
    return sum(sum(1 for k in indices if repr(a[k]) == repr(b[k])) / len(indices) for a, b in pares) / len(pares)


def es_re_registro(similitud: float, base: float) -> bool:
    """Las filas que repiten la llave son el mismo documento si se parecen mucho y MUCHO MÁS que dos cualesquiera."""
    return similitud >= 0.6 and similitud - base >= 0.3


def llaves_duplicadas(cursor, columnas: list[dict], por_tabla: dict[str, list[dict]],
                      historicas: frozenset[str] = frozenset()) -> list[dict]:
    """Columnas con forma de llave natural (casi únicas) que repiten valor. Si las filas repetidas son el MISMO
    documento (casi todas sus columnas iguales, muy por encima de dos filas cualesquiera) con otra llave interna,
    es un re-registro. Las tablas de historial de una tabla temporal se omiten: guardan versiones por diseño."""
    hallazgos = []
    bases: dict[str, float] = {}
    for col in columnas:
        if col['tipo'] not in TEXTO | {'uniqueidentifier'} or col['es_pk'] or col['es_fk'] or col['filas'] < 100:
            continue
        esq, tab, nombre = col['esquema'], col['tabla'], col['columna']
        if f'{esq}.{tab}'.lower() in historicas:
            continue
        no_nulos, distintos, largo = consultar(
            cursor, 'SELECT COUNT_BIG({c}), COUNT_BIG(DISTINCT {c}), AVG(CAST(LEN(CAST({c} AS nvarchar(400))) AS '
                    'float)) FROM {t}', esq, tab, nombre)[0]
        if not no_nulos or (largo or 0) < 6 or distintos == no_nulos or distintos / no_nulos < 0.3:
            continue
        grupos = [g[0] for g in consultar(
            cursor, 'SELECT TOP (40) {c} FROM {t} WHERE {c} IS NOT NULL GROUP BY {c} HAVING COUNT_BIG(*) > 1 '
                    'ORDER BY {c}', esq, tab, nombre)]
        cols_tabla = por_tabla[f'{esq}.{tab}'.lower()]
        indices = [k for k, c in enumerate(cols_tabla) if not c['es_pk'] and c['columna'] != nombre]
        pk = [k for k, c in enumerate(cols_tabla) if c['es_pk']]
        fechas = [k for k, c in enumerate(cols_tabla) if c['tipo'] in FECHA]
        similitudes, reciente = [], {k: 0 for k in fechas}
        for valor in grupos:
            filas = consultar(cursor, 'SELECT * FROM {t} WHERE {c} = CAST(@v AS nvarchar(4000))', esq, tab, nombre,
                              valor)
            if len(filas) < 2:
                continue
            iguales = sum(1 for k in indices if len({repr(f[k]) for f in filas}) == 1)
            similitudes.append(iguales / len(indices) if indices else 0)
            if pk:
                ultima = max(filas, key=lambda f: tuple(f[k] for k in pk))
                for k in fechas:
                    if all(f[k] is not None for f in filas) and ultima[k] == max(f[k] for f in filas):
                        reciente[k] += 1
        if not similitudes:
            continue
        similitud = sum(similitudes) / len(similitudes)
        llave_tabla = f'{esq}.{tab}'.lower()
        if llave_tabla not in bases:
            todas = [k for k, c in enumerate(cols_tabla) if not c['es_pk']]
            bases[llave_tabla] = similitud_base(cursor, esq, tab, todas)
        base = bases[llave_tabla]
        repetidos = no_nulos - distintos
        mejor = max(reciente, key=reciente.get) if reciente else None
        orden = ''
        if mejor is not None and grupos:
            orden = (f'; en {reciente[mejor]} de {len(similitudes)} grupos la fila de id mayor es la de '
                     f'{cols_tabla[mejor]["columna"]} más reciente')
        es_registro = es_re_registro(similitud, base)
        hallazgos.append({
            'categoria': 're_registro' if es_registro else 'llave_candidata_con_duplicados',
            'objeto': f'{esq}.{tab}.{nombre}'.lower(), 'tipo_objeto': 'COLUMNA', 'linea': None, 'fragmento': '',
            'detalle': (f'{repetidos:,} filas repiten un valor ({distintos:,} distintos en {no_nulos:,}); las filas '
                        f'repetidas comparten el {similitud:.0%} de sus columnas (dos filas cualesquiera, el '
                        f'{base:.0%})'
                        + (': el MISMO documento dado de alta con otra llave interna' if es_registro else '')
                        + orden),
            'similitud': round(similitud, 3), 'similitud_base': round(base, 3), 'repetidas': repetidos})
    return hallazgos


# ── Espacios finales: SQL Server los ignora al comparar; PostgreSQL no ─────────────────────────────────────────

# Se mide EN EL MOTOR, nunca en Python después de un BCP (el BCP de FreeTDS los recorta) ni con rstrip().
# DATALENGTH(RTRIM(c)) en vez de LEN(c): DATALENGTH cuenta BYTES (2 por carácter en nvarchar, de 1 a 4 en UTF-8),
# así que «> LEN(c)» marcaría todo nvarchar; comparar bytes contra bytes vale para cualquier tipo de texto.
_CON_RELLENO = 'DATALENGTH({c}) > DATALENGTH(RTRIM({c}))'
_DINAMICA_FECHA = ("DECLARE @t nvarchar(300) = QUOTENAME(%s) + N'.' + QUOTENAME(%s), @c nvarchar(300) = QUOTENAME(%s), "
                   "@d nvarchar(300) = QUOTENAME(%s); "
                   "DECLARE @sql nvarchar(max) = REPLACE(REPLACE(REPLACE(%s, N'{t}', @t), N'{c}', @c), N'{d}', @d); "
                   "EXEC sp_executesql @sql")


def _ventana(cursor, esquema: str, tabla: str, columna: str, fecha: str) -> dict:
    cursor.execute(_DINAMICA_FECHA, (esquema, tabla, columna, fecha,
                                     f'SELECT MIN({{d}}), MAX({{d}}) FROM {{t}} WHERE {_CON_RELLENO}'))
    dentro = cursor.fetchone()
    cursor.execute(_DINAMICA_FECHA, (esquema, tabla, columna, fecha, 'SELECT MIN({d}), MAX({d}) FROM {t}'))
    toda = cursor.fetchone()
    return {'columna': fecha, 'desde': dentro[0], 'hasta': dentro[1], 'tabla_desde': toda[0], 'tabla_hasta': toda[1]}


def _fraccion(v: dict) -> float:
    try:
        return (v['hasta'] - v['desde']) / (v['tabla_hasta'] - v['tabla_desde'])
    except (TypeError, ZeroDivisionError):
        return 1.0


def espacios_finales(cursor, columnas: list[dict], por_tabla: dict[str, list[dict]]) -> list[dict]:
    """Valores de texto con espacios al final (varchar/nvarchar; char y nchar rellenan por tipo y se omiten)."""
    hallazgos = []
    for col in columnas:
        if col['tipo'] not in ('varchar', 'nvarchar') or col['filas'] == 0:
            continue
        esq, tab, nombre = col['esquema'], col['tabla'], col['columna']
        n, total = consultar(cursor, f'SELECT SUM(CASE WHEN {_CON_RELLENO} THEN 1 ELSE 0 END), COUNT_BIG({{c}}) '
                                     f'FROM {{t}}', esq, tab, nombre)[0]
        if not n:
            continue
        fechas = [c['columna'] for c in por_tabla[f'{esq}.{tab}'.lower()] if c['tipo'] in FECHA]
        ventanas = [_ventana(cursor, esq, tab, nombre, f) for f in fechas]
        ventana = min(ventanas, key=_fraccion) if ventanas else None
        texto = ''
        if ventana and ventana['desde'] is not None:
            texto = (f"; ventana en {ventana['columna']}: {ventana['desde']} → {ventana['hasta']} (la tabla va de "
                     f"{ventana['tabla_desde']} a {ventana['tabla_hasta']})"
                     + ('; concentrados en esa ventana' if _fraccion(ventana) < 0.5 else ''))
        hallazgos.append({
            'categoria': 'espacios_finales', 'objeto': f'{esq}.{tab}.{nombre}'.lower(), 'tipo_objeto': 'COLUMNA',
            'linea': None, 'fragmento': '',
            'detalle': f'{n:,} de {total:,} valores con espacios al final ({n / total:.1%}), medidos con DATALENGTH en '
                       f'el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; '
                       f'PostgreSQL sí los distingue' + texto,
            'filas': n, 'total': total,
            'ventana': {k: (str(v) if v is not None else None) for k, v in ventana.items()} if ventana else None})
    return hallazgos
