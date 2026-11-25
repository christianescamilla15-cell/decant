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


def test_la_migracion_cuadra_byte_a_byte_y_cada_parche_aplica_lo_que_se_mide_en_el_origen(informe):
    """Sin constantes tecleadas: lo aplicado por cada parche debe ser lo que el legado mide de sí mismo con SQL en la
    misma corrida, y cada defecto distinto inyectado en su columna debe fallar."""
    tablas = informe['migracion']['byte_a_byte']
    assert all(t['cuadra'] for t in tablas), [t['tabla'] for t in tablas if not t['cuadra']]
    medidos = 0
    for t in tablas:
        assert not t.get('parches_sin_cuadrar'), (t['tabla'], t.get('parches_sin_cuadrar'))
        for clave, medido in t.get('parches_medidos_en_origen', {}).items():
            assert t['parches'].get(clave, 0) == medido, clave
            medidos += 1
        assert all(x['falla'] for x in t.get('controles_negativos', [])), t['tabla']
    assert medidos >= 20
    corresponsal = next(t for t in tablas if t['tabla'].startswith('dbo.partida_solicitada'))
    assert corresponsal['parches']['ciega1_T3 → referencia'] > 0       # ronda 1 a ciegas, T3


def test_el_esquema_se_compara_despues_de_cada_carga_y_caza_t6(informe):
    assert all(v['cumple'] for k, v in informe['esquema'].items() if k != 'control_negativo_t6')
    assert len([k for k in informe['esquema'] if k != 'control_negativo_t6']) == 5
    assert informe['esquema']['control_negativo_t6']['caza_t6']


def test_el_cuadre_por_lado_pasa_y_su_control_cruzado_falla(informe):
    cuadres = informe['migracion']['cuadre_por_lado']
    assert all(v['cuadra'] for k, v in cuadres.items() if not k.startswith('CONTROL'))
    assert next(v for k, v in cuadres.items() if k.startswith('CONTROL'))['documentos_con_violacion'] > 100_000


def test_el_motor_no_tiene_defectos_nuestros_y_r08_replica_al_legado(informe):
    reglas = {r['regla']: r for r in informe['motor']['reglas']}
    assert all(r['arbitraje']['por_categoria']['defecto nuestro'] == 0 for r in reglas.values())
    assert reglas['R08']['coinciden'] == reglas['R08']['casos'] > 140_000      # réplica (ADR 0006)
    assert all(m['pct'] == 100.0 for m in informe['motor']['solo_marca'])


def test_la_correccion_de_t5_es_hipotesis_auditada_en_los_dos_sentidos(informe):
    hipotesis = [h for h in informe['motor']['hipotesis'] if h['regla'].startswith('R08')]
    fija = next(h for h in hipotesis if h['elegida'])
    instantes = next(h for h in hipotesis if not h['elegida'])
    assert fija['coinciden'] == fija['casos']                                  # la fórmula del legado, columnas crudas
    t5 = informe['motor']['t5']
    assert t5['violaciones'] == 0
    assert t5['diferencias'] == instantes['casos'] - instantes['coinciden'] == t5['suma_de_ventanas'] > 40_000
    assert 'fuera de las ventanas conocidas' not in t5['ventanas']
    assert any(v.startswith('primavera 2021') for v in t5['ventanas'])        # no sólo 2023


def test_la_paridad_de_reporte_cumple_el_contrato_y_juzga_los_empates_contra_el_piso(informe):
    orden = informe['reporte']['orden']
    assert orden['tobe_contra_publicado']['inversiones_contrato'] == 0
    assert orden['piso_misma_corrida']['inversiones_contrato'] == 0
    assert orden['piso_misma_corrida']['pct_empatados_invertidos'] > 0
    categorias = informe['reporte']['arbitraje']['por_categoria']
    assert categorias['defecto nuestro'] == 0
    assert categorias['avance de producción'] == informe['reporte']['renglones_solo_tobe'] > 0


def test_los_mutantes_del_reporte_fallan_y_ninguna_llave_secundaria_queda_supuesta(informe):
    mutantes = informe['reporte']['mutantes']
    assert len(mutantes) == 6 and all(m['falla_como_debe'] for m in mutantes)
    candidatas = informe['reporte']['orden']['piso_misma_corrida']['candidatas']
    for nombre, info in candidatas.items():
        if info['orden_de_hecho_posible']:
            assert informe['reporte']['orden']['ordenes_de_hecho'][nombre]['inversiones_del_tobe'] == 0, nombre
