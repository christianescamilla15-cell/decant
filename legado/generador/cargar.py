"""Carga en bloque (BCP vía pymssql) de lo que el generador produjo ANTES del respaldo.

Las tablas con identidad se cargan sin la columna `id`: el servidor la asigna en el orden en que llegan las filas,
y como cada tabla está vacía ese orden reproduce el id que asignó la simulación. Al final se COMPRUEBA (conteo,
MAX(id), una muestra de filas comparadas EXACTAS columna por columna y los espacios finales de cada columna de
texto contados con DATALENGTH en el motor); si no coincide, la carga falla.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

import pymssql

from .simulacion import COLUMNAS, TABLAS, Datos


def _valor_bcp(valor):
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return datetime(valor.year, valor.month, valor.day)
    return valor


def _normalizar(valor):
    """Sólo tipos: los textos se comparan EXACTOS (un rstrip() aquí absolvía la pérdida de espacios finales)."""
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, Decimal):
        return valor.normalize()
    return valor


def cargar(datos: Datos, conexion: pymssql.Connection) -> dict[str, int]:
    cursor = conexion.cursor()
    for tabla in TABLAS:
        cursor.execute(
            "DECLARE @sql nvarchar(400) = N'SELECT COUNT_BIG(*) FROM dbo.' + QUOTENAME(%s); EXEC sp_executesql @sql",
            (tabla,))
        if cursor.fetchone()[0]:
            raise SystemExit(f'dbo.{tabla} no está vacía: corre primero `python -m legado esquema --recrear`.')
    for tabla in TABLAS:
        filas = datos.tablas[tabla]
        columnas = COLUMNAS[tabla]
        if columnas[0] == 'id':
            if [f[0] for f in filas] != list(range(1, len(filas) + 1)):
                raise SystemExit(f'{tabla}: los ids simulados no son consecutivos desde 1')
            cuerpo = [tuple(_valor_bcp(v) for v in f[1:]) for f in filas]
            ids = list(range(2, len(columnas) + 1))
        else:
            cuerpo = [tuple(_valor_bcp(v) for v in f) for f in filas]
            ids = list(range(1, len(columnas) + 1))
        if cuerpo:
            conexion.bulk_copy(f'dbo.{tabla}', cuerpo, column_ids=ids, batch_size=20000, tablock=True)
            if columnas[0] == 'id':
                _restaurar_espacios_finales(conexion, tabla, columnas, filas)
    return verificar(datos, conexion)


# Identificadores: SIEMPRE de la lista blanca fija (COLUMNAS) y citados con QUOTENAME en el servidor. Los valores
# viajan como parámetros; el relleno, como JSON que lee OPENJSON.
_RELLENAR = (
    "DECLARE @sql nvarchar(max) = N'UPDATE t SET ' + QUOTENAME(%s) + N' = t.' + QUOTENAME(%s) + N' + SPACE(x.n) "
    "FROM dbo.' + QUOTENAME(%s) + N' t JOIN OPENJSON(@pares) WITH (id int ''$[0]'', n int ''$[1]'') x "
    "ON x.id = t.id'; EXEC sp_executesql @sql, N'@pares nvarchar(max)', @pares = %s")
_CON_RELLENO = (
    "DECLARE @sql nvarchar(max) = N'SELECT COUNT_BIG(*) FROM dbo.' + QUOTENAME(%s) + N' WHERE DATALENGTH(' "
    "+ QUOTENAME(%s) + N') > DATALENGTH(RTRIM(' + QUOTENAME(%s) + N'))'; EXEC sp_executesql @sql")


def _validar(tabla: str, columna: str | None = None) -> None:
    if tabla not in COLUMNAS or (columna is not None and columna not in COLUMNAS[tabla]):
        raise ValueError(f'identificador fuera de la lista blanca: {tabla}.{columna}')


def con_relleno_en_el_motor(cursor, tabla: str, columna: str) -> int:
    """Valores con espacios finales, medidos con DATALENGTH EN EL MOTOR (nunca después de leerlos por el driver)."""
    _validar(tabla, columna)
    cursor.execute(_CON_RELLENO, (tabla, columna, columna))
    return cursor.fetchone()[0]


def _con_relleno_generados(filas: list, posicion: int) -> int:
    return sum(1 for f in filas if isinstance(f[posicion], str) and f[posicion] != f[posicion].rstrip(' '))


def _restaurar_espacios_finales(conexion: pymssql.Connection, tabla: str, columnas: tuple, filas: list) -> None:
    """El BCP de FreeTDS recorta los espacios finales de los varchar; una inserción normal los conserva
    (ANSI_PADDING ON). Se devuelven con un UPDATE por lotes y se comprueba en el motor cuántos quedaron."""
    cursor = conexion.cursor()
    for posicion, columna in enumerate(columnas):
        relleno = [(int(f[0]), len(f[posicion]) - len(f[posicion].rstrip(' '))) for f in filas
                   if isinstance(f[posicion], str) and f[posicion].endswith(' ')]
        if not relleno:
            continue
        _validar(tabla, columna)
        for inicio in range(0, len(relleno), 5000):
            cursor.execute(_RELLENAR, (columna, columna, tabla, json.dumps(relleno[inicio:inicio + 5000])))
        if con_relleno_en_el_motor(cursor, tabla, columna) != len(relleno):
            raise SystemExit(f'{tabla}.{columna}: no quedaron los {len(relleno)} valores con espacios finales')


def _tipos(cursor, tabla: str) -> dict[str, tuple[str, int]]:
    _validar(tabla)
    cursor.execute('SELECT c.name, t.name, c.max_length FROM sys.columns c JOIN sys.types t '
                   'ON t.user_type_id = c.user_type_id WHERE c.object_id = OBJECT_ID(%s)', (f'dbo.{tabla}',))
    return {nombre: (tipo, largo) for nombre, tipo, largo in cursor.fetchall()}


def _como_lo_guarda(valor, tipo: tuple[str, int]):
    """char(n)/nchar(n) rellenan con espacios POR TIPO: se espera ese relleno; varchar se compara exacto."""
    if isinstance(valor, str) and tipo[0] in ('char', 'nchar'):
        return valor.ljust(tipo[1] // (2 if tipo[0] == 'nchar' else 1))
    return valor


def verificar(datos: Datos, conexion: pymssql.Connection, muestra: int = 40) -> dict[str, int]:
    cursor = conexion.cursor()
    conteos = {}
    for tabla in TABLAS:
        columnas = COLUMNAS[tabla]
        filas = datos.tablas[tabla]
        cursor.execute(
            "DECLARE @sql nvarchar(400) = N'SELECT COUNT_BIG(*) FROM dbo.' + QUOTENAME(%s); EXEC sp_executesql @sql",
            (tabla,))
        n = cursor.fetchone()[0]
        if n != len(filas):
            raise SystemExit(f'{tabla}: {n} filas en la base, {len(filas)} generadas')
        conteos[tabla] = n
        tipos = _tipos(cursor, tabla)
        # espacios finales: en el motor, columna por columna, contra lo generado
        for posicion, columna in enumerate(columnas):
            if tipos[columna][0] in ('varchar', 'nvarchar'):
                en_motor = con_relleno_en_el_motor(cursor, tabla, columna)
                generados = _con_relleno_generados(filas, posicion)
                if en_motor != generados:
                    raise SystemExit(f'{tabla}.{columna}: {en_motor} valores con espacios finales en la base, '
                                     f'{generados} generados')
        if columnas[0] != 'id' or not filas:
            continue
        paso = max(len(filas) // muestra, 1)
        for indice in range(0, len(filas), paso):
            esperado = filas[indice]
            cursor.execute(
                "DECLARE @sql nvarchar(4000) = N'SELECT * FROM dbo.' + QUOTENAME(%s) + N' WHERE id = @id';"
                " EXEC sp_executesql @sql, N'@id bigint', @id = %s", (tabla, esperado[0]))
            obtenido = cursor.fetchone()
            esperados = [_como_lo_guarda(v, tipos[c]) for v, c in zip(esperado, columnas)]
            if [_normalizar(v) for v in obtenido] != [_normalizar(v) for v in esperados]:
                raise SystemExit(f'{tabla} id={esperado[0]}: la fila cargada no es la generada\n'
                                 f'  base:     {obtenido}\n  generada: {esperado}')
    return conteos
