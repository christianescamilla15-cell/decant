"""Paridad contra el legado del ciclo (lee el informe que deja `python -m paridad`, como las pruebas de integración
leen el de la radiografía). Marcador `paridad`: el CI las corre en el job de paridad."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from paridad import binding

pytestmark = pytest.mark.paridad
INFORME = Path(os.environ.get('DECANT_INFORME_PARIDAD', 'paridad/informe')) / 'paridad.json'


@pytest.fixture(scope='module')
def informe() -> dict:
    return json.loads(INFORME.read_text(encoding='utf-8'))


def test_t4_el_detalle_del_tobe_muestra_lo_que_pinta_cada_rejilla_no_lo_que_dice_la_tabla(informe):
    """Lee el BINDING de la pantalla (REJILLAS) y exige que el TO-BE publique en cada campo lo que esa rejilla pinta.
    La tabla detrás de «Liquidado por el corresponsal» se llama `partida_solicitada`: el nombre miente."""
    enlace = informe['binding']
    for r in binding.rejillas():
        assert enlace[r['titulo']]['conjunto'] == r['conjunto']
        assert enlace[r['titulo']]['campo_tobe'] == binding.campo_json(r['titulo'])
    assert enlace['Liquidado por el corresponsal']['tabla_legado'] == 'dbo.partida_solicitada'
    assert enlace['Solicitado por el cliente']['tabla_legado'] == 'dbo.partida_liquidada'
    casos = informe['gemelos']['casos']
    assert len(casos) == 3
    for caso in casos.values():
        assert caso['cumple'], caso['distintos']
        for rejilla in caso['rejillas']:
            assert rejilla['iguales'] and rejilla['campo_tobe'] == binding.campo_json(rejilla['titulo'])
    assert any(r['renglones'] for c in casos.values() for r in c['rejillas'] if r['rejilla'] == 'rejilla-liquidado')


def test_la_migracion_cuadra_byte_a_byte_con_los_parches_contados(informe):
    tablas = informe['migracion']['byte_a_byte']
    assert all(t['cuadra'] for t in tablas), [t['tabla'] for t in tablas if not t['cuadra']]
    corresponsal = next(t for t in tablas if t['tabla'].startswith('dbo.partida_solicitada'))
    assert corresponsal['parches']['ciega1_T3'] == 48_013          # ronda 1 a ciegas, T3
    operacion = next(t for t in tablas if t['tabla'].startswith('dbo.operacion'))
    assert (operacion['parches']['T3_texto'], operacion['parches']['T3_numero']) == (107_265, 53_702)


def test_el_esquema_se_compara_despues_de_cada_carga_y_caza_t6(informe):
    assert all(v['cumple'] for k, v in informe['esquema'].items() if k != 'control_negativo_t6')
    assert len([k for k in informe['esquema'] if k != 'control_negativo_t6']) == 5
    assert informe['esquema']['control_negativo_t6']['caza_t6']


def test_el_cuadre_por_lado_pasa_y_su_control_cruzado_falla(informe):
    cuadres = informe['migracion']['cuadre_por_lado']
    assert all(v['cuadra'] for k, v in cuadres.items() if not k.startswith('CONTROL'))
    assert next(v for k, v in cuadres.items() if k.startswith('CONTROL'))['documentos_con_violacion'] > 100_000


def test_el_motor_no_tiene_defectos_nuestros_y_t5_queda_auditado(informe):
    reglas = {r['regla']: r for r in informe['motor']['reglas']}
    assert all(r['arbitraje']['por_categoria']['defecto nuestro'] == 0 for r in reglas.values())
    r08 = reglas['R08']
    assert r08['casos'] - r08['coinciden'] == r08['arbitraje']['por_categoria']['discrepancia del legado'] > 40_000
    assert r08['arbitraje']['por_arbitro']['T5-desfase-fijo']['auditoria_fallida'] == 0
    assert all(m['pct'] == 100.0 for m in informe['motor']['solo_marca'])


def test_la_paridad_de_reporte_cumple_el_contrato_y_juzga_los_empates_contra_el_piso(informe):
    orden = informe['reporte']['orden']
    assert orden['tobe_contra_publicado']['inversiones_contrato'] == 0
    assert orden['piso_misma_corrida']['inversiones_contrato'] == 0
    assert orden['piso_misma_corrida']['pct_empatados_invertidos'] > 0
    categorias = informe['reporte']['arbitraje']['por_categoria']
    assert categorias['defecto nuestro'] == 0
    assert categorias['avance de producción'] == informe['reporte']['renglones_solo_tobe'] > 0
