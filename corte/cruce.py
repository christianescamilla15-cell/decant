"""Cruce del inventario (código) con lo observado en el CI (servidor): CLASIFICA, nunca recorta.

Por objeto del inventario, su ejecución:
- `observada`: el servidor la registró (estadísticas de ejecución, Query Store, una petición en curso, un lote ad hoc
  que la nombra o el historial del job);
- `observada_por_quien_la_usa`: sólo vistas y funciones, que no tienen estadísticas propias: no se registraron, pero
  un objeto que la lee o la llama sí se ejecutó (se nombra cuál);
- `sin_ejecucion_observada`: todo lo demás, incluidos la pantalla y las interfaces (el servidor no distingue qué
  cliente hizo cada llamada). Sigue en el inventario y necesita renglón igual: «no se vio ejecutar» no es «no tiene
  consumidor» (ADR 0014).

Además: los objetos que el servidor TIENE o EJECUTÓ y el código no (`fuera_del_codigo`) y los consumidores (logins con
sus aplicaciones), por sesiones muestreadas y por los usuarios que dejó la bitácora.
"""
from __future__ import annotations

OBSERVADA = 'observada'
POR_QUIEN_LA_USA = 'observada_por_quien_la_usa'
SIN_EJECUCION = 'sin_ejecucion_observada'


def cruzar(inv: dict, observado: dict) -> dict:
    ejecutados = observado.get('objetos_ejecutados', {})
    ids = {o['id'] for o in inv['objetos']}
    tablas = set(inv.get('tablas', {}))
    resultado: dict[str, dict] = {}
    for o in inv['objetos']:
        e = ejecutados.get(o['id'])
        if e:
            resultado[o['id']] = {'ejecucion': OBSERVADA, 'fuentes': e['fuentes'], 'ejecuciones': e['ejecuciones']}
        else:
            resultado[o['id']] = {'ejecucion': SIN_EJECUCION}

    # Vistas y funciones: las ejecuta quien las usa (hasta un punto fijo: una vista que lee otra vista).
    usa = {o['id']: set(o['lee']) | set(o['llama']) for o in inv['objetos']}
    tipos = {o['id']: o['tipo'] for o in inv['objetos']}
    cambio = True
    while cambio:
        cambio = False
        vistos = {i for i, r in resultado.items() if r['ejecucion'] != SIN_EJECUCION}
        for id_, r in resultado.items():
            if r['ejecucion'] != SIN_EJECUCION or tipos[id_] not in ('vista', 'funcion'):
                continue
            por = sorted(x for x in vistos if id_ in usa.get(x, ()))
            if por:
                resultado[id_] = {'ejecucion': POR_QUIEN_LA_USA, 'por': por}
                cambio = True

    for o in inv['objetos']:
        if o['tipo'] == 'pantalla' and resultado[o['id']]['ejecucion'] == SIN_EJECUCION:
            vistas = [x for x in o['llama'] if resultado.get(x, {}).get('ejecucion') == OBSERVADA]
            if vistas:
                resultado[o['id']]['nota'] = ('el servidor no distingue qué cliente llamó; lo que la pantalla llama sí '
                                              'se observó: ' + ', '.join(vistas))

    fuera: dict[str, dict] = {}
    catalogo = observado.get('catalogo', {})
    for m in catalogo.get('modulos', []):
        if m['id'] not in ids:
            fuera.setdefault(m['id'], {'id': m['id'], 'tipo': m['tipo'], 'origenes': set()})['origenes'].add(
                'catálogo del servidor')
    for job in catalogo.get('jobs', []):
        if job not in ids:
            fuera.setdefault(job, {'id': job, 'tipo': 'job', 'origenes': set()})['origenes'].add('msdb del servidor')
    for id_, e in ejecutados.items():
        if id_ not in ids and id_ not in tablas:
            fuera.setdefault(id_, {'id': id_, 'tipo': e['tipo'], 'origenes': set()})['origenes'].add(
                'ejecución observada')
    return {
        'observacion': {k: observado.get(k) for k in ('ci', 'inicio_utc', 'fin_utc', 'segundos', 'muestras',
                                                      'terminado')}
        | {'query_store': {k: observado.get('query_store', {}).get(k) for k in ('estado', 'captura')}},
        'objetos': resultado,
        'fuera_del_codigo': [{**f, 'origenes': sorted(f['origenes'])} for _, f in sorted(fuera.items())],
        'consumidores': consumidores(observado),
        'ad_hoc': observado.get('ad_hoc', []),
    }


def consumidores(observado: dict) -> dict[str, dict]:
    """Logins con sus aplicaciones y de dónde salen (sesiones muestreadas o bitácora)."""
    resultado: dict[str, dict] = {}

    def login(nombre: str) -> dict:
        return resultado.setdefault(nombre, {'aplicaciones': set(), 'origenes': set(), 'sesiones': 0,
                                             'filas_en_bitacora': 0})

    for c in observado.get('consumidores', []):
        x = login(c['login'])
        x['aplicaciones'].add(c['aplicacion'])
        x['origenes'].add('sesiones (dm_exec_sessions)')
        x['sesiones'] += c['sesiones']
    for u in observado.get('bitacora', {}).get('usuarios', []):
        x = login(u['login'])
        x['origenes'].add('bitácora (SUSER_SNAME del trigger)')
        x['filas_en_bitacora'] += u['filas']
    return {k: {**v, 'aplicaciones': sorted(v['aplicaciones']), 'origenes': sorted(v['origenes'])}
            for k, v in sorted(resultado.items())}


def sin_ejecucion(cruce: dict) -> list[str]:
    return sorted(i for i, r in cruce['objetos'].items() if r['ejecucion'] == SIN_EJECUCION)
