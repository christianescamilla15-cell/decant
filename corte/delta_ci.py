"""El delta del mismo día en el CI (S3 paso 4): el runbook de verdad sobre la base cerrada y el legado vivo, con sus
controles negativos.

    python -m corte.delta_ci --base corte/base --salida corte/delta-ci                    # restaura el volcado
    python -m corte.delta_ci --base corte/base --construir-base --salida corte/delta-ci   # sin volcado: 36 meses

Necesita el legado arriba después de `./ciclo.sh` (DECANT_SA_PASSWORD, DECANT_PUERTO) y PostgreSQL
(DECANT_PG_PASSWORD, DECANT_PG_PUERTO). Pasos:
1. El respaldo de ESTA corrida restaurado como `BFN_DIVISAS_CORTE` (el plan y los totales del origen hasta el corte).
2. La base cerrada: restaurada del volcado de la nocturna (`destino.dump` + `destino.json`) o, si no hay, construida
   (36 meses y cierre). Se verifica sin creerle (`corte/base.py`).
3. El delta desde el legado VIVO (`corte/runbook_delta.py`): los controles 1 a 3 (en ensayos), el ensayo verde,
   `aplicar`, la evidencia (conciliación por llave, altas fechadas hacia atrás, lo posterior al congelamiento), los
   controles 4 y 5 (el 5 revierte y vuelve a aplicar), las cifras de control contra las del paso 2 y, al final, el 6
   (cruza el punto de no retorno).
Controles negativos; cada uno tiene que FALLAR donde se dice:
1. un delta por FECHA pierde las 5 altas fechadas hacia atrás y la comparación las nombra;
2. un delta por id SIN conciliar por llave deja los re-registros del corte duplicados por documento;
3. un folio sin margen choca con los que el legado usó después del congelamiento;
4. repetir el delta se niega (el registro, la guarda del corte y el índice único de la base) y no duplica;
5. una reversa que no devuelve un valor previo la detecta la huella;
6. tras una acción de negocio, la reversa del delta se niega.
Deja `delta.json` y, con `--resumen`, el resumen del job. Sale con 1 si algo no cuadra o un control no falla.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from corte import base, caminos, carga_ci, delta, runbook, runbook_delta
from corte.carga import TABLAS
from corte.carga_ci import _negado
from corte.runbook import Negado, NoCuadra
from corte.runbook_delta import CIFRAS_PASO_2, DATOS

MUESTRA = delta.MUESTRA


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


def oraculos(vivo: dict, paso_2: dict) -> dict:
    """Lo que el delta tiene que dar, de fuentes que no son el delta: los choques que anotó el legado vivo y las cifras
    versionadas del paso 2."""
    choques = vivo['choques']
    return {'fechadas_hacia_atras': {int(f['id']): f for f in choques['altas_fechadas_hacia_atras']['filas']},
            'ordenes_posteriores': choques['documentos_tambien_en_tobe']['filas'],
            'folios_op_posteriores': choques['folios_op_tras_congelamiento']['folios'],
            're_registros_del_corte': paso_2['conciliacion']['re_registros_del_dia']['de_documentos_del_corte'],
            'muestra_salen': paso_2['conciliacion']['por_llave']['muestra_registros_que_salen'],
            'duplicados_por_id': paso_2['conciliacion']['por_id']['duplicados']}


# ── la base ─────────────────────────────────────────────────────────────────────────────────────────────────────

def preparar_base(args, ms_corte, p: dict, corte: dict) -> dict:
    hay = (args.base / base.DUMP).exists() and (args.base / base.META).exists()
    if hay:
        resultado = {'modo': 'restaurada del volcado', 'fuente': args.fuente,
                     'restaurar': base.restaurar(args.contenedor, args.base, args.destino_base)}
        meta = _json(args.base / base.META)
    elif args.construir_base:
        with runbook.conectar_destino(args.destino_base, crear=True) as pg:
            resultado = {'modo': 'construida en esta corrida (no había volcado)', 'fuente': args.fuente,
                         'construir': base.construir(pg, ms_corte, p, corte, args.margen_folios)}
        meta = None
    else:
        raise SystemExit(f'no hay volcado en {args.base} y no se pidió --construir-base')
    with runbook.conectar_destino(args.destino_base) as pg:
        resultado['verificacion'] = base.verificar(pg, ms_corte, meta, p, corte)
    if meta is not None:
        resultado['volcado'] = {'corrida': meta.get('corrida'), 'bytes': meta['dump']['bytes'],
                                'sha256': meta['dump']['sha256'], 'plan_sha': meta['plan_sha']}
    return resultado


# ── los controles negativos ─────────────────────────────────────────────────────────────────────────────────────

def control_por_fecha(pg, ms, d: dict, vivo: dict, guion: dict, oraculo: dict) -> dict:
    """1. El delta tomado por la fecha de NEGOCIO de la operación (lo que haría un delta «por fecha»): la comparación
    con el rango de la identidad nombra lo que pierde, y deben ser las altas que la sucursal reenvió fechadas hacia
    atrás (el oráculo: los choques que anotó el legado vivo)."""
    camino = next(c for c in caminos.CAMINOS if c.tabla == 'dbo.operacion' and c.control_negativo)
    limite = caminos.limites(camino.reloj, vivo, guion)
    cursor = ms.cursor()
    cursor.execute(camino.consulta, (limite['parametro'],))
    clases = caminos.por_sello(((i, caminos.sello(camino.reloj, s)) for i, s in cursor.fetchall()),
                               limite['desde'], limite['hasta'])
    por_fecha = delta.con_seleccion(d, 'operacion', clases.delta, 'fecha_operacion')
    antes = runbook.huella_destino(pg)
    visto, como = _negado(runbook_delta.cargar_delta, pg, por_fecha, confirmar=False)
    igual = runbook.huella_destino(pg) == antes
    faltan = sorted(set(d['identidad']['operacion']) - set(clases.delta))
    esperadas = sorted(oraculo['fechadas_hacia_atras'])
    return {'seleccion': f"fecha_operacion > {limite['desde']} (hora de negocio del respaldo)",
            'filas_por_fecha': len(clases.delta), 'filas_por_id': len(d['identidad']['operacion']),
            'pierde': [f"{i} ({d['nombres']['operacion'].get(i)})" for i in faltan], 'resultado': como,
            'destino_sin_cambios': igual,
            'detectado': visto and faltan == esperadas and all(f'{i} (' in como for i in esperadas) and igual,
            'regla': 'el delta va por id: uno por fecha pierde las altas con id nuevo y fecha vieja, y la comparación '
                     'con el rango de la identidad las nombra'}


def control_sin_conciliar(pg, d: dict, oraculo: dict) -> dict:
    """2. El delta por id SIN los UPDATE derivados de la bitácora (sin conciliar por llave): el registro viejo de cada
    re-registro sigue vigente y el documento queda dos veces."""
    antes = runbook.huella_destino(pg)
    viejos = sorted(k for k, c in d['cambios']['al_corte'].items() if c[-1].nuevo == 'REEMPLAZADA')
    try:
        runbook_delta.cargar_delta(pg, d, confirmar=False, conciliar=False)
        visto, como, detalle = False, 'no falló', {}
    except NoCuadra as error:
        visto, como, detalle = True, f'NoCuadra: {error}', error.detalle
    igual = runbook.huella_destino(pg) == antes
    dobles = detalle.get('muestra_duplicados', [])
    return {'duplicados_por_documento': detalle.get('duplicados'), 'esperados_paso_2': oraculo['duplicados_por_id'],
            'muestra': [f"{x['documento']}/{x['sucursal']} {x['ids']}" for x in dobles[:5]],
            'resultado': como[:600], 'destino_sin_cambios': igual,
            'detectado': (visto and detalle.get('duplicados') == oraculo['duplicados_por_id'] == len(viejos)
                          and all(x['ids'][0] in viejos for x in dobles) and igual),
            'regla': 'por id sólo entran altas: el registro viejo del re-registro sigue vigente y el documento queda '
                     'dos veces; conciliar por llave (UPDATE a REEMPLAZADA desde la bitácora) lo saca'}


def control_folio(pg, d: dict, sin_margen: dict[str, int], oraculo: dict) -> dict:
    """3. Los consumibles SIN margen (el `siguiente` del respaldo, como si el cierre no los hubiera subido): aun
    después de que el delta los sube por encima de sus propios folios, chocan con los que el legado usó tras el
    congelamiento."""
    antes = runbook.huella_destino(pg)
    with pg.transaction(force_rollback=True):
        for serie, n in sorted(sin_margen.items()):
            pg.execute('UPDATE legado.folio SET siguiente = %s WHERE serie = %s', (n, serie))
        try:
            runbook_delta.cargar_delta(pg, d, confirmar=False)
            visto, como, choques = False, 'no falló', []
        except NoCuadra as error:
            visto, como = True, f'NoCuadra: {error}'
            choques = error.detalle.get('folios', {}).get('choques', [])
    igual = runbook.huella_destino(pg) == antes
    op = next((c for c in choques if c.startswith('folio OP')), '')
    return {'siguiente_sin_margen': sin_margen, 'choques': choques, 'destino_sin_cambios': igual,
            'detectado': (visto and bool(op) and all(f in op for f in oraculo['folios_op_posteriores'])
                          and any(c.startswith('folio FX') for c in choques) and igual),
            'resultado': como[:600],
            'regla': 'el TO-BE numera desde el siguiente del destino: sin margen, choca con los folios que el legado '
                     'siguió usando después del congelamiento (y que el delta no trae)'}


def control_repetir(pg, d: dict) -> dict:
    """4. Repetir el delta ya aplicado: lo niega el registro (aplicar), la guarda del corte (ensayo) y, en la base, el
    índice único de «a lo más un delta aplicado». Nada se duplica."""
    import psycopg
    antes = runbook.huella_destino(pg)
    por_registro = _negado(runbook_delta.cargar_delta, pg, d, confirmar=True)
    por_guarda = _negado(runbook_delta.cargar_delta, pg, d, confirmar=False)
    try:
        with pg.transaction(force_rollback=True):
            pg.execute("INSERT INTO corte.carga_delta (plan_sha, estado, plan, reversa, huella_previa) "
                       "VALUES (%s, 'aplicado', '{}', '{}', '{}')", (d['sha'],))
        por_indice = (False, 'no chocó')
    except psycopg.errors.UniqueViolation as error:
        por_indice = (True, f'UniqueViolation: {str(error).splitlines()[0]}')
    igual = runbook.huella_destino(pg) == antes
    return {'aplicar': por_registro[1], 'ensayo': por_guarda[1], 'indice_de_la_base': por_indice[1],
            'destino_sin_cambios': igual,
            'detectado': por_registro[0] and por_guarda[0] and por_indice[0] and igual,
            'regla': 'el delta se aplica una vez: el registro, la guarda «sólo ids > corte» y el índice único lo '
                     'niegan, y el destino no cambia'}


def control_reversa_plantada(pg, d: dict, aplicado: dict, trabajo: Path) -> dict:
    """5. Una reversa PLANTADA que borra lo insertado pero no devuelve el valor previo de UN UPDATE: la huella la ve y
    no confirma. Luego la reversa buena vuelve a la huella previa y el delta se aplica otra vez (ensayo → aplicar),
    con la misma huella que la primera vez."""
    despues = runbook.huella_destino(pg)
    omitir = min(k for k, c in d['cambios']['al_corte'].items() if c[-1].nuevo == 'REEMPLAZADA')
    visto, como = _negado(runbook_delta.revertir_delta, pg, omitir=omitir)
    sigue_aplicado = runbook.huella_destino(pg) == despues
    buena = runbook_delta.revertir_delta(pg)
    vuelve = buena['ahora'] == aplicado['previa']
    runbook_delta.cargar_delta(pg, d, confirmar=False)
    otra = runbook_delta.cargar_delta(pg, d, confirmar=True, trabajo=trabajo)
    igual_que_antes = runbook.huella_destino(pg) == despues
    return {'omitida': f'legado.orden_pago #{omitir} (REEMPLAZADA → su valor previo ENVIADA)', 'resultado': como[:600],
            'la_plantada_no_confirma': sigue_aplicado,
            'reversa_buena': {'borradas': buena['borradas'], 'restauradas': buena['restauradas'],
                              'vuelve_a_la_huella_previa': vuelve, 'segundos': buena['segundos']},
            'reaplicado': {'segundos': otra['segundos'], 'misma_huella_que_la_primera_vez': igual_que_antes},
            'detectado': visto and 'orden_pago' in como and sigue_aplicado and vuelve and igual_que_antes,
            'regla': 'la reversa guarda los VALORES PREVIOS de cada UPDATE antes de aplicar; una que no los devuelve '
                     'deja otra huella y no confirma'}


def control_no_retorno(pg, d: dict) -> dict:
    """6. Una acción de negocio del TO-BE sobre una fila del delta registra el punto de no retorno: la reversa del delta
    se niega (volver a la huella previa borraría lo capturado)."""
    antes = runbook.huella_destino(pg)
    fila = d['identidad']['orden_pago'][0]
    pg.execute('INSERT INTO corte.accion_negocio (tabla, fila, accion) VALUES (%s, %s, %s)',
               ('legado.orden_pago', fila, 'cancelar'))
    punto = runbook.no_retorno(pg)
    visto, como = _negado(runbook_delta.revertir_delta, pg)
    igual = runbook.huella_destino(pg) == antes
    return {'accion': f'cancelar legado.orden_pago #{fila}', 'punto': punto, 'resultado': como[:600],
            'destino_sin_cambios': igual, 'detectado': visto and punto is not None and 'no retorno' in como and igual,
            'regla': 'desde la primera acción de negocio la reversa se niega: sólo hacia adelante'}


# ── la evidencia ────────────────────────────────────────────────────────────────────────────────────────────────

def evidencia(pg, d: dict, oraculo: dict) -> dict:
    """Lo que el delta dejó, contra los oráculos: las altas fechadas hacia atrás entran, lo posterior al congelamiento
    queda fuera (listado para el barrido) y los re-registros del corte se concilian por llave."""
    n = TABLAS['operacion'].nombres
    esperadas = sorted(oraculo['fechadas_hacia_atras'])
    filas = runbook_delta.presentes(pg, 'operacion', esperadas)
    atras = [{'id': f[0], 'folio': f[n.index('folio')], 'sucursal': f[n.index('sucursal')].strip(),
              'fecha_operacion': str(f[n.index('fecha_operacion')])} for f in filas]
    entran = ([x['id'] for x in atras] == esperadas
              and all(x['folio'] == oraculo['fechadas_hacia_atras'][x['id']]['folio'] for x in atras))
    post = d['posteriores']
    uetrs = [o['uetr'] for o in post['orden_pago']]
    en_destino = pg.execute('SELECT count(*) FROM legado.orden_pago WHERE uetr = ANY(%s::text[]) OR id > %s',
                            (uetrs, d['congelamiento']['orden_pago'])).fetchone()[0]
    siguiente = {s: n for s, n in pg.execute('SELECT serie, siguiente FROM legado.folio')}
    folios = sorted(o['folio'] for o in post['orden_pago'])
    oraculo_ordenes = sorted((o['uetr'], o['folio']) for o in oraculo['ordenes_posteriores'])
    fuera = {
        'ordenes': post['orden_pago'], 'operaciones': len(post['operacion']),
        'muestra_operaciones': [f"{o['id']} {o['folio']}" for o in post['operacion'][:MUESTRA]],
        **{t: len(post[t]) for t in ('partida_solicitada', 'partida_liquidada', 'bitacora')},
        'en_el_destino': en_destino,
        'folios_op': folios, 'siguiente_op_del_destino': siguiente.get('OP'),
        'coinciden_con_el_vivo': sorted((o['uetr'], o['folio']) for o in post['orden_pago']) == oraculo_ordenes
        and folios == sorted(oraculo['folios_op_posteriores']),
        'sin_choque_de_folio': all(int(f[3:]) < siguiente['OP'] for f in folios),
        'catalogo_posterior': d['catalogo_posteriores'],
    }
    conciliacion = runbook_delta.conciliacion(pg, d)
    conciliacion['esperados_paso_2'] = oraculo['re_registros_del_corte']
    conciliacion['misma_muestra_que_el_paso_2'] = conciliacion['ids_que_salen'][:len(oraculo['muestra_salen'])] == \
        oraculo['muestra_salen']
    conciliacion['ids_que_salen'] = conciliacion['ids_que_salen'][:MUESTRA]
    return {'fechadas_hacia_atras': {'filas': atras, 'entran': entran},
            'posteriores_al_congelamiento': fuera, 'conciliacion': conciliacion}


def _resumen_aplicado(aplicado: dict, d: dict) -> dict:
    v = aplicado['verificacion']
    return {'insertadas': aplicado['insertadas'], 'actualizadas': aplicado['actualizadas'],
            'cambios_por_estado': delta.resumen_de_cambios(d['cambios']),
            'catalogo': {'altas': [f[0] for f in d['catalogo']['insertar']], 'cambios': d['catalogo']['actualizar']},
            'secuencias': {'antes': {t: s['last_value'] for t, s in aplicado['previa']['secuencias'].items()},
                           'despues': aplicado['secuencias']},
            'folios': v['folios'], 'lotes': v['lotes'], 'duplicados': v['duplicados'],
            'derivados_rearmados': aplicado['derivados'], 'segundos': aplicado['segundos']}


# ── el resumen ──────────────────────────────────────────────────────────────────────────────────────────────────

def resumen(informe: dict) -> str:
    lineas = [f"## Delta del mismo día ({'verde' if informe.get('verde') else 'ROJO'})", '']
    b = informe.get('base', {})
    if b:
        r = b.get('restaurar') or b.get('construir') or {}
        v = b.get('verificacion', {})
        lineas.append(f"**Base:** {b['modo']} ({b.get('fuente') or 'sin fuente'}) en {r.get('segundos')} s"
                      + (f" · volcado {b['volcado']['bytes'] / 1e6:.0f} MB, sha256 `{b['volcado']['sha256'][:16]}…`"
                         if b.get('volcado') else '')
                      + f" · verificación: {'verde' if v.get('verde') else 'ROJA ' + str(v.get('faltas'))[:300]}"
                      + f" ({v.get('meses_aplicados')} meses, plan `{str(v.get('plan_sha'))[:12]}`, llaves foráneas "
                        f"{len(v.get('llaves_foraneas', []))}, {v.get('segundos')} s).")
    x = informe.get('delta')
    if x:
        lineas += ['', '| tabla | corte | congelamiento | insertadas | actualizadas |', '|---|---|---|---|---|']
        for t in delta.ORDEN_INSERTAR:
            lineas.append(f"| {t} | {informe['corte'][t]:,} | {informe['congelamiento'][t]:,} | "
                          f"{x['insertadas'][t]:,} | {x['actualizadas'].get(t, 0):,} |")
        lineas.append(f"| moneda | – | – | {x['insertadas']['moneda']} ({', '.join(x['catalogo']['altas'])}) | "
                      f"{x['actualizadas']['moneda']} ({x['catalogo']['cambios']}) |")
        cambios = x['cambios_por_estado']
        lineas += ['', f"Filas del corte actualizadas desde la bitácora: {cambios['al_corte']}; del delta, ya con su "
                       f"estado: {cambios['del_delta']}; cambios posteriores al congelamiento: "
                       f"{cambios['posteriores']}. Secuencias {x['secuencias']['antes']} → "
                       f"{x['secuencias']['despues']}. Derivados re-armados: {x['derivados_rearmados'] or 'ninguno'}."]
    e = informe.get('evidencia')
    if e:
        c, a, p = e['conciliacion'], e['fechadas_hacia_atras'], e['posteriores_al_congelamiento']
        lineas += ['', f"**Conciliación por llave:** {c['re_registros_de_documentos_del_corte']} re-registros de "
                       f"documentos del corte (paso 2: {c['esperados_paso_2']}), {c['salen']} registros viejos salen "
                       f"(REEMPLAZADA, con su vigente del delta), {c['duplicados_por_documento']} duplicados por "
                       "documento.",
                   f"**Altas fechadas hacia atrás:** {'entran' if a['entran'] else 'NO entran'}: "
                   + ', '.join(f"{r['id']} {r['folio']} {r['sucursal']} {r['fecha_operacion']}" for r in a['filas']),
                   f"**Fuera del delta, para el barrido:** {len(p['ordenes'])} órdenes "
                   f"({', '.join(o['folio'] + ' ' + o['uetr'][:8] for o in p['ordenes'])}), {p['operaciones']} "
                   f"operaciones, {p['partida_liquidada']} partidas del cliente, {p['partida_solicitada']} del "
                   f"corresponsal y {p['bitacora']} renglones de bitácora; en el destino: {p['en_el_destino']}. Folios "
                   f"OP ya usados por el legado; el destino numera desde OP-{p['siguiente_op_del_destino']:09d}: "
                   f"{'0 choques' if p['sin_choque_de_folio'] else 'CHOCAN'}."]
    k = informe.get('cifras')
    if k:
        lineas += ['', f"**Cifras de control contra el paso 2** (`{k['paso_2']['archivo']}`, sha256 "
                       f"`{k['paso_2']['sha256'][:16]}…`, {'el versionado' if k['paso_2']['firmado'] else 'NO firmado'}"
                       f"): {k['documentos_en_destino']:,} documentos en el destino, {k['grupos_comparados']} grupos "
                       f"tipo + estado + mes, {'cuadran' if k['cuadra'] else 'NO cuadran: ' + str(k['faltas'][:3])}."]
        for t, v in k['por_tipo'].items():
            nv = ' + '.join(f'{m} {n:,}' for m, n in v['no_viaja_paso_2'].items() if n)
            lineas.append(f"- {t}: destino {v['destino']:,} (= cargado del paso 2 {v['cargado_paso_2']:,}) + "
                          f"no viaja {nv or 0} = origen del paso 2 {v['origen_paso_2']:,}")
    if informe.get('controles'):
        lineas += ['', '| control negativo | detectado | cómo |', '|---|---|---|']
        for nombre, c in informe['controles'].items():
            lineas.append(f"| {nombre} | {'sí' if c.get('detectado') else 'NO'} | "
                          f"{str(c.get('resultado') or c.get('aplicar') or c.get('choques'))[:260]} |")
    lineas += ['', 'Tiempos: ' + ' · '.join(f'{k} {v} s' for k, v in informe['segundos'].items()) + '.']
    lineas += [f'- ✘ {f}' for f in informe.get('faltas', [])]
    return '\n'.join(lineas) + '\n'


# ── el conductor ────────────────────────────────────────────────────────────────────────────────────────────────

def correr(pg, ms, corte: dict, tope: dict, vivo: dict, guion: dict, oraculo: dict, informe: dict,
           trabajo: Path) -> None:
    s, c = informe['segundos'], informe['controles']
    t = time.monotonic()
    informe['preparar'] = runbook_delta.preparar(pg)
    d = runbook_delta.leer_delta(pg, ms, corte, tope, vivo)
    informe['plan'] = runbook_delta.resumen_del_plan(d)
    s['leer_delta'] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    c['1_delta_por_fecha'] = control_por_fecha(pg, ms, d, vivo, guion, oraculo)
    c['2_por_id_sin_conciliar'] = control_sin_conciliar(pg, d, oraculo)
    c['3_folio_sin_margen'] = control_folio(pg, d, vivo['al_respaldo']['folios'], oraculo)
    s['controles_1_a_3'] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    ensayo = runbook_delta.cargar_delta(pg, d, confirmar=False)
    s['ensayo'] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    aplicado = runbook_delta.cargar_delta(pg, d, confirmar=True, trabajo=trabajo)
    s['aplicar'] = round(time.monotonic() - t, 1)
    informe['delta'] = _resumen_aplicado(aplicado, d)
    informe['delta']['ensayo'] = ensayo['segundos']
    informe['evidencia'] = evidencia(pg, d, oraculo)
    t = time.monotonic()
    c['4_repetir'] = control_repetir(pg, d)
    c['5_reversa_sin_valor_previo'] = control_reversa_plantada(pg, d, aplicado, trabajo)
    s['controles_4_y_5'] = round(time.monotonic() - t, 1)
    t = time.monotonic()
    informe['cifras'] = runbook_delta.cifras_del_destino(pg, tope)
    s['cifras'] = round(time.monotonic() - t, 1)
    c['6_reversa_tras_no_retorno'] = control_no_retorno(pg, d)


def faltas_de(informe: dict) -> list[str]:
    faltas = list(informe.get('faltas', []))
    v = informe.get('base', {}).get('verificacion', {})
    faltas += [f'base: {f}' for f in v.get('faltas', [])]
    faltas += [f'plan del delta: {f}' for f in informe.get('plan', {}).get('faltas', [])]
    faltas += [f'control {n} no detectado' for n, c in informe.get('controles', {}).items() if not c.get('detectado')]
    e = informe.get('evidencia')
    if e:
        if not e['fechadas_hacia_atras']['entran']:
            faltas.append('las altas fechadas hacia atrás no entraron')
        p = e['posteriores_al_congelamiento']
        if p['en_el_destino'] or not p['coinciden_con_el_vivo'] or not p['sin_choque_de_folio']:
            faltas.append(f"lo posterior al congelamiento: en el destino {p['en_el_destino']}, coincide con el vivo "
                          f"{p['coinciden_con_el_vivo']}, sin choque de folio {p['sin_choque_de_folio']}")
        c = e['conciliacion']
        if not c['concilia'] or c['re_registros_de_documentos_del_corte'] != c['esperados_paso_2'] \
                or not c['misma_muestra_que_el_paso_2']:
            faltas.append(f"conciliación: {c['salen']} salen de {c['re_registros_de_documentos_del_corte']} "
                          f"(paso 2: {c['esperados_paso_2']}), {c['duplicados_por_documento']} duplicados")
    if informe.get('cifras') and not informe['cifras']['cuadra']:
        faltas += [f'cifras: {f}' for f in informe['cifras']['faltas'][:10]]
    if 'cifras' not in informe and 'error' not in informe:
        faltas.append('el delta no llegó a las cifras de control')
    return faltas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.delta_ci', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', type=Path, default=Path('corte/base'), help='carpeta con destino.dump y destino.json')
    parser.add_argument('--construir-base', action='store_true', help='sin volcado: cargar los 36 meses y cerrar')
    parser.add_argument('--fuente', default='', help='de dónde vino el volcado (para el resumen)')
    parser.add_argument('--contenedor', default='decant-pg-delta')
    parser.add_argument('--destino-base', default=runbook.DESTINO_BASE)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--manifiesto', type=Path, default=None)
    parser.add_argument('--resumen', type=Path, default=None)
    parser.add_argument('--margen-folios', type=int, default=10_000)
    args = parser.parse_args(argv)
    t0 = time.monotonic()
    args.salida.mkdir(parents=True, exist_ok=True)
    informe: dict = {'version': 1, 'segundos': {}, 'controles': {}, 'faltas': []}
    try:
        manifiesto = args.manifiesto or runbook._ultimo_manifiesto()
        if manifiesto is None:
            raise SystemExit('falta el manifiesto del respaldo: corre antes ./ciclo.sh')
        t = time.monotonic()
        informe['origen'] = carga_ci.restaurar_corte(manifiesto)
        corte, tope, vivo = runbook_delta.contexto(manifiesto)
        guion = _json(runbook_delta.ultimo(DATOS, 'delta_*.json'))
        oraculo = oraculos(vivo, _json(CIFRAS_PASO_2))
        informe['corte'], informe['congelamiento'] = corte, tope
        with runbook.conectar_origen() as ms_corte:
            p = runbook.leer_plan(ms_corte, corte)
            informe['base'] = preparar_base(args, ms_corte, p, corte)
        informe['segundos']['base'] = round(time.monotonic() - t, 1)
        if informe['base']['verificacion']['verde']:
            with runbook.conectar_destino(args.destino_base) as pg, \
                    runbook.conectar_origen(runbook_delta.ORIGEN_VIVO) as ms:
                correr(pg, ms, corte, tope, vivo, guion, oraculo, informe, args.salida)
    except (Negado, NoCuadra) as error:
        informe['faltas'].append(f'{type(error).__name__}: {error}'[:3000])
        informe['error'] = traceback.format_exc()
    except Exception as error:      # cualquier otra: el informe y el resumen salen igual, y el job en rojo
        informe['faltas'].append(f'{type(error).__name__}: {error}'[:3000])
        informe['error'] = traceback.format_exc()
    informe['segundos']['total'] = round(time.monotonic() - t0, 1)
    informe['faltas'] = faltas_de(informe)
    informe['verde'] = not informe['faltas']
    (args.salida / 'delta.json').write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str) + '\n',
                                            encoding='utf-8')
    texto = resumen(informe)
    print(texto)
    if informe.get('error'):
        print(informe['error'], file=sys.stderr)
    if args.resumen:
        with args.resumen.open('a', encoding='utf-8') as salida:
            salida.write(texto)
    return 0 if informe['verde'] else 1


if __name__ == '__main__':
    sys.exit(main())
