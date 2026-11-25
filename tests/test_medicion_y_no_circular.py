"""La radiografía no es circular: sólo la medición lee el catálogo de trampas, y lo hace al final."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from radiografia.medicion import leer_catalogo, medir
from radiografia.sqlserver import IMAGEN

RADIOGRAFIA = Path('radiografia')


def test_ningun_detector_lee_el_catalogo_ni_importa_el_legado():
    for ruta in RADIOGRAFIA.glob('*.py'):
        if ruta.name == 'medicion.py':
            continue
        texto = ruta.read_text(encoding='utf-8')
        assert 'TRAMPAS' not in texto, ruta
        modulos = {n.module or '' for n in ast.walk(ast.parse(texto)) if isinstance(n, ast.ImportFrom)}
        modulos |= {a.name for n in ast.walk(ast.parse(texto)) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m == 'legado' or m.startswith('legado.') for m in modulos), ruta


def test_el_contenedor_limpio_usa_la_misma_imagen_que_el_legado():
    compose = Path('legado/docker-compose.yml').read_text(encoding='utf-8')
    assert re.search(r'image:\s*(\S+)', compose).group(1) == IMAGEN


def test_el_catalogo_tiene_nueve_trampas_y_tres_defectos():
    trampas = leer_catalogo(Path('legado/TRAMPAS.md').read_text(encoding='utf-8'))
    ids = [t['id'] for t in trampas]
    assert ids == [f'T{n}' for n in range(1, 10)] + ['D1', 'D2', 'D3']
    t3 = next(t for t in trampas if t['id'] == 'T3')
    assert len(t3['senales']) == 3
    assert next(t for t in trampas if t['id'] == 'T4')['senales'] == []


def test_la_medicion_distingue_detectada_parcial_y_sin_patron():
    trampas = [{'id': 'T1', 'nombre': 'a', 'senales': [('top_sin_order_by', 'dbo.p')]},
               {'id': 'T2', 'nombre': 'b', 'senales': [('centinela', 'dbo.t.a'), ('centinela', 'dbo.t.b')]},
               {'id': 'T3', 'nombre': 'c', 'senales': []},
               {'id': 'T4', 'nombre': 'd', 'senales': [('mojibake', 'dbo.t.c')]}]
    hallazgos = [{'categoria': 'top_sin_order_by', 'objeto': 'dbo.p'},
                 {'categoria': 'centinela', 'objeto': 'dbo.t.a'},
                 {'categoria': 'inner_join_hija', 'objeto': 'dbo.v'},
                 {'categoria': 'literal_magico', 'objeto': 'dbo.p'}]
    m = medir(hallazgos, trampas)
    assert [f['estado'] for f in m['filas']] == ['detectada', 'parcial', 'sin patrón en S1', 'no detectada']
    assert m['detectadas'] == 1 and m['pct_deteccion'] == 25.0
    # lo que no corresponde a ninguna trampa queda a la vista (los literales son inventario, no hallazgo)
    assert m['hallazgos_sin_trampa'] == [{'categoria': 'inner_join_hija', 'objeto': 'dbo.v'}]
