"""Informe de la paridad (Markdown y JSON) y el veredicto de cada ejercicio."""
from __future__ import annotations

from paridad.arbitraje import CATEGORIAS, DEFECTO

# Salidas del legado que la paridad de S2 compara de verdad (lo demás no puede delatar nada aquí).
COMPARADAS = {
    'tablas': 'verificar la migración: las 7 tablas, byte a byte',
    'dbo.sp_reporte_ordenes': 'paridad de reporte (el reporte publicado al respaldar)',
    'dbo.sp_detalle_operacion': 'gemelos (la pantalla de detalle)',
}
# Trampas de las dos rondas a ciegas (legado/TRAMPAS_CIEGAS*.md): objeto afectado y si el catálogo las mide latentes.
CIEGAS = [
    ('ronda 1', 'T1', 'variable asignada desde varias filas', 'dbo.sp_reporte_posicion',
     'latente: con el plan de hoy coincide 9,341 de 9,341 (catálogo)'),
    ('ronda 1', 'T2', 'reloj del servidor por una variable', 'dbo.sp_ordenes_por_vencer', None),
    ('ronda 1', 'T3', 'espacios finales en la referencia del corresponsal', 'dbo.partida_solicitada.referencia', None),
    ('ronda 2', 'T1', 'ORDER BY dentro de una vista (TOP 100 PERCENT)', 'dbo.vw_liquidaciones_recientes', None),
    ('ronda 2', 'T2', 'asignación por PK que el JOIN multiplica', 'dbo.sp_constancia_operacion',
     'latente: las 104,773 constancias muestran hoy la orden vigente (catálogo)'),
    ('ronda 2', 'T3', 'división entera y AVG de enteros', 'dbo.sp_tablero_corresponsales', None),
]


def trampas_a_ciegas(r: dict) -> list[dict]:
    """¿La paridad vio el EFECTO de cada trampa a ciegas? Medido tal cual: sólo puede verlo si compara su objeto."""
    filas = []
    for ronda, id_, trampa, objeto, latente in CIEGAS:
        es_tabla = objeto.count('.') == 2
        comparado = es_tabla or objeto in COMPARADAS
        if es_tabla:
            tabla = '.'.join(objeto.split('.')[:2])
            fila = next((t for t in r.get('migracion', {}).get('byte_a_byte', [])
                         if t['tabla'].startswith(tabla + ' ')), {})
            parches = fila.get('parches', {})
            vistos = parches.get('ciega1_T3', 0) + sum(fila.get('celdas_distintas', {}).values())
            visto = 'sí' if vistos else 'no'
            evidencia = (f'byte a byte, {fila.get("tabla")}: {vistos:,} celdas de `referencia` difieren del TO-BE '
                         f'(que guarda la referencia del buzón, sin relleno). El parche ciega1_T3 que las explica '
                         f'({parches.get("ciega1_T3", 0):,}) se escribió con el catálogo YA revelado; sin él, la '
                         f'verificación falla con esas celdas. La paridad de reporte no la ve: el reporte no imprime '
                         f'la referencia')
        elif latente:
            visto = 'no aplica (latente)'
            evidencia = latente + ('' if comparado else '; además la paridad de S2 no compara esa salida')
        else:
            visto = 'no'
            evidencia = (f'la paridad de S2 no compara `{objeto}`: compara las tablas, el reporte de órdenes y la '
                         'pantalla de detalle. Un efecto en una salida que no se compara no se puede ver')
        filas.append({'ronda': ronda, 'trampa': id_, 'descripcion': trampa, 'objeto': objeto, 'visto': visto,
                      'evidencia': evidencia})
    return filas


def cumple(r: dict) -> dict:
    migracion = r.get('migracion', {})
    cuadres = migracion.get('cuadre_por_lado', {})
    control = next((v for k, v in cuadres.items() if k.startswith('CONTROL')), {})
    motor = r.get('motor', {})
    veredicto = {
        'migracion_byte_a_byte': all(t['cuadra'] for t in migracion.get('byte_a_byte', [])) and bool(migracion),
        'esquema_tras_cada_carga': all(v.get('cumple', True) for k, v in r.get('esquema', {}).items()
                                       if k != 'control_negativo_t6')
        and r.get('esquema', {}).get('control_negativo_t6', {}).get('caza_t6', False),
        'cuadre_por_lado': all(v['cuadra'] for k, v in cuadres.items() if not k.startswith('CONTROL'))
        and control.get('documentos_con_violacion', 0) > 0,
        'motor_sin_defectos_nuestros': all(x['arbitraje']['por_categoria'][DEFECTO] == 0 and not x['sobran_en_tobe']
                                           for x in motor.get('reglas', [])) and bool(motor),
        'solo_marca': all(m['pct'] == 100.0 and m['actuados_por_el_legado_sin_marca'] == 0
                          for m in motor.get('solo_marca', [])),
        'paridad_de_reporte': r.get('reporte', {}).get('cumple', False),
        'gemelos': r.get('gemelos', {}).get('cumple', True),
    }
    veredicto['todo'] = all(veredicto.values())
    return veredicto


def _n(valor) -> str:
    return f'{valor:,}' if isinstance(valor, int) else str(valor)


def markdown(r: dict) -> str:
    c = r['cumple']
    md = ['# Paridad del TO-BE contra el legado', '',
         f"Generado {r['generado']} con `python -m paridad`. Corte medido de la fuente: "
         f"**{r['corte']['instante_local']}** (Ciudad de México) = {r['corte']['instante_utc']}; "
         f"{r['corte']['regla']}.", '',
         '| Ejercicio | Cumple |', '|---|---|']
    md += [f"| {k.replace('_', ' ')} | {'sí' if v else '**NO**'} |" for k, v in c.items() if k != 'todo']
    md += ['', '## 1. Verificar la migración', '', '### Byte a byte (después de los parches documentados)', '',
          '| Legado → TO-BE | Llave | Filas | Celdas | Bytes | Faltan | Sobran | Distintas | Parches aplicados |',
          '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for t in r['migracion']['byte_a_byte']:
        distintas = sum(t.get('celdas_distintas', {}).values()) if 'celdas_distintas' in t else (
            sum(t.get('columnas_distintas_al_documento', {}).values()) or t.get('no_reconstruibles', 0))
        parches = ', '.join(f'{k} {v:,}' for k, v in t.get('parches', {}).items()) or '—'
        md.append(f"| {t['tabla']} | {t['llave']} | {_n(t['filas'])} | {_n(t.get('celdas', '—'))} | "
                 f"{_n(t.get('bytes', '—'))} | {_n(t['faltan'])} | {_n(t['sobran'])} | {_n(distintas)} | {parches} |")
    md += ['', '### Esquema columna por columna, después de cada carga', '',
          '| Carga | Columnas legado | Columnas TO-BE | Errores | Avisos |', '|---|---:|---:|---:|---|']
    for nombre, e in r['esquema'].items():
        if nombre == 'control_negativo_t6':
            continue
        md.append(f"| {r['cargas'][nombre]['base']} | {e['columnas_legado']} | {e['columnas_tobe']} | "
                 f"{len(e['errores'])} | {'; '.join(e['avisos']) or '—'} |")
    t6 = r['esquema']['control_negativo_t6']
    md += ['', f"**Control negativo (T6):** la misma comparación contra un TO-BE sin `codigo_proposito` "
              f"{'FALLA y la nombra' if t6['caza_t6'] else 'NO la caza'}: "
              f"«{t6['errores'][0] if t6['errores'] else ''}».",
          '', '### Cuadre interno por lado (Σ partes = total del encabezado)', '',
          '| Base | Documentos | Con violación | Violaciones |', '|---|---:|---:|---|']
    for nombre, q in r['migracion']['cuadre_por_lado'].items():
        detalle = '; '.join(f'{k}: {v:,}' for k, v in q['violaciones'].items()) or '—'
        md.append(f"| {nombre} | {_n(q['documentos'])} | {_n(q['documentos_con_violacion'])} | {detalle} |")
    b = r['binding']
    md += ['', 'Lados según el BINDING de la pantalla (T4): ' + '; '.join(
        f"«{t}» = conjunto {x['conjunto']} = `{x['tabla_legado']}` → `{x['campo_tobe']}`" for t, x in b.items()) + '.',
          '', '## 2. Medir el motor (replay sólo del universo, hasta el corte)', '',
          '| Regla | Qué | Origen | Casos | Coinciden | % | ' + ' | '.join(CATEGORIAS) + ' |',
          '|---|---|---|---:|---:|---:|' + '---:|' * len(CATEGORIAS)]
    for x in r['motor']['reglas']:
        cat = x['arbitraje']['por_categoria']
        md.append(f"| {x['regla']} | {x['nombre']} | `{x['origen']}` | {_n(x['casos'])} | {_n(x['coinciden'])} | "
                 f"{x['pct']} | " + ' | '.join(_n(cat[k]) for k in CATEGORIAS) + ' |')
    md += ['', 'Árbitros que absolvieron (con su auditoría):', '']
    for x in r['motor']['reglas']:
        for id_, a in x['arbitraje']['por_arbitro'].items():
            if a['casos'] or a['auditoria_fallida']:
                md.append(f"- **{x['regla']} · {id_}** ({a['categoria']}, {a['decision']}): {a['casos']:,} casos, "
                         f"{a['auditoria_fallida']} con la auditoría fallida. {a['explicacion']}. "
                         + (f"Pregunta cerrada: {a['pregunta']}" if a['pregunta'] else '')
                         + (f" Ejemplo: {a['ejemplos'][0]['evidencia']}." if a['ejemplos'] else ''))
    md += ['', '### Hipótesis y controles', '', '| Regla | Hipótesis | Elegida | Casos | Coinciden | % |',
          '|---|---|---|---:|---:|---:|']
    for h in r['motor']['hipotesis']:
        md.append(f"| {h['regla']} | {h['hipotesis']} | {'sí' if h['elegida'] else 'no'} | {_n(h['casos'])} | "
                 f"{_n(h['coinciden'])} | {h['pct']} |")
        if 'pct_por_clase' in h:
            md.append(f"| | por clase: {h['pct_por_clase']} | | | | |")
    md += ['', '### Sólo marca (bandera apagada: el motor marca ✔/✘ y no actúa)', '',
          '| Regla | Marcas | ✔ | ✘ | Coinciden con la bitácora del legado | % | Actuados por el legado sin marca |',
          '|---|---:|---:|---:|---:|---:|---:|']
    for m in r['motor']['solo_marca']:
        md.append(f"| {m['regla']} | {_n(m['marcas'])} | {_n(m['con_palomita'])} | {_n(m['con_tache'])} | "
                 f"{_n(m['coinciden_con_el_legado'])} | {m['pct']} | {m['actuados_por_el_legado_sin_marca']} |")
    p = r['reporte']
    o = p['orden']
    md += ['', '## 3. Paridad de reporte (TO-BE en sombra contra lo que el legado publicó)', '',
          f"Publicado: `{p['publicado']['archivo']}` ({p['publicado']['renglones']:,} renglones, sha256 "
          f"`{p['publicado']['sha256'][:16]}…`). TO-BE: {p['tobe']['renglones']:,} renglones. Comunes "
          f"{p['renglones_comunes']:,}; sólo en el TO-BE {p['renglones_solo_tobe']:,}; sólo en el legado "
          f"{p['renglones_solo_legado']:,}; comunes con alguna celda distinta "
          f"{p['renglones_comunes_con_celdas_distintas']:,}.",
          '', '| Orden (inversiones, por llave natural) | Pares de contrato | Inversiones de contrato | '
              'Pares empatados | % empatados invertidos |', '|---|---:|---:|---:|---:|']
    for nombre, m in (('piso: el legado re-corrido contra lo que publicó (esta corrida)', o['piso_misma_corrida']),
                      ('TO-BE contra lo publicado', o['tobe_contra_publicado'])):
        md.append(f"| {nombre} | {_n(m['pares_contrato'])} | {_n(m['inversiones_contrato'])} | "
                 f"{_n(m['pares_empatados'])} | {m['pct_empatados_invertidos']} |")
    md += ['', 'Piso (control negativo) con el plan variado en el contenedor limpio: ' + '; '.join(
        f"{m['variante']}: {m['pct_empatados_invertidos']} % de empatados invertidos, {m['inversiones_contrato']} de "
        f"contrato" for m in o['piso_misma_corrida'].get('muestras', [])) + '.']
    md += ['', f"**Veredicto del orden:** {o['veredicto']}.", '', '| Categoría | Diferencias |', '|---|---:|']
    md += [f'| {k} | {_n(v)} |' for k, v in p['arbitraje']['por_categoria'].items()]
    md += ['']
    for id_, a in p['arbitraje']['por_arbitro'].items():
        md.append(f"- **{id_}** ({a['categoria']}, {a['decision']}): {a['casos']:,} casos, {a['auditoria_fallida']} "
                 f"con la auditoría fallida. {a['explicacion']}."
                 + (f" Ejemplo: {a['ejemplos'][0]['evidencia']}." if a['ejemplos'] else ''))
    if p['arbitraje']['sin_explicar']:
        md += ['', 'Sin explicar (defecto nuestro):', '']
        md += [f"- {d['regla']} {d['llave']}: legado {d['legado']} · TO-BE {d['tobe']} · {d['evidencia']}"
              for d in p['arbitraje']['sin_explicar'][:10]]
    if 'gemelos' in r:
        g = r['gemelos']
        md += ['', '## 4. Gemelos (pantalla de detalle del legado contra el JSON de la API)', '',
              '| Caso | Operación | Campos comparados | Distintos | Rejillas (binding → campo del TO-BE) |',
              '|---|---:|---:|---:|---|']
        for nombre, caso in g['casos'].items():
            rej = '; '.join(f"{x['rejilla']} → {x['campo_tobe']} ({x['renglones']} renglones, "
                            f"{'iguales' if x['iguales'] else 'DISTINTAS'})" for x in caso.get('rejillas', []))
            md.append(f"| {nombre} | {caso['operacion']} | {caso.get('campos_comparados', 0)} | "
                     f"{len(caso.get('distintos', []))} | {rej} |")
        md += ['', 'No expuestos: ' + '; '.join(f'`{k}`: {v}' for k, v in g['no_expuestos'].items()) + '.']
    md += ['', '## Trampas de las rondas a ciegas: ¿la paridad vio su efecto?', '',
          'Medido tal cual, sin ajustar nada: la paridad sólo puede ver el efecto de una trampa en una salida que '
          'compara (' + '; '.join(f'`{k}`: {v}' for k, v in COMPARADAS.items()) + ').', '',
          '| Ronda | Trampa | Objeto | ¿Lo vio? | Evidencia |', '|---|---|---|---|---|']
    for t in r['trampas_a_ciegas']:
        md.append(f"| {t['ronda']} | {t['trampa']} · {t['descripcion']} | `{t['objeto']}` | {t['visto']} | "
                 f"{t['evidencia']} |")
    md += ['', '## Tiempos', '', '| Paso | Segundos |', '|---|---:|']
    md += [f'| {k} | {v} |' for k, v in r['tiempos'].items()]
    return '\n'.join(md) + '\n'


def resumen(r: dict) -> str:
    lineas = ['', 'Paridad: ' + ' · '.join(f"{k} {'✔' if v else '✘'}" for k, v in r['cumple'].items() if k != 'todo')]
    for x in r['motor']['reglas']:
        lineas.append(f"  {x['regla']} {x['pct']} % ({x['coinciden']:,} de {x['casos']:,})")
    cat = r['reporte']['arbitraje']['por_categoria']
    lineas.append('  reporte: ' + ' · '.join(f'{k} {v:,}' for k, v in cat.items()))
    lineas.append(f"  {r['reporte']['orden']['veredicto']}")
    return '\n'.join(lineas)
