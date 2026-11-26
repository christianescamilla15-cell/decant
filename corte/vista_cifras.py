"""`corte/cifras/CIFRAS.md`: la vista legible del corte por dos caminos y de las cifras de control de la corrida
versionada (`python -m corte.veredicto … --versionar` la regenera; no se edita a mano)."""
from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from corte import cifras, medir


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


def _montos(montos: dict) -> str:
    return ' · '.join(f'{m} {Decimal(v):,.2f}' for m, v in sorted(montos.items())) or '–'


def markdown(directorio: Path) -> str:
    corte = _json(directorio / medir.CORTE)
    control = _json(directorio / medir.CIFRAS)
    huella = _json(directorio / 'huella.json')
    ci = huella.get('corrida', {})
    origen = (f"Generado por `python -m corte.veredicto --versionar` desde la corrida {ci.get('corrida')} del CI "
              f"(commit `{(ci.get('sha') or '')[:12]}`). Plan: [`docs/s3/PLAN.md`](../../docs/s3/PLAN.md), criterios "
              '3, 7 y 8. No se edita a mano.')
    partes = ['# Corte medido por dos caminos y cifras de control', origen]

    partes.append('## 1. El corte por dos caminos (criterio 3)')
    f = corte['fotos']
    partes.append(f"Corte = foto del respaldo; congelamiento = la del legado vivo cuando se congela. Reloj del "
                  f"servidor: `{f['respaldo_servidor']}` → `{f['congelamiento_servidor']}`. Hora de negocio: "
                  f"`{f['respaldo_utc']}` → `{f['congelamiento_utc']}` (UTC). Cada camino por sellos tiene que dar "
                  'EXACTAMENTE los mismos ids que la identidad, del delta y de lo posterior: la diferencia de '
                  'conjuntos es 0 o el corte no avanza.')
    encabezado = ('| tabla | corte (MAX id) | congelamiento | delta | posterior | huecos | camino por sellos: delta + '
                  'posterior | coincide |')
    filas = [encabezado, '|---|---|---|---|---|---|---|---|']
    for tabla, t in corte['tablas'].items():
        if 'por_identidad' not in t:
            filas.append(f"| `{tabla}` | – | – | – | – | – | sin identidad: catálogo o consumible, se compara "
                         'completo | – |')
            continue
        p = t['por_identidad']
        for i, c in enumerate(t['caminos']):
            inicio = (f"| `{tabla}` | {p['corte']:,} | {p['congelamiento']:,} | {p['delta']:,} | {p['posterior']:,} | "
                      f"{t['huecos']['cuantos']} |") if i == 0 else '| | | | | | |'
            m = c['comparacion']['mayores_al_corte']
            marca = 'sí' if c['comparacion']['coincide'] else (
                f"NO: {m['solo_por_identidad']} sólo por identidad, {m['solo_por_sellos']} sólo por sellos")
            nombre = f"{c['nombre']}{' *(control negativo)*' if c['control_negativo'] else ''}"
            filas.append(f"{inicio} {nombre}: {c['delta']:,} + {c['posterior']:,} | {marca} |")
    partes.append('\n'.join(filas))
    n = corte.get('control_negativo') or {}
    partes.append(f"**Control negativo.** El camino por `fecha_operacion` (fecha de negocio, no sello de registro) "
                  f"pierde {n.get('perdidos_por_el_camino')} ids mayores al corte y la comparación falla nombrando "
                  f"{n.get('nombradas')} de {n.get('esperadas')} altas fechadas hacia atrás:\n"
                  + '\n'.join(f'- `{x}`' for x in n.get('altas_fechadas_hacia_atras', [])))

    partes.append('## 2. Totales de las tablas y consumibles (criterio 8)')
    filas = ['| tabla | respaldo | + delta | = congelamiento | + posterior | = ahora | IDENT_CURRENT |',
             '|---|---|---|---|---|---|---|']
    for tabla, t in control['tablas'].items():
        filas.append(f"| `{tabla}` | {t['respaldo']:,} | {t.get('delta', '–')} | {t['congelamiento']:,} | "
                     f"{t.get('posterior', '–')} | {t['ahora']:,} | {t.get('ident_current') or '–'} |")
    partes.append('\n'.join(filas))
    folios = control['consumibles']['folios']
    partes.append('Folios (siguiente por serie): ' + ' · '.join(
        f"{s}: {folios['respaldo'][s]:,} → {folios['congelamiento'][s]:,} → {folios['ahora'][s]:,}"
        for s in sorted(folios['ahora'])) + f". Monedas: {control['catalogos']['monedas']} "
        f"({control['catalogos']['activas']} activas).")

    partes.append('## 3. Cifras de control por documento (criterios 7 y 8)')
    h = control['huellas_por_documento']
    partes.append(f"{h['documentos']:,} documentos, cada uno con su huella sha256 en `{h['archivo']}` (artefacto del "
                  f"CI; sha256 `{h['sha256']}`). Llave de negocio: orden = uetr + sucursal, operación = folio FX + "
                  'sucursal. cargado + no viaja = origen, por tipo y por cada grupo tipo + estado + mes.')
    filas = ['| tipo | origen | cargado | ' + ' | '.join(cifras.MOTIVOS) + ' | montos del origen |',
             '|---|---|---|' + '---|' * len(cifras.MOTIVOS) + '---|']
    for tipo, b in control['cifras']['tipos'].items():
        filas.append(f"| {tipo} | {b['origen']['documentos']:,} | {b['cargado']['documentos']:,} | "
                     + ' | '.join(f"{b['no_viaja'][m]['documentos']:,}" for m in cifras.MOTIVOS)
                     + f" | {_montos(b['origen']['montos'])} |")
    partes.append('\n'.join(filas))
    por_estado: dict[tuple[str, str], dict] = defaultdict(lambda: {'meses': 0, 'origen': 0, 'cargado': 0,
                                                                   'no_viaja': 0})
    for g in control['cifras']['grupos']:
        e = por_estado[(g['tipo'], g['estado'])]
        e['meses'] += 1
        e['origen'] += g['origen']['documentos']
        e['cargado'] += g['cargado']['documentos']
        e['no_viaja'] += sum(v['documentos'] for v in g['no_viaja'].values())
    filas = ['| tipo | estado | meses | origen | cargado | no viaja |', '|---|---|---|---|---|---|']
    filas += [f"| {t} | {e} | {v['meses']} | {v['origen']:,} | {v['cargado']:,} | {v['no_viaja']:,} |"
              for (t, e), v in sorted(por_estado.items())]
    partes.append(f"Por estado (los {len(control['cifras']['grupos'])} grupos tipo + estado + mes, con su huella, "
                  f"están en `{medir.CIFRAS}`):\n\n" + '\n'.join(filas))
    muestra = control.get('no_viaja_muestra', {})
    if muestra:
        partes.append('Lo que no viaja, por motivo (muestra):\n' + '\n'.join(
            f"- **{m}**: " + '; '.join(f"`{x['documento']}` ({x['estado']}, {x['mes']}): {x['motivo']}"
                                       for x in lista[:5]) for m, lista in muestra.items()))
    con = control['conciliacion']
    rr = con['re_registros_del_dia']
    partes.append(f"**Conciliación del delta por llave de negocio (criterio 7).** Re-registros del día del corte: "
                  f"{rr['llamadas']}: {rr['de_documentos_del_corte']} de documentos que ya estaban en la foto del "
                  f"corte y {rr['de_documentos_nuevos_del_dia']} de documentos dados de alta ese mismo día después del "
                  f"respaldo (viven enteros en el delta). Por llave: {con['por_llave']['duplicados']} duplicados y "
                  f"{con['por_llave']['registros_que_salen']} registros viejos que salen. Por id (control negativo): "
                  f"{con['por_id']['duplicados']} documentos quedan dos veces. Duplicados por documento: "
                  f"{len(control['duplicados_por_documento'])}.")
    filas = ['| control negativo | qué se planta | detectado | dónde |', '|---|---|---|---|']
    k = control['controles_negativos']
    if 'un_centavo' in k:
        u = k['un_centavo']
        filas.append(f"| un centavo | `{u['documento']}` +0.01 | {'sí' if u['detectado'] else 'NO'} | su huella y "
                     f"el grupo {' · '.join(u['grupo'])}; totales: {u['globales_distintos']} |")
    if 'grieta_utc' in k:
        g = k['grieta_utc']
        filas.append(f"| grieta UTC | el mes en UTC: {g['documentos_que_cambian_de_mes']:,} documentos cambian de mes "
                     f"| {'sí' if g['detectado'] else 'NO'} | {g['grupos_distintos']} grupos por mes; totales "
                     f"globales distintos: {g['globales_distintos']} |")
    if 'duplicado' in k:
        d = k['duplicado']
        filas.append(f"| duplicado | otro registro vigente de `{d['documento']}` | {'sí' if d['detectado'] else 'NO'}"
                     f" | duplicados por documento: {d['duplicados_por_documento']} |")
    partes.append('\n'.join(filas))

    partes.append('## 4. Huella versionada')
    filas = ['| archivo | sha256 | artefacto (id · digest de GitHub) |', '|---|---|---|']
    artefactos = huella.get('artefactos', {})
    for nombre, sha in huella['archivos'].items():
        a = artefactos.get(nombre, {})
        filas.append(f"| `{nombre}` | `{sha}` | {a.get('id', '–')} · `{a.get('digest', '–')}` |")
    partes.append('\n'.join(filas))
    partes.append('El job `corte` vuelve a medir en cada corrida y exige estos mismos sha256: las cifras no dependen '
                  'del reloj de la corrida. Si cambian a propósito (otro legado, otra forma canónica), se versionan de '
                  'nuevo con `python -m corte.veredicto <artefacto corte-medido> --versionar --artefactos <gh api …>`.')
    return '\n\n'.join(partes) + '\n'
