"""Criterio de salida NO tautológico: el respaldo restaurado tiene que cuadrar con lo que el legado decía de sí
mismo en el instante del respaldo (el manifiesto), no consigo mismo.

1. Cada tabla: COUNT y MAX(id) del restaurado = los del manifiesto; y los contadores (folios) también.
2. Cada cifra de la pantalla: hay que AVERIGUAR qué cuenta. Se prueban COUNT(*) y COUNT(DISTINCT columna) de su
   tabla; si ninguna coincide, el respaldo no es lo que la pantalla publicaba.
3. Cada salida publicada (reporte, lista): se re-corre sobre el restaurado y se compara contra la captura del
   respaldo: mismo contenido, 0 inversiones en el orden que promete la consulta, y el desorden de los empates
   medido (ése es el piso de la paridad). Una salida SIN orden prometido (TOP sin ORDER BY) puede devolver otras
   filas en otra instancia: eso no invalida el respaldo (las tablas ya cuadraron), se mide y se reporta como
   «no reproducible».
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from radiografia import orden

_NOMBRE = re.compile(r'^[A-Za-z_][\w]*\.[A-Za-z_][\w]*$')
_SIN_DISTINCT = frozenset(('text', 'ntext', 'image', 'xml', 'geography', 'geometry', 'hierarchyid', 'sql_variant'))


def _partes(tabla: str) -> tuple[str, str]:
    if not _NOMBRE.match(tabla):
        raise ValueError(f'nombre de tabla no válido: {tabla!r}')
    esquema, nombre = tabla.split('.')
    return esquema, nombre


def cuadre_tablas(cursor, manifiesto: dict, filas: dict[str, int], corte: list[dict]) -> list[dict]:
    maximos = {c['tabla']: (c['identidad'] or {}).get('max') for c in corte}
    resultado = []
    for tabla, esperado in sorted(manifiesto.get('tablas', {}).items()):
        medido = {'filas': filas.get(tabla), 'max_id': maximos.get(tabla)}
        resultado.append({'objeto': tabla, 'manifiesto': esperado, 'restaurado': medido, 'cuadra': medido == esperado})
    for tabla, contador in sorted(manifiesto.get('contadores', {}).items()):
        esquema, nombre = _partes(tabla)
        cursor.execute(
            "DECLARE @sql nvarchar(max) = N'SELECT ' + QUOTENAME(%s) + N', ' + QUOTENAME(%s) + N' FROM ' "
            "+ QUOTENAME(%s) + N'.' + QUOTENAME(%s); EXEC sp_executesql @sql",
            (contador['llave'], contador['valor'], esquema, nombre))
        medido = {str(llave).strip(): valor for llave, valor in cursor.fetchall()}
        resultado.append({'objeto': f"{tabla}.{contador['valor']}", 'manifiesto': contador['filas'],
                          'restaurado': medido, 'cuadra': medido == contador['filas']})
    return resultado


def interpretar_cifra(cursor, tabla: str, valor: int, columnas: list[dict]) -> dict:
    """¿Qué cuenta la cifra de la pantalla? Prueba COUNT(*) y COUNT(DISTINCT c) de cada columna."""
    esquema, nombre = _partes(tabla)
    cursor.execute("DECLARE @sql nvarchar(max) = N'SELECT COUNT_BIG(*) FROM ' + QUOTENAME(%s) + N'.' + "
                   "QUOTENAME(%s); EXEC sp_executesql @sql", (esquema, nombre))
    filas = cursor.fetchone()[0]
    interpretaciones = ['COUNT(*)'] if filas == valor else []
    for c in columnas:
        if c['tipo'] in _SIN_DISTINCT:
            continue
        cursor.execute("DECLARE @sql nvarchar(max) = N'SELECT COUNT_BIG(DISTINCT ' + QUOTENAME(%s) + N') FROM ' + "
                       "QUOTENAME(%s) + N'.' + QUOTENAME(%s); EXEC sp_executesql @sql",
                       (c['columna'], esquema, nombre))
        if cursor.fetchone()[0] == valor:
            interpretaciones.append(f"COUNT(DISTINCT {c['columna']})")
    if interpretaciones and interpretaciones[0] != 'COUNT(*)':
        lectura = (f'la pantalla NO cuenta filas ({filas:,}): cuenta valores distintos; {filas - valor:,} filas '
                   f'repiten la llave')
    elif interpretaciones:
        lectura = 'la pantalla cuenta filas'
    else:
        lectura = 'ninguna interpretación probada da la cifra: el respaldo no es lo que la pantalla publicaba'
    return {'tabla': tabla, 'valor': valor, 'filas': filas, 'interpretaciones': interpretaciones,
            'lectura': lectura, 'cumple': bool(interpretaciones)}


def _texto(valor) -> str | None:
    return None if valor is None else str(valor)


def recorrer(cursor, procedimiento: str, parametros: list, conjunto: int) -> tuple[list[str], list[list]]:
    if not _NOMBRE.match(procedimiento):
        raise ValueError(f'nombre de procedimiento no válido: {procedimiento!r}')
    cursor.callproc(procedimiento, tuple(parametros))
    indice = 0
    while True:
        if cursor.description:
            if indice == conjunto:
                return [d[0] for d in cursor.description], [[_texto(v) for v in f] for f in cursor.fetchall()]
            cursor.fetchall()
            indice += 1
        if not cursor.nextset():
            raise ValueError(f'{procedimiento} no devolvió el conjunto {conjunto}')


def leer_captura(ruta: Path) -> tuple[list[str], list[list]]:
    renglones = ruta.read_text(encoding='utf-8').splitlines()
    return json.loads(renglones[0]), [json.loads(r) for r in renglones[1:]]


def salidas(cursor, manifiesto: dict, carpeta: Path, sha256) -> list[dict]:
    resultado = []
    for s in manifiesto.get('salidas', []):
        ruta = carpeta / s['archivo']
        if sha256(ruta) != s['sha256']:
            raise SystemExit(f"{s['archivo']}: el sha256 no coincide con el manifiesto")
        columnas, capturada = leer_captura(ruta)
        columnas_re, recorrida = recorrer(cursor, s['procedimiento'], s['parametros'], s['conjunto'])
        if columnas_re != columnas:
            raise SystemExit(f"{s['nombre']}: las columnas de la re-corrida no son las de la captura")
        natural = [columnas.index(c) for c in s['llave_natural']]
        orden_ = [columnas.index(c) for c in s['llave_orden']]
        medida = orden.comparar([tuple(f) for f in capturada], [tuple(f) for f in recorrida], natural, orden_)
        con_contrato = bool(s['llave_orden'])
        resultado.append({'nombre': s['nombre'], 'procedimiento': s['procedimiento'], 'parametros': s['parametros'],
                          'llave_natural': s['llave_natural'], 'llave_orden': s['llave_orden'], **medida,
                          'reproducible': medida['mismo_contenido'],
                          'cumple': (medida['mismo_contenido'] and medida['inversiones_contrato'] == 0)
                          if con_contrato else True})
    return resultado
