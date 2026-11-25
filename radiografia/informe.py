"""Informe de la radiografía en JSON (máquina) y Markdown (persona)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ORDEN_CATEGORIAS = ('top_sin_order_by', 'inner_join_hija', 'reloj_en_regla', 'if_exists_sin_else',
                    'if_exists_guarda', 'desfase_horario_fijo', 'round_trunca', 'division_entera', 'centinela',
                    'mojibake',
                    'espacios_finales', 're_registro',
                    'llave_candidata_con_duplicados', 'columna_sin_lectura', 'tabla_sin_lectura', 'literal_magico')
TITULOS = {
    'top_sin_order_by': ('Selección no determinista: TOP sin ORDER BY, asignación desde varias filas u ORDER BY '
                         'que no ordena (vista o tabla derivada)'),
    'inner_join_hija': 'INNER JOIN a una tabla hija',
    'reloj_en_regla': 'Reloj del servidor (GETDATE y similares) en una regla, directo o por una variable',
    'if_exists_sin_else': 'IF EXISTS sin ELSE que escribe datos (camino silencioso)',
    'if_exists_guarda': 'IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo)',
    'desfase_horario_fijo': 'Conversión de zona con desfase fijo',
    'round_trunca': 'ROUND con tercer argumento: trunca en vez de redondear',
    'division_entera': 'División entera: entero entre entero (el cociente se trunca)',
    'centinela': 'Centinelas en vez de NULL (por distribución de valores)',
    'mojibake': 'Texto con mojibake (UTF-8 leído como latin-1)',
    'espacios_finales': 'Espacios finales que SQL Server ignora al comparar y PostgreSQL no',
    're_registro': 'Re-registro: el mismo documento con otra llave interna',
    'llave_candidata_con_duplicados': 'Llave candidata con duplicados (no parece re-registro)',
    'columna_sin_lectura': 'Columnas que ningún módulo lee',
    'tabla_sin_lectura': 'Tablas que ningún módulo lee',
    'literal_magico': 'Literales mágicos (números y códigos en duro)',
}


def escribir(informe: dict, salida: Path) -> tuple[Path, Path]:
    salida.mkdir(parents=True, exist_ok=True)
    ruta_json = salida / 'radiografia.json'
    ruta_md = salida / 'radiografia.md'
    ruta_json.write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str) + '\n', encoding='utf-8')
    ruta_md.write_text(markdown(informe), encoding='utf-8')
    return ruta_json, ruta_md


def _md(valor) -> str:
    return str(valor).replace('|', '\\|').replace('\n', ' ')


def markdown(informe: dict) -> str:
    r = []
    base = informe['base']
    r.append(f'# Radiografía de `{base}`\n')
    r.append(f"Generada {informe['generado_utc']} (UTC) por `python -m radiografia`. Todo lo que sigue se midió "
             f'sobre el respaldo restaurado en un contenedor limpio.\n')
    r.append('## Restauración\n')
    r.append('| Base restaurada | Archivo | sha256 contra el manifiesto | Verificación | Segundos |')
    r.append('|---|---|---|---|---:|')
    for x in informe['restauracion']:
        sha = {True: 'coincide', False: '**NO coincide**', None: 'sin manifiesto'}[x['sha256_ok']]
        r.append(f"| `{x['restaurada_como']}` | `{x['archivo']}` | {sha} | {x['verificacion']} | {x['segundos']} |")
    c = informe['criterio_salida']
    r.append('\n## Criterio de salida\n')
    if c['aplica']:
        estado = 'CUMPLE' if c['cumple'] else '**NO CUMPLE: el respaldo no es lo que el legado publicaba**'
        r.append(f'**{estado}.** El restaurado se compara contra lo que el legado decía de sí mismo al tomar el '
                 f'respaldo (el manifiesto), no contra sí mismo.\n')
        r.append('### Cifras de la pantalla: qué cuenta cada una\n')
        r.append('| Cifra | Valor | Tabla | COUNT(*) | Interpretaciones que dan la cifra | Lectura |')
        r.append('|---|---:|---|---:|---|---|')
        for x in c['cifras']:
            r.append(f"| {x['etiqueta']} | {x['valor']:,} | `{x['tabla']}` | {x['filas']:,} | "
                     f"{', '.join(f'`{i}`' for i in x['interpretaciones']) or '—'} | {_md(x['lectura'])} |")
        r.append('\n### Cuadre de cada tabla y contador contra el manifiesto\n')
        r.append('| Objeto | Manifiesto | Restaurado | Cuadra |')
        r.append('|---|---|---|---|')
        for x in c['tablas']:
            r.append(f"| `{x['objeto']}` | {_md(x['manifiesto'])} | {_md(x['restaurado'])} | "
                     f"{'sí' if x['cuadra'] else '**NO**'} |")
        r.append('\n### Salidas publicadas: re-corrida sobre el restaurado contra la captura del respaldo\n')
        r.append('El orden se mide por inversiones con llave natural. Los pares con distinta llave de orden son '
                 'contrato (0 inversiones). Los pares empatados son libres, y su desorden es el piso de la paridad.\n')
        r.append('| Salida | Renglones (comunes) | Mismo contenido | Pares contrato | Inversiones contrato '
                 '| Pares empatados | Empatados invertidos | % posiciones distintas |')
        r.append('|---|---:|---|---:|---:|---:|---:|---:|')
        for x in c['salidas']:
            contenido = 'sí' if x['mismo_contenido'] else (
                '**NO**' if x['llave_orden'] else 'no: sin ORDER BY, otra instancia devuelve otras filas')
            r.append(f"| {x['nombre']} (`{x['procedimiento']}`) | {x['renglones']:,} ({x['renglones_comunes']:,}) | "
                     f"{contenido} | {x['pares_contrato']:,} | "
                     f"{x['inversiones_contrato']:,} | {x['pares_empatados']:,} | {x['inversiones_empatados']:,} "
                     f"({x['pct_empatados_invertidos']} %) | {x['pct_posiciones_distintas']} |")
        r.append('')
    else:
        r.append('No aplica: no hay manifiesto con lo que publicaba el legado (base de muestra).\n')
    corte = informe['corte']
    r.append('## Corte medido en la fuente\n')
    if corte.get('tabla_principal'):
        p = corte['principal']
        ident = p.get('identidad') or {}
        r.append(f"Tabla principal `{corte['tabla_principal']}`: MAX({ident.get('columna')}) = "
                 f"**{ident.get('max')}** (IDENT_CURRENT {ident.get('ident_current')}).")
        for col, rango in p['fechas'].items():
            r.append(f"- `{col}`: {rango['min']} → **{rango['max']}**")
        r.append('')
    r.append('| Tabla | MAX(id) | IDENT_CURRENT | Fecha más reciente |')
    r.append('|---|---:|---:|---|')
    for t in corte['tablas']:
        ident = t['identidad'] or {}
        fechas = ', '.join(f"{k} {v['max']}" for k, v in t['fechas'].items())
        r.append(f"| `{t['tabla']}` | {ident.get('max', '—')} | {ident.get('ident_current', '—')} | {_md(fechas)} |")
    inv = informe['inventario']
    r.append('\n## Inventario\n')
    r.append(f"{len(inv['tablas'])} tablas · {sum(t['filas'] for t in inv['tablas']):,} filas · "
             f"{len(inv['modulos'])} módulos · {len(inv['triggers'])} triggers · {len(inv['jobs'])} pasos de job.\n")
    r.append('| Tabla | Filas |')
    r.append('|---|---:|')
    for t in sorted(inv['tablas'], key=lambda x: -x['filas']):
        r.append(f"| `{t['esquema']}.{t['tabla']}` | {t['filas']:,} |")
    tipos = Counter(m['tipo'] for m in inv['modulos'])
    r.append('\nMódulos: ' + ', '.join(f'{n} {t.lower()}' for t, n in sorted(tipos.items())) + '.\n')
    if inv['triggers']:
        r.append('Triggers: ' + ', '.join(f"`{t['trigger']}` sobre `{t['tabla']}`" for t in inv['triggers']) + '.\n')
    if inv['jobs']:
        r.append('| Job | Paso | Base | Comando | Horario | Habilitado |')
        r.append('|---|---|---|---|---|---|')
        for j in inv['jobs']:
            r.append(f"| {_md(j['job'])} | {_md(j['nombre_paso'])} | {j['base']} | `{_md(j['comando'])}` | "
                     f"{_md(j['horario'])} {j['hora'] or ''} | {'sí' if j['habilitado'] else 'no'} |")
    elif informe.get('msdb') is None:
        r.append('Jobs: no se restauró msdb, así que no se pueden inventariar (viven ahí, no en la base).\n')
    hallazgos = informe['hallazgos']
    r.append('\n## Hallazgos por patrón\n')
    conteo = Counter(h['categoria'] for h in hallazgos)
    r.append('| Patrón | Hallazgos |')
    r.append('|---|---:|')
    for cat in ORDEN_CATEGORIAS:
        r.append(f'| {TITULOS[cat]} | {conteo.get(cat, 0)} |')
    for cat in ORDEN_CATEGORIAS:
        lista = [h for h in hallazgos if h['categoria'] == cat]
        if not lista:
            continue
        r.append(f'\n### {TITULOS[cat]} ({len(lista)})\n')
        if cat == 'literal_magico':
            por_objeto = Counter(h['objeto'] for h in lista)
            r.append('| Objeto | Literales distintos | Ejemplos |')
            r.append('|---|---:|---|')
            for objeto, n in por_objeto.most_common():
                ejemplos = ', '.join(f"`{_md(h['valor'])}`" for h in lista if h['objeto'] == objeto)
                r.append(f'| `{objeto}` | {n} | {ejemplos[:300]} |')
            continue
        r.append('| Objeto | Línea | Detalle | Fragmento |')
        r.append('|---|---:|---|---|')
        for h in lista[:200]:
            fragmento = f"`{_md(h['fragmento'])}`" if h.get('fragmento') else ''
            r.append(f"| `{h['objeto']}` | {h['linea'] or ''} | {_md(h['detalle'])} | {fragmento} |")
        if len(lista) > 200:
            r.append(f'\n… y {len(lista) - 200} más en `radiografia.json`.')
    t = informe['tiempos']
    r.append('\n## Tiempos\n')
    r.append(' · '.join(f'{k}: {v} s' for k, v in t.items()) + '\n')
    return '\n'.join(r) + '\n'
