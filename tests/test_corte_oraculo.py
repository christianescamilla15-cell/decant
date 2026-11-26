"""Oráculo del corte (S3 paso 5, ADR 0014; criterio 2), sin base. La captura en el congelamiento y la re-corrida del
TO-BE sobre la base de referencia corren en el CI (`corte/estado_ci.py`, job `estado` de `carga.yml`)."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from corte import codigo, oraculo, trampas
from legado.pantalla import app
from legado.vivo.__main__ import oraculo_al_congelar

RAIZ = Path(__file__).resolve().parent.parent
LEGADO = '\n'.join(p.read_text(encoding='utf-8') for p in sorted((RAIZ / 'legado' / 'sql').glob('*.sql')))


@pytest.fixture(scope='module')
def inv():
    return codigo.inventario()


def test_todo_objeto_de_lectura_del_inventario_tiene_caso(inv):
    lectores = [o['id'] for o in inv['objetos'] if o['acceso'] == 'lee']
    assert len(lectores) == 12                      # 9 procedimientos, 2 vistas y la pantalla
    assert oraculo.n_de_n(lectores)['verde']
    # control negativo: un lector nuevo sin caso
    r = oraculo.n_de_n([*lectores, 'dbo.sp_lector_nuevo'])
    assert not r['verde'] and r['faltas'] == ['dbo.sp_lector_nuevo: objeto de lectura sin caso en el oráculo']
    assert any(c.borde for c in oraculo.todos())
    assert {c.objeto for c in oraculo.todos() if c.borde} >= {
        'dbo.sp_reporte_posicion', 'dbo.sp_tablero_corresponsales', 'dbo.sp_liquidaciones_recientes'}


def test_cada_caso_tiene_su_re_corrida_en_el_tobe_con_los_mismos_argumentos():
    for c in oraculo.CASOS:
        consultas = oraculo.TOBE[c.objeto]
        pedidos = {m for q in consultas for m in re.findall(r'%\((\w+)\)s', q)} - {'reloj'}
        assert pedidos <= set(c.argumentos), (c.id, pedidos)
        assert set(re.findall(r'%\((\w+)\)s', c.legado)) <= set(c.argumentos), c.id
    # el reloj ENTRA en los dos objetos que lo usan, y en ningún otro
    con_reloj = {o for o, qs in oraculo.TOBE.items() if any('%(reloj)s' in q for q in qs)}
    assert con_reloj == {'dbo.sp_antiguedad_ordenes', 'dbo.sp_ordenes_por_vencer'}
    assert not any(re.search(r'now\(\)|current_timestamp|getdate', q, re.I) for qs in oraculo.TOBE.values() for q in qs)


def test_el_orden_prometido_sale_del_codigo_del_legado():
    """Cada orden prometido está escrito en el objeto (o en la vista que lee): no se lo inventa el oráculo."""
    for c in oraculo.todos():
        if not c.orden:
            continue
        orden = c.de_donde.split(' de ')[0]
        assert orden in LEGADO, (c.id, orden)
    vista = re.search(r'CREATE OR ALTER VIEW dbo\.vw_liquidaciones_recientes.*?GO', LEGADO, re.S).group()
    assert 'TOP 100 PERCENT' in vista and 'ORDER BY s.fecha_hora DESC' in vista


def test_la_copia_literal_del_tablero_sólo_cambia_las_horas():
    literal = oraculo.LITERAL['dbo.sp_tablero_corresponsales'][0]
    tobe = oraculo.TOBE['dbo.sp_tablero_corresponsales'][0]
    assert literal.replace('avg(', 'X(').split('AS horas_promedio_envio')[1] == \
        tobe.replace('avg(', 'X(').split('AS horas_promedio_envio')[1]
    assert 'trunc(avg(' in tobe and 'trunc(avg(' not in literal and 'avg(' in literal


def test_los_conjuntos_se_comparan_como_multiconjuntos_con_numeros_por_valor():
    a = oraculo.conjunto(['A', 'b'], [(Decimal('1.50'), 'x  '), (2, 'y')])
    b = oraculo.conjunto(['a', 'B'], [(2, 'y'), (Decimal('1.5000'), 'x  ')])
    assert a['columnas'] == ['a', 'b'] and oraculo.comparar_conjunto(a, b)['coincide']
    # los espacios finales y las mayúsculas sí cuentan (r1-T3 en PostgreSQL)
    c = oraculo.conjunto(['a', 'b'], [(Decimal('1.5'), 'x'), (2, 'Y')])
    r = oraculo.comparar_conjunto(a, c)
    assert not r['coincide'] and r['solo_legado'] == 2 and r['solo_tobe'] == 2
    # un renglón repetido cuenta dos veces
    d = oraculo.conjunto(['a', 'b'], [(2, 'y'), (2, 'y'), (Decimal('1.5'), 'x  ')])
    assert oraculo.comparar_conjunto(a, d)['solo_tobe'] == 1
    assert oraculo.texto(datetime(2023, 12, 29, 6, 0, 0, 3000)) == '2023-12-29 06:00:00.003'
    assert oraculo.texto(date(2023, 12, 1)) == '2023-12-01' and oraculo.texto(True) == '1'


def test_el_orden_prometido_cuenta_los_pares_al_reves_y_no_los_empates():
    filas = [(datetime(2023, 12, 3), 'a'), (datetime(2023, 12, 3), 'b'), (datetime(2023, 12, 5), 'c'),
             (datetime(2023, 12, 1), 'd')]
    c = oraculo.conjunto(['fecha_hora', 'x'], filas)
    r = oraculo.orden_incumplido(c, (('fecha_hora', 'desc'),))
    assert r['pares'] == 3 and r['incumplidos'] == 1 and r['primero']['par'] == 2
    assert oraculo.orden_incumplido(c, (('fecha_hora', 'asc'),))['incumplidos'] == 1
    assert oraculo.orden_incumplido(c, ())['incumplidos'] == 0


def test_las_fechas_representativas_incluyen_el_borde_del_cierre_de_mes():
    assert oraculo.fechas({'fecha_negocio': '2023-12-29'}) == {
        'dia_corte': '2023-12-29', 'inicio_mes': '2023-12-01', 'fin_mes_anterior': '2023-11-30',
        'inicio_mes_anterior': '2023-11-01'}
    caso = next(c for c in oraculo.CASOS if c.objeto == 'dbo.sp_antiguedad_ordenes' and c.argumentos['bic'])
    assert oraculo.argumentos(caso, {'bic_enviadas': 'FICTUS33XXX'}) == {'dias': 3, 'bic': 'FICTUS33XXX'}


def test_la_pantalla_se_lee_como_la_pinta_el_legado():
    """La misma forma para la pantalla del legado (HTML por HTTP) y para la del TO-BE (los mismos helpers): totales
    del encabezado, la lista y, en el detalle, el encabezado y las dos rejillas por su binding (T4)."""
    filas = [{'id': 7, 'folio': 'FX-000000007', 'fecha_operacion': datetime(2023, 12, 29, 9), 'sucursal': '0001',
              'canal': 'EN_LINEA', 'cliente': 'Ana & Cía', 'tipo': 'V', 'moneda': 'USD',
              'monto_divisa': Decimal('10.50'), 'tipo_cambio': Decimal('17.000000'), 'monto_mxn': Decimal('178.50'),
              'estatus': 'CONCERTADA'}]
    html = ('<p class="total" data-total-operaciones="412556">x</p><p class="total" data-total-ordenes="150723">x</p>'
            + app._tabla(filas, app.COLUMNAS_LISTA))
    lista = oraculo.pantalla_en_conjuntos(html)
    assert lista[0]['filas'] == [['412556', '150723']] and lista[1]['columnas'][0] == 'folio'
    assert lista[1]['filas'][0][4] == 'Ana & Cía' and lista[1]['filas'][0][7] == '10.50'
    detalle = ('<table><tr><th>folio</th><td>FX-1</td></tr><tr><th>horas_liquidacion</th><td></td></tr></table>'
               + app._tabla([], app.COLUMNAS_PARTIDA, 'rejilla-liquidado')
               + app._tabla([{'renglon': 1, 'concepto': 'PRINCIPAL'}], app.COLUMNAS_PARTIDA, 'rejilla-solicitado'))
    d = oraculo.pantalla_en_conjuntos(detalle)
    assert d[0]['columnas'] == ['campo', 'valor'] and d[0]['filas'] == [['folio', 'FX-1'], ['horas_liquidacion', '']]
    assert len(d) == 3 and d[2]['filas'][0][:2] == ['1', 'PRINCIPAL']


def test_el_vivo_sólo_captura_el_oraculo_si_se_lo_piden(monkeypatch):
    """El job `legado` observa el ciclo para la puerta: lo que ejecuta el arnés no puede contarse como consumidor."""
    monkeypatch.delenv('DECANT_ORACULO', raising=False)
    assert oraculo_al_congelar(object(), {'fecha_negocio': '2023-12-29'}) is None


def test_las_seis_trampas_observables_viven_en_objetos_con_caso_o_escenario():
    cat = trampas.catalogo()
    assert len(cat) == 9 and set(trampas.OBSERVABLES) | set(trampas.LATENTES) | set(trampas.YA_EN_S2) == set(cat)
    con_caso = {c.objeto for c in oraculo.todos()}
    escritores = {'dbo.sp_reflejar_estatus_operacion', 'dbo.sp_alta_manual_orden'}
    for t in (*trampas.OBSERVABLES, *trampas.LATENTES):
        assert set(cat[t]['objetos']) <= con_caso | escritores, t
    assert trampas.nombrar('dbo.sp_alta_manual_orden', cat) == [
        'r3-T3 (@@IDENTITY después de insertar en una tabla con trigger que inserta en otra con identidad)']
    assert trampas.por_objeto(cat)['dbo.vw_liquidaciones_recientes'] == ['r2-T1']
