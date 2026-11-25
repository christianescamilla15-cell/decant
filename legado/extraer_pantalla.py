"""Camino del delta POR LA PANTALLA del legado (y no por la base), para S3.

Hay legados a los que sólo se llega por sus pantallas. Este extractor lee la lista del día y el detalle de cada
operación por HTTP, como lo haría quien no tiene acceso a la base, y deja un JSONL. Sirve para medir lo que ese
camino pierde frente al delta por base:
- la columna que ninguna pantalla imprime (`orden_pago.codigo_proposito`, T6) no llega;
- la lista corta en 200 operaciones por día (TOP sin ORDER BY, T1): las demás del día no se ven;
- la pantalla muestra la orden VIGENTE; los re-registros anteriores (T9) no aparecen.

    python -m legado.extraer_pantalla --fecha 2023-12-29 --salida legado/datos/delta_por_pantalla.jsonl
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class _Tablas(HTMLParser):
    """Junta las tablas de una página: id, renglones (texto de cada celda) y ligas a /operacion/<id>."""

    def __init__(self):
        super().__init__()
        self.tablas: list[dict] = []
        self.ligas: list[int] = []
        self._tabla = None
        self._renglon = None
        self._celda = None

    def handle_starttag(self, etiqueta, atributos):
        atributos = dict(atributos)
        if etiqueta == 'table':
            self._tabla = {'id': atributos.get('id'), 'renglones': []}
            self.tablas.append(self._tabla)
        elif etiqueta == 'tr' and self._tabla is not None:
            self._renglon = []
            self._tabla['renglones'].append(self._renglon)
        elif etiqueta in ('td', 'th') and self._renglon is not None:
            self._celda = []
        elif etiqueta == 'a':
            coincide = re.fullmatch(r'/operacion/(\d+)', atributos.get('href') or '')
            if coincide:
                self.ligas.append(int(coincide.group(1)))

    def handle_endtag(self, etiqueta):
        if etiqueta in ('td', 'th') and self._celda is not None:
            self._renglon.append(''.join(self._celda))
            self._celda = None
        elif etiqueta == 'table':
            self._tabla = None

    def handle_data(self, datos):
        if self._celda is not None:
            self._celda.append(datos)


def _get(url: str, ruta: str) -> str:
    partes = urlsplit(url)
    if partes.scheme != 'http' or not partes.hostname:
        raise SystemExit(f'URL de la pantalla no válida: {url}')
    conexion = http.client.HTTPConnection(partes.hostname, partes.port or 80, timeout=60)
    try:
        conexion.request('GET', ruta)
        respuesta = conexion.getresponse()
        cuerpo = respuesta.read().decode('utf-8')
    finally:
        conexion.close()
    if respuesta.status != 200:
        raise SystemExit(f'la pantalla respondió {respuesta.status} a {ruta}')
    return cuerpo


def leer_lista(html: str) -> list[int]:
    p = _Tablas()
    p.feed(html)
    return p.ligas


def leer_detalle(html: str) -> dict:
    p = _Tablas()
    p.feed(html)
    encabezado = {r[0]: r[1] for r in p.tablas[0]['renglones'] if len(r) == 2}
    rejillas = {}
    for t in p.tablas[1:]:
        if t['id']:
            titulos, *filas = t['renglones']
            rejillas[t['id']] = [dict(zip(titulos, f)) for f in filas]
    return {'encabezado': encabezado, 'rejillas': rejillas}


def extraer(url: str, fecha: str) -> list[dict]:
    ids = leer_lista(_get(url, f'/?fecha={fecha}'))
    return [{'id': i, **leer_detalle(_get(url, f'/operacion/{i}'))} for i in ids]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m legado.extraer_pantalla', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pantalla', default='http://127.0.0.1:8080/')
    parser.add_argument('--fecha', required=True)
    parser.add_argument('--salida', type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.fecha):
        parser.error('--fecha va como AAAA-MM-DD')
    operaciones = extraer(args.pantalla, args.fecha)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open('w', encoding='utf-8') as archivo:
        for op in operaciones:
            archivo.write(json.dumps(op, ensure_ascii=False) + '\n')
    campos = sorted({c for op in operaciones for c in op['encabezado']})
    print(f'{len(operaciones)} operaciones del {args.fecha} leídas por la pantalla → {args.salida}')
    print(f"  campos visibles: {len(campos)} · ¿codigo_proposito? {'sí' if 'codigo_proposito' in campos else 'no'}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
