"""Pantalla del legado (sólo lectura): lista de operaciones del día y detalle de una operación.

Como la pantalla original, NO consulta tablas: llama a `sp_lista_operaciones` y a `sp_detalle_operacion`.
El encabezado publica el total de operaciones registradas; es la cifra contra la que se valida un respaldo.

    python -m legado pantalla --puerto 8080
"""
from __future__ import annotations

import html
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from legado.conexion import conectar

# Rejillas del detalle: qué conjunto de resultados de sp_detalle_operacion pinta cada una.
# sp_detalle_operacion devuelve 0 = encabezado, 1 = partidas de dbo.partida_solicitada, 2 = de dbo.partida_liquidada.
REJILLAS = (
    {'id': 'rejilla-liquidado', 'titulo': 'Liquidado por el corresponsal', 'conjunto': 1},
    {'id': 'rejilla-solicitado', 'titulo': 'Solicitado por el cliente', 'conjunto': 2},
)

COLUMNAS_LISTA = (('folio', 'Folio'), ('fecha_operacion', 'Fecha'), ('sucursal', 'Suc.'), ('canal', 'Canal'),
                  ('cliente', 'Cliente'), ('tipo', 'C/V'), ('moneda', 'Moneda'), ('monto_divisa', 'Monto'),
                  ('tipo_cambio', 'T.C.'), ('monto_mxn', 'Pesos'), ('estatus', 'Estatus'))
COLUMNAS_PARTIDA = (('renglon', '#'), ('concepto', 'Concepto'), ('moneda', 'Moneda'), ('monto', 'Monto'),
                    ('fecha_hora', 'Fecha y hora'), ('referencia', 'Referencia'))
ESTILO = ('body{font-family:Verdana,sans-serif;font-size:13px;margin:16px;background:#f4f4ef;color:#222}'
          'table{border-collapse:collapse;margin:8px 0 18px}td,th{border:1px solid #999;padding:2px 6px}'
          'th{background:#335;color:#fff}h1{font-size:18px}h2{font-size:15px}.total{font-weight:bold}')


def _e(valor) -> str:
    return '' if valor is None else html.escape(str(valor))


def _celda(fila: dict, columna: str) -> str:
    return _e(fila.get(columna))


def _tabla(filas: list[dict], columnas, id_html: str = '', celda=_celda) -> str:
    cabeza = ''.join(f'<th>{_e(titulo)}</th>' for _c, titulo in columnas)
    cuerpo = ''.join('<tr>' + ''.join(f'<td>{celda(f, c)}</td>' for c, _t in columnas) + '</tr>' for f in filas)
    atributo = f' id="{_e(id_html)}"' if id_html else ''
    return f'<table{atributo}><tr>{cabeza}</tr>{cuerpo}</table>'


def _pagina(titulo: str, cuerpo: str) -> bytes:
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{_e(titulo)}</title>'
            f'<style>{ESTILO}</style></head><body><h1>BFN · Divisas · {_e(titulo)}</h1>{cuerpo}</body></html>'
            ).encode()


def _conjuntos(cursor) -> list[list[dict]]:
    resultado = []
    while True:
        if cursor.description:
            nombres = [d[0] for d in cursor.description]
            resultado.append([dict(zip(nombres, fila)) for fila in cursor.fetchall()])
        if not cursor.nextset():
            return resultado


def lista(fecha: date | None) -> bytes:
    with conectar() as conexion:
        cursor = conexion.cursor()
        cursor.execute('EXEC dbo.sp_lista_operaciones @fecha = %s', (fecha,))
        total, filas = _conjuntos(cursor)
    n = total[0]['total_operaciones']

    def celda(fila: dict, columna: str) -> str:
        if columna == 'folio':
            return f'<a href="/operacion/{int(fila["id"])}">{_e(fila["folio"])}</a>'
        return _e(fila.get(columna))

    tabla = _tabla(filas, COLUMNAS_LISTA, celda=celda)
    cuerpo = (f'<p class="total" data-total-operaciones="{int(n)}">Operaciones registradas: {int(n):,}</p>'
              f'<p>{len(filas)} operaciones del día</p>{tabla}')
    return _pagina('Operaciones', cuerpo)


def detalle(operacion_id: int) -> bytes | None:
    with conectar() as conexion:
        cursor = conexion.cursor()
        cursor.execute('EXEC dbo.sp_detalle_operacion @operacion_id = %s', (operacion_id,))
        conjuntos = _conjuntos(cursor)
    if not conjuntos or not conjuntos[0]:
        return None
    encabezado = conjuntos[0][0]
    datos = ''.join(f'<tr><th>{_e(k)}</th><td>{_e(v)}</td></tr>' for k, v in encabezado.items())
    cuerpo = f'<p><a href="/">← lista</a></p><table>{datos}</table>'
    for rejilla in REJILLAS:
        cuerpo += f'<h2>{_e(rejilla["titulo"])}</h2>'
        cuerpo += _tabla(conjuntos[rejilla['conjunto']], COLUMNAS_PARTIDA, rejilla['id'])
    return _pagina(f'Operación {encabezado["folio"]}', cuerpo)


class Manejador(BaseHTTPRequestHandler):
    server_version = 'BFN-Pantalla/1.0'

    def do_GET(self):          # noqa: N802 (nombre que exige http.server)
        partes = urlsplit(self.path)
        if partes.path == '/salud':
            return self._responder(200, b'ok', 'text/plain')
        if partes.path == '/':
            valor = parse_qs(partes.query).get('fecha', [''])[0]
            try:
                fecha = date.fromisoformat(valor) if valor else None
            except ValueError:
                return self._responder(400, b'fecha invalida', 'text/plain')
            return self._responder(200, lista(fecha))
        coincide = re.fullmatch(r'/operacion/(\d{1,10})', partes.path)
        if coincide:
            pagina = detalle(int(coincide.group(1)))
            if pagina is not None:
                return self._responder(200, pagina)
        return self._responder(404, b'no encontrado', 'text/plain')

    def _responder(self, codigo: int, cuerpo: bytes, tipo: str = 'text/html; charset=utf-8'):
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato, *args):
        pass


def servir(puerto: int = 8080, anfitrion: str = '127.0.0.1') -> None:
    servidor = ThreadingHTTPServer((anfitrion, puerto), Manejador)
    print(f'pantalla del legado en http://{anfitrion}:{puerto}/', flush=True)
    servidor.serve_forever()
