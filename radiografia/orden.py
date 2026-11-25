"""El orden de una salida se mide por INVERSIONES y se compara por LLAVE NATURAL, nunca por posición.

Dadas dos tomas de la misma salida (mismas filas, llave natural única por renglón), cuenta los pares de renglones
cuyo orden relativo se invirtió, separados en dos clases:

- **contrato:** los dos renglones tienen distinta llave de orden (`ORDER BY`). Ese orden lo promete la consulta: debe
  dar 0 inversiones siempre, y cualquier inversión es un defecto.
- **empatados:** misma llave de orden. Su orden relativo es libre (lo decide el plan) y el piso de la paridad se mide
  sólo aquí.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence


def _inversiones(secuencia: list[int]) -> int:
    """Pares (i < j) con secuencia[i] > secuencia[j], por mezcla: O(n log n)."""
    if len(secuencia) < 2:
        return 0
    medio = len(secuencia) // 2
    izquierda, derecha = secuencia[:medio], secuencia[medio:]
    total = _inversiones(izquierda) + _inversiones(derecha)
    izquierda.sort()
    derecha.sort()
    j = 0
    for valor in izquierda:
        while j < len(derecha) and derecha[j] < valor:
            j += 1
        total += j
    return total


def comparar(a: Sequence[tuple], b: Sequence[tuple], llave_natural: Sequence[int],
             llave_orden: Sequence[int]) -> dict:
    """a y b: renglones (tuplas). llave_natural y llave_orden: índices de columna."""
    natural_a = [tuple(r[i] for i in llave_natural) for r in a]
    natural_b = [tuple(r[i] for i in llave_natural) for r in b]
    if len(set(natural_a)) != len(natural_a):
        raise ValueError('la llave natural se repite: no identifica al renglón')
    mismo_contenido = sorted(map(repr, a)) == sorted(map(repr, b))
    posicion_b = {llave: k for k, llave in enumerate(natural_b)}
    comunes = [k for k, llave in enumerate(natural_a) if llave in posicion_b]
    secuencia = [posicion_b[natural_a[k]] for k in comunes]
    grupos: dict[tuple, list[int]] = defaultdict(list)
    for k, pos in zip(comunes, secuencia):
        grupos[tuple(a[k][i] for i in llave_orden)].append(pos)
    total = _inversiones(list(secuencia))
    empatadas = sum(_inversiones(list(g)) for g in grupos.values())
    n = len(secuencia)
    pares_empatados = sum(len(g) * (len(g) - 1) // 2 for g in grupos.values())
    pares = n * (n - 1) // 2
    posiciones_distintas = sum(1 for x, y in zip(natural_a, natural_b) if x != y)
    return {
        'renglones': len(a), 'renglones_otra_toma': len(b), 'renglones_comunes': len(comunes),
        'mismo_contenido': mismo_contenido,
        'pares_contrato': pares - pares_empatados, 'inversiones_contrato': total - empatadas,
        'pares_empatados': pares_empatados, 'inversiones_empatados': empatadas,
        'pct_empatados_invertidos': round(100 * empatadas / pares_empatados, 2) if pares_empatados else 0.0,
        'pct_posiciones_distintas': round(100 * posiciones_distintas / len(a), 1) if a else 0.0,
    }
