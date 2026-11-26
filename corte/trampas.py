"""Las trampas a ciegas como PRUEBA DE ACEPTACIÓN del corte (criterio 2 del plan de S3, ADR 0014 y 0015).

Aquí sólo se NOMBRA: la detección no lee los catálogos. La paridad de estado (`corte/estado.py`) y el oráculo del
corte (`corte/oraculo.py`) comparan sin saber qué trampa hay; cuando una comparación falla sobre un objeto, se busca en
los catálogos sellados (`legado/TRAMPAS_CIEGAS*.md`) qué trampa vive en ese objeto y se nombra. Si el catálogo no
tuviera el objeto, la comparación fallaría igual, sin nombre.

- Con efecto observable (las 6 de este paso): r1-T2, r2-T1, r2-T3, r3-T1, r3-T2, r3-T3.
- Latentes (paso siguiente, con el plan variado): r1-T1, r2-T2. Aquí el oráculo las ve iguales, y eso se dice.
- r1-T3 (espacios finales) ya la ve S2 (parche `ciega1_T3`).
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CATALOGOS = {'r1': RAIZ / 'legado' / 'TRAMPAS_CIEGAS.md', 'r2': RAIZ / 'legado' / 'TRAMPAS_CIEGAS_2.md',
             'r3': RAIZ / 'legado' / 'TRAMPAS_CIEGAS_3.md'}
OBSERVABLES = ('r1-T2', 'r2-T1', 'r2-T3', 'r3-T1', 'r3-T2', 'r3-T3')
LATENTES = ('r1-T1', 'r2-T2')
YA_EN_S2 = ('r1-T3',)

# | T1 | título | `señal → objeto` (· `señal → objeto` …) |
_RENGLON = re.compile(r'^\|\s*(T\d+)\s*\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*$')
_SENAL = re.compile(r'`(\w+)\s*→\s*([\w.]+)`')


def leer(ruta: Path, ronda: str) -> dict[str, dict]:
    """Las trampas de un catálogo: id (`r3-T1`) → título, señales y objetos."""
    resultado: dict[str, dict] = {}
    for linea in ruta.read_text(encoding='utf-8').splitlines():
        m = _RENGLON.match(linea)
        if not m:
            continue
        senales = _SENAL.findall(m.group(3))
        resultado[f'{ronda}-{m.group(1)}'] = {
            'ronda': ronda, 'trampa': m.group(1), 'titulo': m.group(2).replace('`', ''),
            'senales': [s for s, _o in senales], 'objetos': sorted({o for _s, o in senales})}
    return resultado


def catalogo(catalogos: dict[str, Path] = CATALOGOS) -> dict[str, dict]:
    resultado: dict[str, dict] = {}
    for ronda, ruta in sorted(catalogos.items()):
        resultado.update(leer(ruta, ronda))
    return resultado


def por_objeto(cat: dict[str, dict]) -> dict[str, list[str]]:
    """objeto → ids de las trampas que lo señalan (tal como lo escribe el catálogo)."""
    resultado: dict[str, list[str]] = {}
    for id_, t in sorted(cat.items()):
        for objeto in t['objetos']:
            resultado.setdefault(objeto, []).append(id_)
    return resultado


def nombrar(objeto: str, cat: dict[str, dict]) -> list[str]:
    """Las trampas del catálogo en ese objeto, con su título: lo que la comparación que falla tiene que decir."""
    return [f"{id_} ({cat[id_]['titulo']})" for id_ in por_objeto(cat).get(objeto, [])]
