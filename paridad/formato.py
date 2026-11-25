"""Formato de los paquetes de universo y oráculo: JSON Lines con encabezado.

La primera línea es la lista de columnas; cada línea siguiente, una fila como lista de textos (o null). Es el mismo
formato con el que `legado/respaldo.py` captura las salidas publicadas. Los valores van como TEXTO EXACTO de lo que
entregó el motor: un decimal conserva su escala (`19.123400`), un `char(n)` su relleno y un `varchar` sus espacios
finales. Ninguna normalización ocurre al extraer; las que haga el TO-BE son parches documentados.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


def texto(valor) -> str | None:
    """Texto canónico de un valor del motor: el mismo para el legado y para el TO-BE."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        return '1' if valor else '0'
    if isinstance(valor, datetime):
        return valor.isoformat(sep='T', timespec='microseconds' if valor.microsecond else 'seconds')
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return format(valor, 'f')
    return str(valor)


def escribir(ruta: Path, columnas: list[str], filas: Iterable[Iterable]) -> int:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with ruta.open('w', encoding='utf-8', newline='\n') as archivo:
        archivo.write(json.dumps(columnas, ensure_ascii=False) + '\n')
        for fila in filas:
            archivo.write(json.dumps([texto(v) for v in fila], ensure_ascii=False) + '\n')
            n += 1
    return n


def leer(ruta: Path) -> tuple[list[str], list[list]]:
    with ruta.open(encoding='utf-8') as archivo:
        columnas = json.loads(archivo.readline())
        return columnas, [json.loads(linea) for linea in archivo if linea.strip()]


def leer_dicts(ruta: Path) -> Iterator[dict]:
    with ruta.open(encoding='utf-8') as archivo:
        columnas = json.loads(archivo.readline())
        for linea in archivo:
            if linea.strip():
                yield dict(zip(columnas, json.loads(linea)))


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()
