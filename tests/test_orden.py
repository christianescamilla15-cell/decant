"""El orden se compara por inversiones con llave natural, separando contrato (distinta llave de orden) de empates."""
from __future__ import annotations

import pytest

from radiografia.orden import _inversiones, comparar


def test_cuenta_inversiones_de_una_permutacion():
    assert _inversiones([0, 1, 2, 3]) == 0
    assert _inversiones([3, 2, 1, 0]) == 6
    assert _inversiones([1, 0, 3, 2]) == 2


def test_misma_toma_no_tiene_inversiones():
    a = [('A', 1), ('B', 1), ('C', 2)]
    r = comparar(a, list(a), [0], [1])
    assert r['inversiones_contrato'] == 0 and r['inversiones_empatados'] == 0 and r['mismo_contenido']


def test_empates_reordenados_son_libres_y_el_contrato_queda_en_cero():
    # el reporte del legado ordena por fecha valor; dentro de un día el orden lo decide el plan
    a = [('OP-1', 'd1'), ('OP-2', 'd1'), ('OP-3', 'd1'), ('OP-4', 'd2')]
    b = [('OP-3', 'd1'), ('OP-1', 'd1'), ('OP-2', 'd1'), ('OP-4', 'd2')]
    r = comparar(a, b, [0], [1])
    assert r['pares_empatados'] == 3 and r['inversiones_empatados'] == 2
    assert r['pares_contrato'] == 3 and r['inversiones_contrato'] == 0
    assert r['pct_empatados_invertidos'] == pytest.approx(66.67)
    assert r['pct_posiciones_distintas'] == 75.0     # por posición parecería un desastre


def test_romper_el_order_by_cuenta_como_inversion_de_contrato():
    a = [('OP-1', 'd1'), ('OP-2', 'd2')]
    b = [('OP-2', 'd2'), ('OP-1', 'd1')]
    r = comparar(a, b, [0], [1])
    assert r['inversiones_contrato'] == 1 and r['inversiones_empatados'] == 0


def test_sin_llave_de_orden_todos_los_pares_son_libres():
    r = comparar([(1,), (2,), (3,)], [(3,), (2,), (1,)], [0], [])
    assert r['pares_contrato'] == 0 and r['inversiones_empatados'] == 3


def test_contenido_distinto_se_reporta():
    r = comparar([('A', 1, 10)], [('A', 1, 11)], [0], [1])
    assert r['mismo_contenido'] is False


def test_llave_natural_repetida_no_sirve_para_comparar():
    with pytest.raises(ValueError):
        comparar([('A', 1), ('A', 2)], [('A', 1), ('A', 2)], [0], [1])
