"""Arbitraje de CADA diferencia entre el TO-BE y el legado, en cuatro categorías:

- **defecto nuestro**: lo que ningún árbitro explica (o cuyo árbitro no pasó su auditoría). Se corrige.
- **regla real del legado**: el legado tiene una regla que el TO-BE no replica (todavía); se documenta y se replica.
- **discrepancia del legado**: un defecto o accidente del legado con su ADR y su pregunta cerrada a negocio.
- **avance de producción**: el TO-BE ya vio un evento POSTERIOR al corte que el respaldo no tiene.

Cada árbitro dice cuándo APLICA y cómo se AUDITA: la auditoría vuelve a medir que su explicación da exactamente el
valor (no sólo que el caso «cae en la ventana»). Una diferencia que aplica a un árbitro y no pasa su auditoría NO
queda absuelta: cuenta como defecto nuestro, con el árbitro que falló.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

DEFECTO = 'defecto nuestro'
REGLA = 'regla real del legado'
DISCREPANCIA = 'discrepancia del legado'
AVANCE = 'avance de producción'
CATEGORIAS = (DEFECTO, REGLA, DISCREPANCIA, AVANCE)


@dataclass
class Diferencia:
    regla: str
    llave: str
    legado: object
    tobe: object
    contexto: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Arbitro:
    id: str
    categoria: str
    decision: str                       # ADR o regla documentada
    explicacion: str
    aplica: Callable[[Diferencia], bool]
    audita: Callable[[Diferencia], tuple[bool, str]]
    pregunta: str | None = None         # pregunta cerrada a negocio (discrepancias)


def arbitrar(diferencias: list[Diferencia], arbitros: list[Arbitro]) -> dict:
    por_categoria: Counter = Counter()
    por_arbitro: dict[str, dict] = {a.id: {'categoria': a.categoria, 'decision': a.decision,
                                           'explicacion': a.explicacion, 'pregunta': a.pregunta, 'casos': 0,
                                           'auditoria_fallida': 0, 'ejemplos': []} for a in arbitros}
    sin_explicar: list[dict] = []
    for d in diferencias:
        arbitro = next((a for a in arbitros if a.aplica(d)), None)
        if arbitro is None:
            por_categoria[DEFECTO] += 1
            sin_explicar.append(_resumen(d, 'ningún árbitro la explica'))
            continue
        ok, evidencia = arbitro.audita(d)
        registro = por_arbitro[arbitro.id]
        if ok:
            por_categoria[arbitro.categoria] += 1
            registro['casos'] += 1
            if len(registro['ejemplos']) < 3:
                registro['ejemplos'].append(_resumen(d, evidencia))
        else:
            por_categoria[DEFECTO] += 1
            registro['auditoria_fallida'] += 1
            sin_explicar.append(_resumen(d, f'{arbitro.id} aplica pero su auditoría falla: {evidencia}'))
    return {'diferencias': len(diferencias), 'por_categoria': {c: por_categoria.get(c, 0) for c in CATEGORIAS},
            'por_arbitro': por_arbitro, 'sin_explicar': sin_explicar[:20],
            'sin_explicar_total': len(sin_explicar)}


def _resumen(d: Diferencia, evidencia: str) -> dict:
    return {'regla': d.regla, 'llave': d.llave, 'legado': _t(d.legado), 'tobe': _t(d.tobe), 'evidencia': evidencia}


def _t(valor) -> str | None:
    return None if valor is None else str(valor)
