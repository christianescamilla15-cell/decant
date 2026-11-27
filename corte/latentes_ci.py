"""Las trampas LATENTES con el plan variado, en el CI (S3 paso 6; ADR 0011 y 0014; criterio 2 del plan).

    python -m corte.latentes_ci --base corte/base --salida corte/latentes-ci              # PR: lo pesado en muestra
    python -m corte.latentes_ci --base corte/base --salida corte/latentes-ci --completo   # de noche: todo

Necesita `./ciclo.sh` (el respaldo fechado), el legado arriba (DECANT_SA_PASSWORD, DECANT_PUERTO) y PostgreSQL
(DECANT_PG_PASSWORD, DECANT_PG_PUERTO). Reusa el arnés del paso 5 (`corte/estado_ci.py`):
1. El respaldo de ESTA corrida como `BFN_DIVISAS_CORTE` y la base cerrada (el volcado de la nocturna, restaurado y
   verificado sin creerle, o construida): el estado del respaldo en los dos motores.
2. La copia temporal del paso 5 (esquema `estado`, verificada igual al original) y, en ella, las copias de los dos
   objetos latentes: tal cual, con cada pista de variante y con el parche del TO-BE. Se verifica que el respaldo trae el
   código del repositorio, que cada copia guardada es su transformación y que nada de la copia depende de `dbo`.
3. Cada variante sobre su universo (todas las entradas donde el orden decide), en una transacción revertida con la
   guarda de `@@TRANCOUNT` en cada llamada; después, su plan REAL de la caché (`query_plan_hash`, showplan, DOP).
4. El TO-BE (`oraculo.TOBE`) sobre la base cerrada para todas las entradas, dentro de una transacción revertida; una
   muestra por entrada y sin índices comprueba que es la misma consulta.
5. El legado contra sí mismo y contra el TO-BE, cada diferencia arbitrada; los controles (el mismo plan no detecta; el
   parche hace coincidir todo); la aceptación, con el nombre de la trampa de los catálogos sellados.
Deja `latentes.json`, los showplan en `planes/` y, con `--resumen`, el resumen del job. Sale con 1 si algo no cuadra.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from pathlib import Path

from corte import (
    base,
    carga_ci,
    codigo,
    delta_ci,
    estado,
    estado_ci,
    latentes,
    oraculo,
    runbook,
    runbook_delta,
    trampas,
)
from corte.carga import TABLAS
from corte.estado import ESQUEMA, NoSeCopia
from corte.latentes import OBJETOS, Objeto, Variante
from corte.runbook import Negado, NoCuadra
from corte.sql import leer_scripts
from radiografia.veredictos import revertida

# Lo que dicen los catálogos sellados del tamaño de cada universo: sólo para REPORTAR si coincide, después de medir.
DEL_CATALOGO = {'r1-T1': ('dbo.sp_reporte_posicion', 9_341, 'pares día-moneda'),
                'r2-T2': ('dbo.sp_constancia_operacion', 104_773, 'operaciones con varias órdenes')}
POR_ENTRADA = 25         # entradas del TO-BE corridas una por una (sin índices) contra la consulta de todas a la vez
TROZO = 20_000


# ── las copias de los dos objetos ───────────────────────────────────────────────────────────────────────────────

def copias_necesarias(objeto: Objeto) -> list[tuple[Variante, bool]]:
    """Cada procedimiento que la medición crea en la copia: tal cual, con el parche, y uno por pista (con y sin el
    parche). Los lotes sueltos, la caché repetida y las estadísticas usan la copia tal cual (o su texto)."""
    resultado = [(latentes.TAL_CUAL, False), (latentes.TAL_CUAL, True)]
    for v in latentes.VARIANTES[objeto.id]:
        if v.pista is not None and not v.lote:
            resultado.append((v, False))
            if v in latentes.con_parche(objeto):
                resultado.append((v, True))
    return resultado


def copiar_latentes(ms) -> dict:
    """En la copia temporal (ya verificada por el paso 5): cada objeto con el código del RESPALDO (que tiene que ser el
    del repositorio) transformado por `estado.copiar`, con sus variantes; y el lote suelto de cada uno."""
    t0 = time.monotonic()
    cursor = ms.cursor()
    del_codigo = {m.id: estado_ci.normal_de_modulo(m.texto)
                  for m in leer_scripts(sorted(codigo.SQL.glob('*.sql')), codigo.RAIZ, codigo.PRINCIPAL).modulos}
    conocidos = {f'dbo.{t}' for t in TABLAS} | {o.id for o in OBJETOS}
    resultado, faltas, lotes = {}, [], {}
    for objeto in OBJETOS:
        cursor.execute(estado_ci.DEFINICION, (objeto.id,))
        original = (cursor.fetchone()[0] or '').strip()
        info = {'igual_al_repositorio': estado_ci.normal_de_modulo(original) == del_codigo.get(objeto.id),
                'copias': {}}
        if not info['igual_al_repositorio']:
            faltas.append(f'{objeto.id}: el respaldo no trae el mismo código que el repositorio')
        for v, parche in copias_necesarias(objeto):
            texto, reemplazos = latentes.texto_de_variante(original, objeto, v, parche)
            c = estado.copiar(texto, conocidos)
            if c.cuenta.get('reloj') or c.emulados:
                raise NoSeCopia(f'{objeto.id}: un lector con reloj o con efectos fuera de la base no es de este paso')
            nombre = latentes.nombre_de_copia(objeto, v, parche)
            ddl = latentes.renombrar(c.texto, nombre)
            cursor.execute(ddl)
            cursor.execute(estado_ci.DEFINICION, (nombre,))
            guardado = (cursor.fetchone()[0] or '').strip()
            info['copias'][nombre] = {'variante': v.id, 'parche': parche, 'reemplazos': len(reemplazos),
                                      'copia_igual_a_la_transformacion': guardado == ddl}
            if guardado != ddl:
                faltas.append(f'{nombre}: la copia guardada no es la transformación del original')
        for v in latentes.VARIANTES[objeto.id]:
            if not v.lote:
                continue
            for parche in (False, True):
                texto, _r = latentes.texto_de_variante(original, objeto, v, parche)
                lotes[(objeto.id, v.id, parche)] = latentes.lote_suelto(estado.copiar(texto, conocidos).texto, objeto,
                                                                        v, parche)
        info['lotes'] = sorted(f"{v}{' (con el parche)' if p else ''}" for o, v, p in lotes if o == objeto.id)
        resultado[objeto.id] = info
    cursor.execute(estado_ci.DEPENDENCIAS)
    nombres = {f'{t}' for t in TABLAS} | {x.split('.')[1] for o in resultado.values() for x in o['copias']}
    malas = [list(f) for f in cursor.fetchall() if f[3] in nombres and (f[1] is not None or f[2] != ESQUEMA)]
    if malas:
        faltas.append(f'la copia de los latentes depende de objetos fuera de `estado`: {malas[:5]}')
    if faltas:
        raise NoCuadra(faltas)
    return {'objetos': resultado, 'dependencias': 'ninguna fuera de `estado`',
            'segundos': round(time.monotonic() - t0, 1), '_lotes': lotes}


# ── una variante sobre sus entradas ─────────────────────────────────────────────────────────────────────────────

def paralelismo(ms) -> dict:
    cursor = ms.cursor()
    cursor.execute(latentes.PARALELISMO)
    maxdop, umbral, cpus, de_la_base = cursor.fetchone()
    return {'max_degree_of_parallelism': maxdop, 'cost_threshold_for_parallelism': umbral, 'cpus': cpus,
            'maxdop_de_la_base': de_la_base}


def planes_de_la_copia(ms) -> list[str]:
    cursor = ms.cursor()
    cursor.execute(latentes.PLANES_DE_LA_COPIA)
    return [h for (h,) in cursor.fetchall()]


def preparar(ms, objeto: Objeto, objetos: list[dict]) -> dict:
    """«Estadísticas y caché», sólo en la copia: UPDATE STATISTICS … WITH FULLSCAN de las tablas que el objeto lee y sus
    planes (los de la copia) fuera de la caché, uno por uno. La caché y las estadísticas del original no se tocan."""
    t0 = time.monotonic()
    cursor = ms.cursor()
    lee = sorted(t.removeprefix('dbo.') for t in estado.unidad(objetos, objeto.id)['efectivo']['lee']
                 if t.removeprefix('dbo.') in TABLAS)
    for t in lee:
        cursor.execute(ESTADISTICAS_MS[t])
    antes = planes_de_la_copia(ms)
    for h in antes:
        cursor.execute(latentes.SACAR_PLAN, (h,))
    quedan = planes_de_la_copia(ms)
    return {'tablas': [f'{ESQUEMA}.{t}' for t in lee], 'planes_sacados': len(antes), 'planes_que_quedan': len(quedan),
            'segundos': round(time.monotonic() - t0, 1)}


ESTADISTICAS_MS = {t: f'UPDATE STATISTICS {ESQUEMA}.{t} WITH FULLSCAN' for t in TABLAS}


def correr(ms, objeto: Objeto, v: Variante, parche: bool, entradas: list, lote: str | None) -> dict:
    """La variante sobre sus entradas, en UNA transacción revertida (con la guarda de @@TRANCOUNT en cada llamada, en
    el servidor); su salida y, después, su plan de la caché."""
    import pymssql
    t0 = time.monotonic()
    cursor = ms.cursor()
    llamada = latentes.llamada_de(objeto, v, parche)
    conductor = latentes.conductor(objeto, llamada, lote=v.lote)
    resultado = {'variante': v.id, 'parche': parche, 'entradas': len(entradas), 'error': None, 'guarda': None}
    with revertida(cursor):
        cursor.execute(latentes.tablas_temporales(objeto))
        for i in range(0, len(entradas), TROZO):
            cursor.execute(latentes.cargar_entradas(objeto), (','.join(latentes.canonico(x) for x in
                                                                       entradas[i:i + TROZO]),))
        try:
            if v.lote:
                cursor.execute(conductor, (lote,))
            else:
                cursor.execute(conductor)
            t_inicio, t_fin, roto, hechas = cursor.fetchone()
        except pymssql.Error as error:
            resultado['error'] = str(error)[:800]
            resultado['no_compila'] = bool(error.args) and error.args[0] == latentes.NO_COMPILA
            cursor.execute('SELECT @@TRANCOUNT')
            t_inicio, t_fin, roto, hechas = 1, cursor.fetchone()[0], None, None
        if resultado.get('no_compila'):
            # la pista no se puede cumplir: el procedimiento no corrió y el servidor revirtió la transacción por el
            # error de compilación; no es un ROLLBACK del objeto (la guarda es para eso)
            resultado['revertida_por_el_servidor'] = t_fin == 0
        else:
            resultado['guarda'] = estado.guarda_trancount(llamada, t_inicio, t_fin) or (
                f'{llamada}: @@TRANCOUNT cambió en la entrada {roto}' if roto else None)
        resultado['llamadas'] = hechas
        filas = []
        if resultado['error'] is None and resultado['guarda'] is None:
            cursor.execute(latentes.leer_salida(objeto))
            filas = cursor.fetchall()
    resultado['segundos'] = round(time.monotonic() - t0, 1)
    resultado['_salida'] = latentes.por_unidad(objeto, filas)
    resultado['renglones'] = len(filas)
    marca = f"%/* {latentes.MARCA}:{objeto.id}:{'parche:' if parche else ''}{v.sufijo} */%"
    cursor.execute(latentes.PLANES, (None, marca) if v.lote else (latentes.nombre_de_copia(objeto, v, parche), ''))
    resultado['plan'] = latentes.plan_de(cursor.fetchall(), objeto)
    return resultado


def control_de_dato(ms, objeto: Objeto, universo: list) -> dict | None:
    """El control del comparador por DATO (`latentes.CONTROL_DE_DATO`): en UNA transacción revertida, la fila vigente
    deja de ser la última y la copia tal cual se compara con la copia con el parche del TO-BE sobre esas entradas.
    Tienen que diferir en todas: si no, la comparación sería ciega a la latente aunque el plan cambiara."""
    if objeto.id not in latentes.CONTROL_DE_DATO:
        return None
    que, cambio = latentes.CONTROL_DE_DATO[objeto.id]
    t0 = time.monotonic()
    entradas = latentes.muestra(universo, latentes.CADA_CONTROL_DE_DATO)
    cursor = ms.cursor()
    salidas, guardas = {}, []
    with revertida(cursor):
        cursor.execute(latentes.tablas_temporales(objeto))
        cursor.execute(latentes.cargar_entradas(objeto), (','.join(latentes.canonico(x) for x in entradas),))
        cursor.execute(latentes.RELOJ_DE_LA_COPIA)
        cursor.execute(cambio)
        tocadas = cursor.rowcount
        for parche in (False, True):
            cursor.execute('TRUNCATE TABLE #salida')
            llamada = latentes.llamada_de(objeto, latentes.TAL_CUAL, parche)
            cursor.execute(latentes.conductor(objeto, llamada))
            t_inicio, t_fin, roto, _hechas = cursor.fetchone()
            guarda = estado.guarda_trancount(llamada, t_inicio, t_fin) or (
                f'{llamada}: entrada {roto}' if roto else None)
            if guarda:
                guardas.append(guarda)
            cursor.execute(latentes.leer_salida(objeto))
            salidas[parche] = latentes.por_unidad(objeto, cursor.fetchall())
    comp = latentes.comparar(objeto, salidas[False], salidas[True])
    return {'que': que, 'entradas': len(entradas), 'cada': latentes.CADA_CONTROL_DE_DATO, 'filas_cambiadas': tocadas,
            'distintas': comp['distintas'], 'columnas': comp['columnas'], 'guardas': guardas,
            'detectado': not guardas and comp['distintas'] == len(entradas),
            'lectura': 'dato, no plan: no cuenta como detección de la latente; dice que la comparación no es ciega',
            'segundos': round(time.monotonic() - t0, 1)}


# ── el TO-BE ────────────────────────────────────────────────────────────────────────────────────────────────────

def correr_tobe(pg, objeto: Objeto, entradas: list) -> dict:
    """La consulta del TO-BE (la del oráculo) sobre la base cerrada: primero una muestra por entrada, tal cual y sin
    índices; luego, con los índices que tiene el legado (sólo dentro de la transacción revertida), para todas las
    entradas a la vez. Las dos tienen que coincidir en la muestra: es la misma consulta, y el TO-BE no depende del
    plan."""
    t0 = time.monotonic()
    consulta = oraculo.TOBE[objeto.id][0]
    parametro = 'fecha' if objeto is latentes.R1_T1 else 'op'
    paso = max(1, len(entradas) // POR_ENTRADA)
    muestra = entradas[::paso][:POR_ENTRADA]
    nombres = ['entrada', *(c for c, _t in objeto.salida)]
    with pg.transaction(force_rollback=True):
        una_por_una = []
        for x in muestra:
            cursor = pg.execute(consulta, {parametro: x})
            una_por_una += [(x, *f) for f in cursor.fetchall()]
        for ddl in latentes.INDICES_TOBE:
            pg.execute(ddl)
        cursor = pg.execute(latentes.tobe_para_todas(objeto, consulta), {'entradas': entradas})
        columnas = [d.name for d in cursor.description]
        todas = cursor.fetchall()
    if columnas != nombres:
        raise NoCuadra([f'{objeto.id}: el TO-BE devuelve {columnas}, se esperaba {nombres}'])
    salida = latentes.por_unidad(objeto, todas)
    sola = latentes.por_unidad(objeto, una_por_una)
    fidelidad = latentes.comparar(objeto, sola, salida, sobre={latentes.canonico(x) for x in muestra})
    return {'_salida': salida, 'renglones': len(todas), 'entradas': len(entradas),
            'por_entrada': {'entradas': len(muestra), 'distintas': fidelidad['distintas'],
                            'que': 'la consulta del oráculo por entrada, sin índices, contra la de todas las entradas '
                                   'con los índices del legado'},
            'segundos': round(time.monotonic() - t0, 1)}


# ── medir ───────────────────────────────────────────────────────────────────────────────────────────────────────

def _resumen_corrida(c: dict, base: dict | None, tobe: dict, objeto: Objeto, cand: dict, cada: int) -> dict:
    """La corrida en el informe: su plan, si cambió respecto a la base (y qué), y su salida contra la base y contra el
    TO-BE, con cada diferencia arbitrada."""
    sobre = {latentes.canonico(x) for x in c['_entradas']}
    salida = c['_salida']
    r = {'entradas': c['entradas'], 'cada': cada, 'renglones': c['renglones'], 'llamadas': c['llamadas'],
         'error': c['error'], 'no_compila': c.get('no_compila', False), 'guarda': c['guarda'],
         'segundos': c['segundos'], 'plan': c['plan']}
    r['contra_tobe'] = latentes.comparar(objeto, salida, tobe['_salida'], sobre=sobre)
    if base is not None:
        r['plan_cambio'] = latentes.plan_cambio(c['plan'], base['plan'])
        r['que_cambio'] = latentes.que_cambio(c['plan'], base['plan'])
        r['contra_tal_cual'] = latentes.comparar(objeto, salida, base['_salida'], sobre=sobre)
    else:
        r['contra_tal_cual'] = {'distintas': 0, 'unidades': len(salida), 'columnas': {}, '_llaves': []}
    arbitraje = {}
    for lado, otro, comp in (('contra la copia tal cual', base, r['contra_tal_cual']),
                             ('contra el TO-BE', tobe, r['contra_tobe'])):
        if otro is not None and comp['distintas'] and not r['no_compila']:
            arbitraje[lado] = latentes.arbitrar(objeto, salida, otro['_salida'], comp['_llaves'], cand)
    r['arbitraje'] = arbitraje
    return r


def medir(ms, pg, objetos: list[dict], lotes: dict, completo: bool, segundos: dict) -> dict:
    """Las variantes de los dos objetos en TRES fases, para que ninguna herede lo que cambió otra: (1) todas las que
    no tocan las estadísticas, de los dos objetos; (2) «estadísticas y caché», que recalcula las de la copia; (3) las
    mismas con el parche del TO-BE. Cada corrida se resume en cuanto termina: en memoria sólo quedan la copia tal cual
    de cada objeto (con y sin parche) y su TO-BE."""
    t = time.monotonic()
    estado_de: dict[str, dict] = {}
    for objeto in OBJETOS:
        cursor = ms.cursor()
        cursor.execute(objeto.universo)
        universo = [f[0] for f in cursor.fetchall()]
        cursor.execute(latentes.CANDIDATOS_MS[objeto.id])
        cand = latentes.candidatos(objeto, cursor.fetchall())
        tobe = correr_tobe(pg, objeto, universo)
        estado_de[objeto.id] = {'universo': universo, 'cand': cand, 'tobe': tobe, 'bases': {}, 'resultado': {
            'objeto': objeto.id, 'universo': len(universo), 'unidades': len(tobe['_salida']),
            'tobe': {k: v for k, v in tobe.items() if not k.startswith('_')}, 'preparaciones': {},
            'corridas': {}, 'con_parche': {}}}
    segundos['tobe'] = round(time.monotonic() - t, 1)

    def una(objeto: Objeto, v: Variante, parche: bool) -> None:
        e = estado_de[objeto.id]
        r = e['resultado']
        if v.preparar:
            r['preparaciones'][f"{v.id}{' (con el parche)' if parche else ''}"] = preparar(ms, objeto, objetos)
        cada = latentes.cada_cuanto(objeto, v, completo)
        entradas = latentes.muestra(e['universo'], cada)
        c = correr(ms, objeto, v, parche, entradas, lotes.get((objeto.id, v.id, parche)))
        c['_entradas'] = entradas
        base = e['bases'].get(parche)
        r['con_parche' if parche else 'corridas'][v.id] = _resumen_corrida(c, base, e['tobe'], objeto, e['cand'],
                                                                          cada)
        if v is latentes.TAL_CUAL:
            e['bases'][parche] = c

    for fase, (parche, preparan) in enumerate(((False, False), (False, True), (True, None)), 1):
        t = time.monotonic()
        for objeto in OBJETOS:
            variantes = latentes.con_parche(objeto) if parche else latentes.VARIANTES[objeto.id]
            for v in variantes:
                if preparan is None or v.preparar == preparan:
                    una(objeto, v, parche)
        segundos[f'fase_{fase}'] = round(time.monotonic() - t, 1)
    resultado = {}
    for objeto in OBJETOS:
        r = estado_de[objeto.id]['resultado']
        r['veredicto'] = latentes.veredicto(objeto, r['corridas'], r['con_parche'])
        r['control_de_dato'] = control_de_dato(ms, objeto, estado_de[objeto.id]['universo'])
        resultado[objeto.id] = r
    return resultado


def guardar_planes(salida: Path, medido: dict) -> list[str]:
    """Cada plan distinto de cada variante como .sqlplan (el showplan que abre cualquier herramienta de SQL Server)."""
    carpeta = salida / 'planes'
    carpeta.mkdir(parents=True, exist_ok=True)
    escritos = []
    for objeto, m in medido.items():
        for clase, grupo in (('', m['corridas']), ('__parche', m['con_parche'])):
            for v, c in grupo.items():
                for h, xml in (c['plan'].get('_xml') or {}).items():
                    nombre = re.sub(r'[^\w.-]+', '_', f'{objeto}__{v}{clase}__{h}') + '.sqlplan'
                    (carpeta / nombre).write_text(xml, encoding='utf-8')
                    escritos.append(nombre)
    return sorted(escritos)


# ── el resumen ──────────────────────────────────────────────────────────────────────────────────────────────────

def _n(x) -> str:
    return '–' if x is None else f'{x:,}'


def resumen(informe: dict) -> str:
    lineas = [f"## Latentes con el plan variado ({'verde' if informe.get('verde') else 'ROJO'})", '']
    b = informe.get('base', {})
    if b:
        lineas.append(f"**Base de referencia (TO-BE):** {b.get('modo')} ({b.get('fuente') or 'sin fuente'}) · "
                      f"verificación {'verde' if b.get('verificacion', {}).get('verde') else 'ROJA'}. **Alcance:** "
                      f"{'todo el universo' if informe.get('completo') else 'PR (lo pesado en muestra)'}.")
    p = informe.get('paralelismo')
    if p:
        lineas.append(f"**Servidor:** max degree of parallelism {p['max_degree_of_parallelism']} · cost threshold "
                      f"{p['cost_threshold_for_parallelism']} · {p['cpus']} CPU · MAXDOP de la base "
                      f"{p['maxdop_de_la_base']} (las variantes van en la copia, nunca en la configuración).")
    for objeto, m in informe.get('latentes', {}).items():
        v = m['veredicto']
        nombre = '; '.join(informe.get('nombres', {}).get(objeto, [])) or 'sin nombre en los catálogos'
        lineas += ['', f"### {objeto}: {v['estado']}", '',
                   f"{v['que']}. Universo: {m['universo']:,} entradas, {m['unidades']:,} unidades. Trampa del "
                   f'catálogo (después de detectar): {nombre}.', '',
                   '| variante | entradas | plan real (showplan) | ¿cambió el plan? | contra la copia tal cual | '
                   'contra el TO-BE | s |', '|---|---|---|---|---|---|---|']
        for f in v['variantes']:
            cambio = {None: '–', True: f"sí: {f.get('que_cambio')}", False: 'no'}[f['plan_cambio']]
            etiqueta = f"{f['variante']}{' (forzada)' if f['forzada'] else ''}"
            muestra = f" (1 de {f['cada']})" if f['cada'] > 1 else ''
            lineas.append(f"| {etiqueta} | {f['entradas']:,}{muestra} | {f['acceso']} | {cambio} | "
                          f"{_n(f['contra_tal_cual'])} | {_n(f['contra_tobe'])} | {f['segundos']} |")
        c = v['controles']
        lineas += ['', '| control | se cumple | cifra |', '|---|---|---|',
                   f"| el mismo plan no detecta | {'sí' if c['mismo_plan_no_detecta']['detectado'] else 'NO'} | "
                   f"con el mismo plan: {', '.join(c['mismo_plan_no_detecta']['variantes_con_el_mismo_plan']) or '–'}"
                   f"; con el mismo plan y otra salida: "
                   f"{', '.join(c['mismo_plan_no_detecta']['con_el_mismo_plan_y_otra_salida']) or 'ninguna'} |",
                   f"| con el parche del TO-BE, todo coincide | {'sí' if c['parche']['detectado'] else 'NO'} | "
                   + ' · '.join(f"{k} {x['contra_tal_cual']}/{x['contra_tobe']}"
                                for k, x in c['parche']['variantes'].items()) + ' (contra tal cual / TO-BE) |']
        if v['tal_cual_contra_tobe']:
            lineas.append(f"- ✘ la copia TAL CUAL ya difiere del TO-BE en {v['tal_cual_contra_tobe']:,} de "
                          f"{m['unidades']:,} unidades ({nombre}; {latentes.DEFECTO_LEGADO}).")
        for f in v['variantes']:
            if f['contra_tal_cual'] and f['plan_cambio']:
                lineas.append(f"- ✘ el legado no coincide consigo mismo: «{f['variante']}»"
                              f"{' (forzada)' if f['forzada'] else ''} da otra salida en {f['contra_tal_cual']:,} de "
                              f"{f['unidades']:,} unidades ({nombre}; {latentes.DEFECTO_LEGADO}).")
        d = m.get('control_de_dato')
        if d:
            lineas.append(f"- control del comparador por dato ({d['que']}): {d['distintas']:,} de {d['entradas']:,} "
                          f"entradas distintas entre la copia tal cual y con el parche "
                          f"({'falla donde debe' if d['detectado'] else 'NO falla'}; {d['lectura']}).")
        if v['no_aplican']:
            lineas.append(f"- pistas que el optimizador no puede cumplir (error {latentes.NO_COMPILA}, no aplican): "
                          f"{', '.join(v['no_aplican'])}.")
    lineas += ['', 'Tiempos: ' + ' · '.join(f'{k} {v} s' for k, v in informe['segundos'].items()) + '.']
    lineas += [f'- ✘ {f}' for f in informe.get('faltas', [])]
    return '\n'.join(lineas) + '\n'


def faltas_de(informe: dict) -> list[str]:
    faltas = list(informe.get('faltas', []))
    faltas += [f'base: {f}' for f in informe.get('base', {}).get('verificacion', {}).get('faltas', [])]
    for objeto, m in informe.get('latentes', {}).items():
        o = next(x for x in OBJETOS if x.id == objeto)
        for grupo in (m['corridas'], m['con_parche']):
            for v, c in grupo.items():
                forzada = latentes.variante(o, v).forzada
                if c['no_compila'] and forzada and not c['guarda']:
                    continue                    # una pista que no se puede cumplir: se reporta «no aplica»
                if c['error'] or c['guarda']:
                    faltas.append(f"{objeto} · {v}: {c['guarda'] or c['error']}")
                if not c['plan'].get('visto'):
                    faltas.append(f'{objeto} · {v}: su plan no está en la caché (no se puede saber si cambió)')
        if m['tobe']['por_entrada']['distintas']:
            faltas.append(f"{objeto}: el TO-BE por entrada no coincide con el de todas las entradas "
                          f"({m['tobe']['por_entrada']['distintas']})")
        faltas += latentes.faltas_de(o, m['veredicto'])
        if m.get('control_de_dato') and not m['control_de_dato']['detectado']:
            faltas.append(f"{objeto}: el control del comparador por dato no falló donde tenía que fallar "
                          f"({m['control_de_dato']['distintas']} de {m['control_de_dato']['entradas']})")
        prep = [x for x in m['preparaciones'].values() if x['planes_que_quedan']]
        if prep:
            faltas.append(f'{objeto}: quedaron planes de la copia en la caché al prepararla: {prep}')
    a = informe.get('alcance')
    if a and not a['coincide']:
        faltas.append(f"los latentes medidos no son los del catálogo: {a}")
    copia = informe.get('copia', {})
    if copia.get('al_terminar') and not copia['al_terminar']['esquema_borrado']:
        faltas.append('la copia temporal no se borró')
    if copia.get('originales') and copia.get('al_terminar', {}).get('originales') != copia['originales']:
        faltas.append('los originales del respaldo cambiaron durante la corrida')
    t = informe.get('tobe_al_terminar')
    if t and not t['huella_igual']:
        faltas.append(f"la base del TO-BE no volvió a su huella: {t['diferencias'][:5]}")
    if 'latentes' not in informe and 'error' not in informe:
        faltas.append('la corrida no llegó a medir las latentes')
    return faltas


# ── el conductor ────────────────────────────────────────────────────────────────────────────────────────────────

def alcance(cat: dict) -> dict:
    """Confirmación contra el catálogo sellado (después de medir): los latentes del catálogo son los objetos medidos."""
    del_catalogo = sorted(o for id_ in trampas.LATENTES for o in cat[id_]['objetos'])
    medidos = sorted(o.id for o in OBJETOS)
    return {'catalogo': {id_: cat[id_]['objetos'] for id_ in trampas.LATENTES}, 'medidos': medidos,
            'coincide': del_catalogo == medidos}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.latentes_ci', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--base', type=Path, default=Path('corte/base'), help='carpeta con destino.dump y destino.json')
    parser.add_argument('--construir-base', action='store_true', help='sin volcado: cargar los 36 meses y cerrar')
    parser.add_argument('--fuente', default='', help='de dónde vino el volcado (para el resumen)')
    parser.add_argument('--contenedor', default='decant-pg-latentes')
    parser.add_argument('--destino-base', default='decant_corte_latentes')
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--manifiesto', type=Path, default=None)
    parser.add_argument('--resumen', type=Path, default=None)
    parser.add_argument('--margen-folios', type=int, default=10_000)
    parser.add_argument('--completo', action='store_true', help='todo el universo también en lo pesado (nocturna)')
    args = parser.parse_args(argv)
    t0 = time.monotonic()
    args.salida.mkdir(parents=True, exist_ok=True)
    informe: dict = {'version': 1, 'completo': args.completo, 'segundos': {}, 'faltas': []}
    s = informe['segundos']
    try:
        manifiesto = args.manifiesto or runbook._ultimo_manifiesto()
        if manifiesto is None:
            raise SystemExit('falta el manifiesto del respaldo: corre antes ./ciclo.sh')
        inventario = codigo.inventario()
        objetos, escritores = inventario['objetos'], inventario['escritores']
        cat = trampas.catalogo()
        t = time.monotonic()
        informe['origen'] = carga_ci.restaurar_corte(manifiesto)
        corte, _tope, _vivo = runbook_delta.contexto(manifiesto)
        s['respaldo'] = round(time.monotonic() - t, 1)
        t = time.monotonic()
        with runbook.conectar_origen() as ms_corte:
            p = runbook.leer_plan(ms_corte, corte)
            informe['base'] = delta_ci.preparar_base(args, ms_corte, p, corte)
        s['base'] = round(time.monotonic() - t, 1)
        if informe['base']['verificacion']['verde']:
            efectos = estado.efectos_declarados(objetos, escritores)
            with runbook.conectar_origen() as ms, runbook.conectar_destino(args.destino_base) as pg:
                huella_tobe = runbook.huella_destino(pg)
                informe['paralelismo'] = paralelismo(ms)
                t = time.monotonic()
                try:
                    informe['copia'] = estado_ci.preparar_copia(ms, objetos, escritores, efectos)
                    s['copia'] = round(time.monotonic() - t, 1)
                    t = time.monotonic()
                    informe['copia_latentes'] = copiar_latentes(ms)
                    s['copia_latentes'] = round(time.monotonic() - t, 1)
                    lotes = informe['copia_latentes']['_lotes']
                    informe['latentes'] = medir(ms, pg, objetos, lotes, args.completo, s)
                finally:
                    for h in planes_de_la_copia(ms):
                        ms.cursor().execute(latentes.SACAR_PLAN, (h,))
                    informe.setdefault('copia', {})['al_terminar'] = estado_ci.borrar_copia(ms)
                ahora = runbook.huella_destino(pg)
                informe['tobe_al_terminar'] = {'huella_igual': ahora == huella_tobe,
                                               'diferencias': base.delta.diferencias(huella_tobe, ahora)}
            informe['planes'] = guardar_planes(args.salida, informe['latentes'])
            informe['nombres'] = {o.id: trampas.nombrar(o.id, cat) for o in OBJETOS}
            informe['alcance'] = alcance(cat)
            informe['del_catalogo'] = {
                id_: {'objeto': o, 'catalogo': n, 'medido': informe['latentes'][o]['unidades'], 'que': que,
                      'coincide': informe['latentes'][o]['unidades'] == n}
                for id_, (o, n, que) in DEL_CATALOGO.items()}
    except (Negado, NoCuadra, NoSeCopia) as error:
        informe['faltas'].append(f'{type(error).__name__}: {error}'[:3000])
        informe['error'] = traceback.format_exc()
    except Exception as error:      # cualquier otra: el informe y el resumen salen igual, y el job en rojo
        informe['faltas'].append(f'{type(error).__name__}: {error}'[:3000])
        informe['error'] = traceback.format_exc()
    s['total'] = round(time.monotonic() - t0, 1)
    informe['faltas'] = faltas_de(informe)
    informe['verde'] = not informe['faltas']
    (args.salida / 'latentes.json').write_text(
        json.dumps(estado_ci._sin_internos(informe), ensure_ascii=False, indent=1, default=str) + '\n',
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
