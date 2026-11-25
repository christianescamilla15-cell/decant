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
            clave = 'ciega1_T3 → referencia'
            aplicado = fila.get('parches', {}).get(clave, 0)
            medido = fila.get('parches_medidos_en_origen', {}).get(clave)
            controles = [x for x in fila.get('controles_negativos', []) if x['parche'] == clave]
            visto = 'sí' if aplicado and aplicado == medido else 'no'
            evidencia = (f'byte a byte, {fila.get("tabla")}: sin su parche, {_n(aplicado)} celdas de `referencia` '
                         f'difieren del TO-BE (que guarda la referencia del buzón). El parche es exacto (ventana, '
                         f'ancho 35, sólo espacios) y su conteo, medido en el ORIGEN por otro camino, da {_n(medido)}; '
                         f'{sum(x["falla"] for x in controles)} de {len(controles)} defectos distintos inyectados '
                         f'en la columna fallan como deben. El parche se escribió con el catálogo YA revelado '
                         f'(ADR 0007). La '
                         f'paridad de reporte no la ve: el reporte no imprime la referencia')
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
        'parches_aplicados_igual_a_lo_medido_en_el_origen': all(
            not t.get('parches_sin_cuadrar') for t in migracion.get('byte_a_byte', [])) and bool(migracion),
        'controles_negativos_de_parches': all(
            x['falla'] for t in migracion.get('byte_a_byte', []) for x in t.get('controles_negativos', [])),
        'r08_replica_y_auditoria_de_t5': bool(motor) and _t5_cumple(motor),
        'paridad_de_reporte': r.get('reporte', {}).get('cumple', False),
        'mutantes_del_reporte_fallan': bool(r.get('reporte', {}).get('mutantes'))
        and all(m['falla_como_debe'] for m in r['reporte']['mutantes']),
        'gemelos': r.get('gemelos', {}).get('cumple', True),
    }
    veredicto['todo'] = all(veredicto.values())
    return veredicto


def _t5_cumple(motor: dict) -> bool:
    t5 = motor.get('t5', {})
    fija = next((h for h in motor.get('hipotesis', []) if h['regla'].startswith('R08') and h['elegida']), {})
    return (t5.get('violaciones', 1) == 0 and t5.get('suma_de_ventanas') == t5.get('diferencias')
            and fija.get('coinciden') == fija.get('casos') and 'fuera de las ventanas conocidas' not in
            t5.get('ventanas', {}))


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
        parches = ', '.join(f'{k} {v:,}' for k, v in t.get('parches', {}).items()
                            if not k.startswith('T5')) or '—'
        md.append(f"| {t['tabla']} | {t['llave']} | {_n(t['filas'])} | {_n(t.get('celdas', '—'))} | "
                 f"{_n(t.get('bytes', '—'))} | {_n(t['faltan'])} | {_n(t['sobran'])} | {_n(distintas)} | {parches} |")
    md += ['', '### Parches: lo aplicado contra lo medido en el ORIGEN, y su control negativo', '',
           'Cada parche es una transformación exacta con el predicado de su hallazgo '
           '([reglas](../../docs/parches.md)). '
           'Su conteo esperado se mide en el legado restaurado con SQL, por otro camino que el diff; en una copia de '
           'renglones reales se inyecta un defecto DISTINTO en la misma columna y debe fallar.', '',
           '| Tabla | Parche → columna | Aplicado | Medido en el origen | Igual | Defectos distintos inyectados que '
           'fallan |', '|---|---|---:|---:|---|---|']
    for t in r['migracion']['byte_a_byte']:
        claves = sorted(set(t.get('parches', {})) | set(t.get('parches_medidos_en_origen', {})))
        for clave in claves:
            aplicado = t.get('parches', {}).get(clave, 0)
            medido = t.get('parches_medidos_en_origen', {}).get(clave)
            controles = [x for x in t.get('controles_negativos', []) if x['parche'] == clave]
            detalle = '; '.join(f"{x['inyeccion']}: {'falla' if x['falla'] else '**PASA**'}" for x in controles)
            md.append(f"| {t['tabla'].split(' ')[0]} | {clave} | {_n(aplicado)} | {_n(medido)} | "
                      f"{'sí' if aplicado == medido else '**NO**'} | {detalle or '—'} |")
    relleno = next((t.get('referencias_con_espacios_finales_en_toda_la_columna')
                    for t in r['migracion']['byte_a_byte'] if t['tabla'].startswith('dbo.partida_solicitada')), None)
    md += ['', f'Espacios finales en TODA la columna `partida_solicitada.referencia`: {_n(relleno)} (los que no '
               'cumplan el predicado del hallazgo quedarían como diferencias).']
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
    t5 = r['motor'].get('t5', {})
    if t5:
        md += ['', '### R08 / T5: la corrección como hipótesis, auditada en los dos sentidos', '',
               'El TO-BE REPLICA la hora fija del legado (ADR 0006; el instante se guarda en UTC, ADR 0008). La '
               'corrección se mide aquí desde fuentes independientes: Nueva York por el desfase EXPLÍCITO del `:13D:` '
               'del buzón; la Ciudad de México por la base de zonas de la paridad; la hora repetida se cuenta aparte '
               '(resuelta por orden de llegada). Lo que se prueba: «desfase extra ≠ 0 ⇔ el legado difiere», con la '
               'diferencia igual al extra.', '', '| Conteo | Casos |', '|---|---:|']
        md += [f'| {k} | {_n(v)} |' for k, v in t5['conteos'].items()]
        md += [f"| diferencias en total (legado contra la corrección) | {_n(t5['diferencias'])} |",
               f"| violaciones | {_n(t5['violaciones'])} |", '', '| Ventana (por la fecha de la última partida, '
               'hora de Nueva York) | Diferencias |', '|---|---:|']
        md += [f'| {k} | {_n(v)} |' for k, v in t5['ventanas'].items()]
        md += [f"| **suma** | **{_n(t5['suma_de_ventanas'])}** |", '',
               'Pregunta cerrada a negocio: ¿las horas de liquidación se calculan con el desfase real de Nueva York? '
               'Hoy el legado suma una hora de más en las semanas en que los dos calendarios no coincidieron: de '
               'mediados de marzo a inicios de abril y de fines de octubre a inicios de noviembre en 2021 y 2022, y '
               'de marzo a noviembre en 2023.']
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
    candidatas = o['piso_misma_corrida'].get('candidatas', {})
    if candidatas:
        md += ['', 'Llaves secundarias candidatas (después de la fecha valor): inversiones del legado contra sí mismo '
                   'en cada variante del plan. Si alguna nunca se invierte, puede ser un orden de hecho y se pregunta '
                   'a negocio.', '', '| Llave candidata | Inversiones por variante | ¿Orden de hecho posible? |',
               '|---|---|---|']
        md += [f"| fecha_valor + {c} | {', '.join(_n(x) for x in v['inversiones_por_variante'])} | "
               f"{'**sí: pregunta a negocio**' if v['orden_de_hecho_posible'] else 'no (el legado la invierte)'} |"
               for c, v in candidatas.items()]
        for x in o.get('ordenes_de_hecho', {}).values():
            md.append(f"\n- {x['pregunta']} El TO-BE la invierte {x['inversiones_del_tobe']:,} veces.")
    ciego = p.get('punto_ciego', {})
    md += ['', f"**Punto ciego declarado:** {ciego.get('lectura', '')}. Celdas de este reporte en la hora repetida: "
               f"{_n(ciego.get('celdas_en_hora_repetida'))}."]
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
    if p.get('mutantes'):
        md += ['', '### Control negativo del comparador: mutantes del reporte del TO-BE', '',
               'El piso calibra el ruido del legado; estos mutantes demuestran que la comparación SÍ falla.', '',
               '| Mutante | Debe | Defectos nuestros | Inversiones de contrato | ¿Falla como debe? |',
               '|---|---|---:|---:|---|']
        md += [f"| {m['mutante']} | {m['debe']} | {m['defectos']} | {m['inversiones_contrato']} | "
               f"{'sí' if m['falla_como_debe'] else '**NO**'} |" for m in p['mutantes']]
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
    md += ['', 'La cobertura de SALIDAS (los procedimientos y vistas que esta paridad no compara) es la puerta de '
               'entrada de S3.']
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
