"""Informe de la radiografía en JSON (máquina) y Markdown (persona)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ORDEN_CATEGORIAS = ('top_sin_order_by', 'inner_join_hija', 'reloj_en_regla', 'if_exists_sin_else',
                    'if_exists_guarda', 'desfase_horario_fijo', 'centinela', 'mojibake', 're_registro',
                    'llave_candidata_con_duplicados', 'columna_sin_lectura', 'tabla_sin_lectura', 'literal_magico')
TITULOS = {
    'top_sin_order_by': 'TOP sin ORDER BY',
    'inner_join_hija': 'INNER JOIN a una tabla hija',
    'reloj_en_regla': 'Reloj del servidor (GETDATE y similares) dentro de una regla',
    'if_exists_sin_else': 'IF EXISTS sin ELSE que escribe datos (camino silencioso)',
    'if_exists_guarda': 'IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo)',
    'desfase_horario_fijo': 'Conversión de zona con desfase fijo',
    'centinela': 'Centinelas en vez de NULL (por distribución de valores)',
    'mojibake': 'Texto con mojibake (UTF-8 leído como latin-1)',
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
        estado = 'CUMPLE' if c['cumple'] else '**NO CUMPLE: el respaldo no trae lo que publica la pantalla**'
        r.append(f"`COUNT(*)` de `{c['tabla']}` en el respaldo = **{c['filas']:,}** · la pantalla del legado "
                 f"publicaba **{c['pantalla']:,}** al tomarlo → {estado}.\n")
    else:
        r.append('No aplica: no hay manifiesto con la cifra de una pantalla (base de muestra).\n')
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
