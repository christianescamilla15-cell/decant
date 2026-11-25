"""Carga en bloque (BCP vía pymssql) de lo que el generador produjo ANTES del respaldo.

Las tablas con identidad se cargan sin la columna `id`: el servidor la asigna en el orden en que llegan las filas,
y como cada tabla está vacía ese orden reproduce el id que asignó la simulación. Al final se COMPRUEBA (conteo,
MAX(id) y una muestra de filas comparadas columna por columna); si no coincide, la carga falla.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pymssql

from .simulacion import COLUMNAS, TABLAS, Datos


def _valor_bcp(valor):
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return datetime(valor.year, valor.month, valor.day)
    return valor


def _normalizar(valor):
    if isinstance(valor, str):
        return valor.rstrip()          # char(n) vuelve con relleno de espacios
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


def _restaurar_espacios_finales(conexion: pymssql.Connection, tabla: str, columnas: tuple, filas: list) -> None:
    """El BCP de FreeTDS recorta los espacios finales de los varchar; una inserción normal los conserva
    (ANSI_PADDING ON). Se devuelven con un UPDATE por lotes y se comprueba cuántos quedaron."""
    cursor = conexion.cursor()
    for posicion, columna in enumerate(columnas):
        relleno = [(int(f[0]), len(f[posicion]) - len(f[posicion].rstrip(' '))) for f in filas
                   if isinstance(f[posicion], str) and f[posicion].endswith(' ')]
        if not relleno:
            continue
        for inicio in range(0, len(relleno), 1000):
            valores = ', '.join(f'({i}, {n})' for i, n in relleno[inicio:inicio + 1000])
            cursor.execute(f'UPDATE t SET [{columna}] = t.[{columna}] + SPACE(x.n) FROM dbo.[{tabla}] t '
                           f'JOIN (VALUES {valores}) x (id, n) ON x.id = t.id')
        cursor.execute(f'SELECT COUNT_BIG(*) FROM dbo.[{tabla}] WHERE DATALENGTH([{columna}]) > LEN([{columna}])')
        if cursor.fetchone()[0] != len(relleno):
            raise SystemExit(f'{tabla}.{columna}: no quedaron los {len(relleno)} valores con espacios finales')


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
        if columnas[0] != 'id' or not filas:
            continue
        paso = max(len(filas) // muestra, 1)
        for indice in range(0, len(filas), paso):
            esperado = filas[indice]
            cursor.execute(
                "DECLARE @sql nvarchar(4000) = N'SELECT * FROM dbo.' + QUOTENAME(%s) + N' WHERE id = @id';"
                " EXEC sp_executesql @sql, N'@id bigint', @id = %s", (tabla, esperado[0]))
            obtenido = cursor.fetchone()
            if [_normalizar(v) for v in obtenido] != [_normalizar(_valor_fecha(v)) for v in esperado]:
                raise SystemExit(f'{tabla} id={esperado[0]}: la fila cargada no es la generada\n'
                                 f'  base:     {obtenido}\n  generada: {esperado}')
    return conteos


def _valor_fecha(valor):
    return valor
