"""Piezas del legado que no necesitan la base: pantalla (con un doble de la conexión), guion del legado vivo,
medición del daño de bcp y lectura de la cifra de la pantalla."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from legado import bcp, respaldo
from legado.conexion import lotes
from legado.pantalla import app
from legado.vivo.__main__ import ejecutar


class CursorFalso:
    """Devuelve conjuntos de resultados fijos, como pymssql con varios SELECT."""

    def __init__(self, conjuntos):
        self.conjuntos = conjuntos
        self.indice = 0
        self.ejecutado = []

    @property
    def description(self):
        return [(c,) for c in self.conjuntos[self.indice][0]] if self.indice < len(self.conjuntos) else None

    def execute(self, sql, parametros=None):
        self.ejecutado.append((sql, parametros))

    def fetchall(self):
        return self.conjuntos[self.indice][1]

    def fetchone(self):
        return self.conjuntos[self.indice][1][0]

    def nextset(self):
        self.indice += 1
        return self.indice < len(self.conjuntos)


class ConexionFalsa:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_lotes_se_separan_por_go_como_en_sqlcmd():
    assert lotes('USE x;\nGO\nCREATE VIEW v AS SELECT 1\ngo\n\n') == ['USE x;', 'CREATE VIEW v AS SELECT 1']


def test_la_pantalla_publica_el_total_y_escapa_lo_que_viene_de_la_base(monkeypatch):
    cursor = CursorFalso([(['total_operaciones', 'total_ordenes'], [(412130, 150724)]),
                          (['id', 'folio', 'cliente'], [(7, 'FX-000000007', '<script>alert(1)</script>')])])
    monkeypatch.setattr(app, 'conectar', lambda: ConexionFalsa(cursor))
    pagina = app.lista(None).decode('utf-8')
    assert 'data-total-operaciones="412130"' in pagina and 'data-total-ordenes="150724"' in pagina
    assert '&lt;script&gt;' in pagina and '<script>' not in pagina
    assert '<a href="/operacion/7">FX-000000007</a>' in pagina
    assert cursor.ejecutado[0][0].startswith('EXEC dbo.sp_lista_operaciones')


def test_el_detalle_pinta_cada_conjunto_en_su_rejilla(monkeypatch):
    columnas = ['renglon', 'concepto', 'moneda', 'monto', 'fecha_hora', 'referencia']
    cursor = CursorFalso([(['folio'], [('FX-1',)]),
                          (columnas, [(1, 'ABONO', 'USD', 99, None, 'FICT1')]),
                          (columnas, [(1, 'PRINCIPAL', 'USD', 100, None, 'OP-1')])])
    monkeypatch.setattr(app, 'conectar', lambda: ConexionFalsa(cursor))
    pagina = app.detalle(1).decode('utf-8')
    liquidado = pagina[pagina.index('id="rejilla-liquidado"'):pagina.index('id="rejilla-solicitado"')]
    assert 'ABONO' in liquidado and 'PRINCIPAL' not in liquidado


def test_operacion_inexistente_no_tiene_detalle(monkeypatch):
    monkeypatch.setattr(app, 'conectar', lambda: ConexionFalsa(CursorFalso([(['folio'], [])])))
    assert app.detalle(999) is None


def test_el_guion_vivo_enlaza_la_orden_con_la_operacion_que_acaba_de_crear():
    cursor = CursorFalso([(['id'], [(412131,)])])
    ids: dict[str, int] = {}
    args_op = {k: None for k in ('fecha_operacion', 'sucursal', 'canal', 'cliente', 'cuenta_clabe', 'tipo',
                                 'moneda', 'monto_divisa', 'tipo_cambio_referencia', 'tipo_cambio')}
    assert ejecutar({'accion': 'operacion', 'ref': 'op:5', 'args': args_op}, cursor, ids) == 412131
    args_orden = {k: None for k in ('uetr', 'referencia_mt103', 'fecha_registro', 'fecha_envio', 'fecha_valor',
                                    'bic_corresponsal', 'bic_intermediario', 'beneficiario', 'cuenta_beneficiario',
                                    'moneda', 'monto', 'gastos', 'codigo_proposito')}
    ejecutar({'accion': 'orden', 'ref': 'doc:x', 'args': {**args_orden, 'operacion_id': 'op:5'}}, cursor, ids)
    assert cursor.ejecutado[-1][1][0] == 412131


def test_el_guion_vivo_rechaza_acciones_desconocidas():
    with pytest.raises(ValueError):
        ejecutar({'accion': 'borrar_todo', 'args': {}}, CursorFalso([]), {})


def test_bcp_cuenta_signos_de_interrogacion_y_sustituciones_silenciosas():
    verdad = 'id|nombre\n1|José\n2|Łódź\n3|ARTESANÃ\x8dAS\n'.encode('utf-16')
    ansi = 'id|nombre\n1|José\n2|Lódz\n3|ARTESANÃ?AS\n'.encode('cp1252')
    r = bcp.comparar(verdad, ansi)
    assert r == {'filas': 4, 'distintas_en_1252': 2, 'con_signos_de_interrogacion': 1, 'ilegibles_como_utf8': 3}


class _Pantalla(BaseHTTPRequestHandler):
    def do_GET(self):          # noqa: N802
        cuerpo = (b'<p class="total" data-total-operaciones="412130">Operaciones registradas: 412,130</p>'
                  b'<p class="total" data-total-ordenes="150724">\xc3\x93rdenes de pago: 150,724</p>')
        self.send_response(200)
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *_):
        pass


def test_el_respaldo_lee_la_cifra_que_publica_la_pantalla():
    servidor = ThreadingHTTPServer(('127.0.0.1', 0), _Pantalla)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        assert respaldo.cifras_pantalla(f'http://127.0.0.1:{servidor.server_port}/') == {
            'Operaciones registradas': 412130, 'Órdenes de pago': 150724}
    finally:
        servidor.shutdown()


def test_el_respaldo_no_acepta_otra_cosa_que_http():
    with pytest.raises(SystemExit):
        respaldo.cifra_pantalla('file:///etc/passwd')


def test_el_delta_por_la_pantalla_no_trae_la_columna_que_la_pantalla_no_imprime(monkeypatch):
    """C12: lo que lee la pantalla es lo que S3 tendría si extrajera por ella y no por la base."""
    from legado import extraer_pantalla
    encabezado = ['id', 'folio', 'cliente', 'folio_orden', 'uetr', 'monto_orden', 'estatus_orden']
    columnas = ['renglon', 'concepto', 'moneda', 'monto', 'fecha_hora', 'referencia']
    cursor = CursorFalso([(encabezado, [(9, 'FX-9', 'ANA', 'OP-1', 'u-1', 100, 'CONCILIADA')]),
                          (columnas, [(1, 'ABONO', 'USD', 99, None, 'FICT1')]),
                          (columnas, [(1, 'PRINCIPAL', 'USD', 100, None, 'OP-1')])])
    monkeypatch.setattr(app, 'conectar', lambda: ConexionFalsa(cursor))
    leido = extraer_pantalla.leer_detalle(app.detalle(9).decode('utf-8'))
    assert leido['encabezado']['uetr'] == 'u-1' and 'codigo_proposito' not in leido['encabezado']
    assert leido['rejillas']['rejilla-liquidado'][0]['Concepto'] == 'ABONO'


def test_la_lista_de_la_pantalla_entrega_los_ids_de_sus_ligas(monkeypatch):
    from legado import extraer_pantalla
    cursor = CursorFalso([(['total_operaciones', 'total_ordenes'], [(3, 1)]),
                          (['id', 'folio'], [(7, 'FX-7'), (8, 'FX-8')])])
    monkeypatch.setattr(app, 'conectar', lambda: ConexionFalsa(cursor))
    assert extraer_pantalla.leer_lista(app.lista(None).decode('utf-8')) == [7, 8]
