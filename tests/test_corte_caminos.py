"""El corte por dos caminos (S3, criterio 3), sin base: el cálculo de conjuntos, los límites de cada reloj y la
cobertura contra el inventario del código. Cada prueba trae su control negativo."""
from __future__ import annotations

import re
from datetime import datetime

import pytest

from corte import caminos, codigo
from legado.generador import Config


def sellos(pares):
    return [(i, s) for i, s in pares]


def test_la_discrepancia_es_diferencia_de_conjuntos_y_nombra_cada_id():
    identidad = caminos.por_identidad([11, 12, 13, 14], corte=10, congelamiento=13)
    assert (identidad.delta, identidad.posterior) == ({11, 12, 13}, {14})
    iguales = caminos.por_sello(sellos([(11, 1), (12, 2), (13, 3), (14, 9)]), desde=0, hasta=5)
    assert caminos.comparar(identidad, iguales)['coincide']
    # control negativo: el sello pierde el 12 y trae un 20 que la identidad no tiene: falla nombrando los dos
    otro = caminos.por_sello(sellos([(11, 1), (13, 3), (14, 9), (20, 4)]), desde=0, hasta=5)
    r = caminos.comparar(identidad, otro)
    assert not r['coincide']
    assert r['mayores_al_corte']['muestra_solo_por_identidad'] == [12]
    assert r['mayores_al_corte']['muestra_solo_por_sellos'] == [20]


def test_dos_errores_opuestos_se_cancelan_en_la_cuenta_pero_no_en_los_conjuntos():
    identidad = caminos.por_identidad([11, 12, 13], corte=10, congelamiento=13)
    sello = caminos.por_sello(sellos([(11, 1), (12, 2), (99, 3)]), desde=0, hasta=5)     # falta 13, sobra 99
    assert len(identidad.mayores_al_corte()) == len(sello.mayores_al_corte())           # la cuenta cuadra
    assert not caminos.comparar(identidad, sello)['coincide']                           # el conjunto no


def test_un_hueco_de_identidad_no_es_discrepancia():
    # la inserción del 103 se revirtió: la identidad la consumió y no hay fila; el sello tampoco la tiene
    ids = [101, 102, 104, 105]
    identidad = caminos.por_identidad(ids, corte=100, congelamiento=104)
    sello = caminos.por_sello(sellos([(101, 1), (102, 2), (104, 3), (105, 7)]), desde=0, hasta=5)
    assert caminos.comparar(identidad, sello)['coincide']
    assert caminos.huecos(ids, 100, 105) == [103]
    # la cuenta ingenua (MAX(id) - corte) diría que falta una fila
    assert 105 - 100 != len(sello.mayores_al_corte())
    # control negativo: si el sello tampoco tiene el 104, ya no es un hueco, es una fila que un camino no ve
    sin_104 = caminos.por_sello(sellos([(101, 1), (102, 2), (105, 7)]), desde=0, hasta=5)
    assert caminos.comparar(identidad, sin_104)['mayores_al_corte']['muestra_solo_por_identidad'] == [104]


def test_la_frontera_del_congelamiento_tambien_se_compara():
    identidad = caminos.por_identidad([11, 12], corte=10, congelamiento=11)
    # el 11 selló DESPUÉS del congelamiento aunque su id es del delta: mismo conjunto «mayores al corte», otra clase
    sello = caminos.por_sello(sellos([(11, 8), (12, 9)]), desde=0, hasta=5)
    r = caminos.comparar(identidad, sello)
    assert r['mayores_al_corte']['solo_por_identidad'] == 0 and r['mayores_al_corte']['solo_por_sellos'] == 0
    assert not r['coincide']
    assert r['delta']['muestra_solo_por_identidad'] == [11] and r['posterior']['muestra_solo_por_sellos'] == [11]


def test_el_camino_por_fecha_de_negocio_pierde_las_altas_fechadas_hacia_atras():
    """La sucursal reenvía hoy, después del corte, operaciones con fecha de AYER: id y folio nuevos, fecha vieja."""
    corte, congelamiento = 100, 110
    ayer, hoy = datetime(2023, 12, 28, 11), datetime(2023, 12, 29, 10)
    filas = {i: (i, hoy) for i in range(101, 111)} | {i: (i, ayer) for i in (104, 105)}      # 104 y 105: reenvío
    identidad = caminos.por_identidad(list(filas), corte, congelamiento)
    desde, hasta = datetime(2023, 12, 29, 6), datetime(2023, 12, 29, 18)
    por_fecha = caminos.por_sello(((i, f) for i, f in filas.values()), desde, hasta)
    r = caminos.comparar(identidad, por_fecha)
    assert not r['coincide'] and r['mayores_al_corte']['muestra_solo_por_identidad'] == [104, 105]
    # el folio (consumible tomado al registrar) sí las ve
    por_folio = caminos.por_sello(((i, 5000 + i) for i in filas), 5000 + corte, 5000 + congelamiento)
    assert caminos.comparar(identidad, por_folio)['coincide']


def test_las_tablas_salen_del_inventario_y_una_nueva_sin_camino_detiene_el_corte():
    tablas = codigo.inventario()['tablas']
    cob = caminos.cobertura(tablas)
    assert cob['con_identidad'] == ['dbo.bitacora', 'dbo.operacion', 'dbo.orden_pago', 'dbo.partida_liquidada',
                                    'dbo.partida_solicitada']
    assert cob['sin_identidad'] == ['dbo.folio', 'dbo.moneda']
    assert cob['sin_camino'] == [] and cob['caminos_huerfanos'] == []
    # control negativo: una tabla nueva con identidad en el código, sin camino por sellos, y una que desaparece
    otras = {**tablas, 'dbo.ajuste': {'identidad': True}}
    otras.pop('dbo.partida_solicitada')
    cob = caminos.cobertura(otras)
    assert cob['sin_camino'] == ['dbo.ajuste']
    assert cob['caminos_huerfanos'] == ['dbo.partida_solicitada · bitácora (liquidación de su orden)']
    faltas = caminos.veredicto({'cobertura': cob, 'tablas': {}})
    assert any('dbo.ajuste' in f for f in faltas) and any('huérfano' in f for f in faltas)


def test_el_control_negativo_no_cuenta_como_camino():
    tablas = {'dbo.operacion': {'identidad': True}}
    solo_negativo = tuple(c for c in caminos.CAMINOS if c.tabla == 'dbo.operacion' and c.control_negativo)
    assert caminos.cobertura(tablas, solo_negativo)['sin_camino'] == ['dbo.operacion']
    assert caminos.cobertura(tablas, tuple(c for c in caminos.CAMINOS if c.tabla == 'dbo.operacion'))[
        'sin_camino'] == []


@pytest.mark.parametrize('camino', caminos.CAMINOS, ids=lambda c: f'{c.tabla}·{c.reloj}')
def test_cada_consulta_es_un_literal_de_su_tabla_con_un_solo_parametro(camino):
    assert camino.consulta.count('%s') == 1
    assert re.search(rf'\b{camino.tabla.split(".")[1]}\b', camino.consulta)
    assert '%' not in camino.consulta.replace('%s', '').replace('%%', '')     # pymssql formatea con %
    assert camino.reloj in ('servidor', 'negocio') or camino.reloj.startswith('folio:')


def test_los_limites_de_negocio_son_las_horas_locales_del_respaldo_y_del_congelamiento():
    cfg = Config()
    delta = {'respaldo_utc': cfg.respaldo.isoformat(), 'congelamiento_utc': cfg.congelamiento.isoformat()}
    vivo = {'al_respaldo': {'folios': {'FX': 412_100}, 'servidor': '2026-11-26 10:00:00.003'},
            'al_congelamiento': {'folios': {'FX': 412_500}, 'servidor': '2026-11-26 10:00:07.120'}}
    negocio = caminos.limites('negocio', vivo, delta)
    assert (negocio['desde'], negocio['hasta']) == (datetime(2023, 12, 29, 6), datetime(2023, 12, 29, 18))
    assert negocio['parametro'] == '2023-12-29T06:00:00'
    servidor = caminos.limites('servidor', vivo, delta)
    assert servidor['desde'] == datetime(2026, 11, 26, 10, 0, 0, 3000) and servidor['parametro'] == \
        '2026-11-26 10:00:00.003'
    folio = caminos.limites('folio:FX', vivo, delta)
    assert (folio['desde'], folio['hasta']) == (412_099, 412_499)       # `siguiente` aún no se usa
    # control negativo: un registro del vivo de antes de S3 (sin el instante del servidor) no se puede medir
    del vivo['al_respaldo']['servidor']
    with pytest.raises(ValueError, match='instante del servidor'):
        caminos.limites('servidor', vivo, delta)


def test_el_sello_del_servidor_conserva_las_milesimas_y_compara_contra_su_limite():
    desde = datetime.fromisoformat('2026-11-26 10:00:00.003')
    assert caminos.sello('servidor', '2026-11-26 10:00:00.003') <= desde
    assert caminos.sello('servidor', '2026-11-26 10:00:00.007') > desde
    assert caminos.sello('folio:FX', 412_185) == 412_185 and caminos.sello('negocio', None) is None
