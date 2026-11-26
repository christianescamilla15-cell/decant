"""Vista legible del inventario (`corte/inventario/INVENTARIO.md`): el código, lo observado en el CI y los renglones
en tablas. Se genera; una prueba la regenera y la compara."""
from __future__ import annotations

from corte import cruce

ETIQUETA = {cruce.OBSERVADA: 'observada', cruce.POR_QUIEN_LA_USA: 'por quien la usa',
            cruce.SIN_EJECUCION: '**sin ejecución observada**'}


NOTA = ('> Generado con `python -m corte.escribir` a partir de `objetos.json` (el código), `observado.json` (lo que '
        'el CI vio durante el ciclo) y `renglones.yml`. No se edita a mano: `tests/test_corte_puerta.py` lo regenera '
        'y lo compara.')
CABECERA_OBJETOS = ('| Objeto | Tipo | Acceso | Lee (total) | Escribe (total, con triggers) | Fuera de la base | '
                    'Reloj | SQL dinámico | En el ciclo | Destino |')
NOTA_AD_HOC = ('Lo que los clientes mandan como texto (no `EXEC` de un procedimiento por RPC): qué tocan, agrupado. '
               'No es un objeto del legado; muestra quién lee o escribe tablas directo.')


def _lista(valores, vacio: str = '–') -> str:
    return ', '.join(f'`{v}`' for v in valores) if valores else vacio


def _escribe(escribe: dict) -> str:
    return ', '.join(f'`{t}` ({"/".join(e)})' for t, e in escribe.items()) if escribe else '–'


def _celda(texto: str) -> str:
    return texto.replace('|', '\\|')


def markdown(inv: dict, cruzado: dict, renglones_: list, evaluacion: dict) -> str:
    destino = {r.clave: r.destino for r in renglones_}
    obs = cruzado['observacion']
    ci = obs.get('ci') or {}
    conteo = {k: sum(1 for r in cruzado['objetos'].values() if r['ejecucion'] == k) for k in ETIQUETA}
    qs = obs.get('query_store') or {}
    muestras = obs.get('muestras') or {}
    pendientes = ''
    if evaluacion['pendientes']:
        pendientes = (f" ({len(evaluacion['pendientes'])} pendientes: "
                      + ', '.join(f'{t} {n}' for t, n in sorted(evaluacion['pendientes_por_tipo'].items())) + ')')
    objetos = (f"- **Objetos desde el código:** {len(inv['objetos'])} · "
               + ' · '.join(f'{t} {n}' for t, n in inv['por_tipo'].items()) + '.')
    escritores = (f"- **Escritores** (procedimientos, triggers y pasos de job; paridad de estado, ADR 0015): "
                  f"{len(inv['escritores'])}.")
    observacion = (f"- **Observación del ciclo:** corrida `{ci.get('corrida')}` (sha `{(ci.get('sha') or '')[:7]}`), "
                   f"{obs.get('segundos')} s, {muestras.get('sesiones')} muestras de sesiones y "
                   f"{muestras.get('estadisticas')} de estadísticas; Query Store `{qs.get('estado')}` con captura "
                   f"`{qs.get('captura')}`.")
    ejecuciones = (f"- **Ejecución:** observada {conteo[cruce.OBSERVADA]} · por quien la usa "
                   f"{conteo[cruce.POR_QUIEN_LA_USA]} · sin ejecución observada {conteo[cruce.SIN_EJECUCION]} "
                   '(clasifica; no recorta).')
    salida = [
        '# Inventario de salidas y consumidores del legado', '', NOTA, '', '## Resumen', '',
        objetos, escritores, observacion, ejecuciones,
        '- **Renglones:** ' + ' · '.join(f'{d} {sum(c.values())}' for d, c in evaluacion['destinos'].items()) + '.',
        f"- **Puerta:** {'verde' if evaluacion['verde'] else 'roja'}{pendientes}.",
        '', '## Objetos', '', CABECERA_OBJETOS, '|---|---|---|---|---|---|---|---|---|---|',
    ]
    for o in inv['objetos']:
        e = o['efectivo']
        r = cruzado['objetos'][o['id']]
        ejecucion = ETIQUETA[r['ejecucion']]
        if r.get('por'):
            ejecucion += ' (' + ', '.join(f'`{x}`' for x in r['por']) + ')'
        salida.append('| ' + ' | '.join(_celda(x) for x in (
            f"`{o['id']}`", o['tipo'], o['acceso'], _lista(e['lee']), _escribe(e['escribe']),
            _lista(e['efectos_externos']), 'sí' if o['reloj'] or e['reloj'] else '–',
            ('sí' + (' (' + _lista(o['desde_sql_dinamico']) + ')' if o['desde_sql_dinamico'] else ''))
            if e['sql_dinamico'] else '–', ejecucion, destino.get(o['id'], '**sin renglón**'))) + ' |')
    salida += ['', '## Escritores', '',
               '| Escritor | Escribe (total) | Dispara | Reloj | Identidad / transacción |', '|---|---|---|---|---|']
    por_id = {o['id']: o for o in inv['objetos']}
    for w in inv['escritores']:
        if '/paso:' in w:
            job, paso = w.split('/paso:')
            u = next(p for p in por_id[job]['pasos'] if p['paso'] == paso)
            identidad = []
        else:
            u = por_id[w]
            identidad = u['identidad'] + u['transaccion']
        e = u['efectivo']
        salida.append('| ' + ' | '.join(_celda(x) for x in (
            f'`{w}`', _escribe(e['escribe']), _lista(e['dispara']), _lista(e['reloj']), _lista(identidad))) + ' |')
    salida += ['', '## Consumidores (logins)', '',
               '| Login | Aplicaciones observadas | Origen | Sesiones | Filas en la bitácora | Destino |',
               '|---|---|---|---|---|---|']
    for login, c in cruzado['consumidores'].items():
        salida.append('| ' + ' | '.join(_celda(str(x)) for x in (
            f'`{login}`', _lista(c['aplicaciones']), ', '.join(c['origenes']), c['sesiones'],
            f"{c['filas_en_bitacora']:,}", destino.get(login, '**sin renglón**'))) + ' |')
    salida += ['', '## Acceso fuera de los módulos (lotes ad hoc observados)', '',
               NOTA_AD_HOC, '',
               '| Lee | Escribe | Llama | Fuera de la base | Lotes | Ejecuciones |', '|---|---|---|---|---|---|']
    for g in cruzado.get('ad_hoc', []):
        salida.append('| ' + ' | '.join(_celda(str(x)) for x in (
            _lista(g['lee']), _escribe(g['escribe']), _lista(g['llama']), _lista(g['efectos']), g['lotes'],
            f"{g['ejecuciones']:,}")) + ' |')
    salida += ['', '## Fuera del código', '']
    if cruzado['fuera_del_codigo']:
        salida += [f"- `{f['id']}` ({f['tipo']}): {', '.join(f['origenes'])}" for f in cruzado['fuera_del_codigo']]
    else:
        salida.append('Nada: todo lo que el servidor tiene o ejecutó del legado está en el código.')
    return '\n'.join(salida) + '\n'
