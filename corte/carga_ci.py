"""La carga histórica por mes en el CI (S3 paso 3): el runbook de verdad, sobre el respaldo restaurado y un
PostgreSQL limpio, con sus controles negativos.

    python -m corte.carga_ci --meses pr     --salida corte/carga-ci   # PR: 2021-01, la grieta y 2023-12
    python -m corte.carga_ci --meses todos  --salida corte/carga-ci   # cada noche: los 36, acumulando, y el cierre
    python -m corte.carga_ci --meses todos  --salida corte/carga-ci --volcar corte/base --contenedor decant-pg-carga

Necesita el legado arriba después de `./ciclo.sh` (DECANT_SA_PASSWORD, DECANT_PUERTO) y PostgreSQL
(DECANT_PG_PASSWORD, DECANT_PG_PUERTO). Pasos:
1. Restaura el respaldo FECHADO (sha256 contra su manifiesto, VERIFYONLY) como `BFN_DIVISAS_CORTE` en el mismo
   servidor: ésa es la foto del corte. El corte de cada tabla es el del manifiesto y el medido en el paso 2.
2. Base `decant_corte`: por cada mes, ensayo → aplicar (huella del mes origen = destino) → reversa (huella previa)
   y, de noche, aplicar otra vez para avanzar; al final, el cierre (setval desde IDENT_CURRENT, folios con margen,
   llaves foráneas y totales globales).
3. Base `decant_corte_controles`: los controles negativos. Cada uno tiene que FALLAR donde se dice:
   - la grieta UTC: el cuadre del mes la ve; los totales globales del plan, no;
   - una reversa plantada que no restaura el setval: la huella la ve;
   - una escritura informativa del sistema: la reversa la sigue incluyendo; una reversa plantada que decide por el
     token de concurrencia la deja fuera y la huella la ve;
   - una fila con id ≤ corte: la guarda la niega y, sin la guarda, el índice único del ensayo choca y el corte se
     detiene;
   - `aplicar` con un automatismo encendido: se niega;
   - `reversa` después del punto de no retorno (aviso al exterior y acción de negocio): se niega.
4. Con `--volcar` (de noche, y sólo si los 36 meses cuadran y el cierre pasa): la base cerrada se vuelca con
   `pg_dump` (`corte/base.py`) para que el delta del mismo día la restaure (en el PR, desde la nocturna anterior).
Deja `carga.json` y, con `--resumen`, el resumen del job. Sale con 1 si un mes no cuadra o un control no falla.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from corte import base, carga, runbook
from corte.runbook import Negado, NoCuadra

CONTROLES_BASE = 'decant_corte_controles'
INTERRUPTOR_DEL_CONTROL = 'ConciliarAutomatico'


# La base del corte es una sola y fija (runbook.ORIGEN_BASE): la sentencia es literal.
BORRAR_CORTE = """IF DB_ID(N'BFN_DIVISAS_CORTE') IS NOT NULL
BEGIN
    ALTER DATABASE BFN_DIVISAS_CORTE SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE BFN_DIVISAS_CORTE;
END"""


def restaurar_corte(manifiesto: Path) -> dict:
    """El respaldo FECHADO como `BFN_DIVISAS_CORTE` en el SQL Server del legado: sha256 contra el manifiesto,
    VERIFYONLY y RESTORE (la misma restauración de la radiografía y de la paridad)."""
    from legado.conexion import contenedor, contrasena
    from paridad.formato import sha256
    from radiografia import sqlserver
    t0 = time.monotonic()
    datos = json.loads(manifiesto.read_text(encoding='utf-8'))
    archivo = next(a for a in datos['archivos'] if a['base'] == 'BFN_DIVISAS')
    ruta = manifiesto.parent / archivo['nombre']
    if sha256(ruta) != archivo['sha256']:
        raise SystemExit(f'{ruta.name}: el sha256 no coincide con el manifiesto; no se restaura')
    servidor = sqlserver.existente(contenedor(), int(os.environ.get('DECANT_PUERTO', '14330')), contrasena())
    with servidor.conectar() as conexion:
        conexion.cursor().execute(BORRAR_CORTE)
    disco = servidor.copiar(str(ruta))
    verificado = servidor.verificar(disco)
    servidor.restaurar(disco, runbook.ORIGEN_BASE)
    return {'manifiesto': manifiesto.name, 'archivo': archivo['nombre'], 'sha256': archivo['sha256'],
            'verificado': verificado, 'base': runbook.ORIGEN_BASE, 'segundos': round(time.monotonic() - t0, 1)}


def _sha(valor) -> str:
    return hashlib.sha256(json.dumps(valor, sort_keys=True, default=str).encode('utf-8')).hexdigest()


# ── los meses ───────────────────────────────────────────────────────────────────────────────────────────────────

def un_mes(pg, ms, p: dict, mes: str, corte: dict, acumular: bool, trabajo: Path) -> dict:
    t0 = time.monotonic()
    r: dict = {'mes': mes}
    try:
        ensayo = runbook.cargar_mes(pg, ms, p, mes, corte, confirmar=False)
        aplicado = runbook.cargar_mes(pg, ms, p, mes, corte, confirmar=True, trabajo=trabajo)
        previa = aplicado['previa']
        r['filas'] = aplicado['filas']
        r['rangos'] = {t: [v['desde'], v['hasta']] for t, v in aplicado['rangos'].items()}
        r['huellas'] = {t: {'origen': aplicado['huella_origen'][t]['huella'],
                            'destino': aplicado['huella_destino'][t]['huella']} for t in aplicado['huella_origen']}
        r['origen_igual_destino'] = all(h['origen'] == h['destino'] for h in r['huellas'].values())
        reversa = runbook.revertir(pg, mes)
        despues = reversa['ahora']
        # el conductor compara también los folios (la reversa compara tablas y secuencias; folio es una de las tablas)
        r['reversa'] = {'borradas': reversa['borradas'], 'huella_previa': _sha(_huella(previa)),
                        'huella_despues': _sha(_huella(despues)),
                        'igual': carga.diferencias_de_huella(previa, despues) == [] and previa['folios'] ==
                        despues['folios']}
        r['segundos'] = {'ensayo': _total(ensayo), 'aplicar': _total(aplicado), 'reversa': reversa['segundos']}
        if acumular:
            otra = runbook.cargar_mes(pg, ms, p, mes, corte, confirmar=True, trabajo=trabajo)
            r['reaplicado'] = all(otra['huella_origen'][t] == otra['huella_destino'][t] for t in otra['huella_origen'])
            r['segundos']['reaplicar'] = _total(otra)
        r['verde'] = r['origen_igual_destino'] and r['reversa']['igual'] and r.get('reaplicado', True)
    except (Negado, NoCuadra) as error:
        r.update(verde=False, error=f'{type(error).__name__}: {error}')
    r['segundos_total'] = round(time.monotonic() - t0, 1)
    return r


def _huella(h: dict) -> dict:
    return {'tablas': h['tablas'], 'secuencias': h['secuencias'], 'folios': h['folios']}


def _total(resultado: dict) -> float:
    return round(sum(resultado['segundos'].values()), 2)


# ── los controles negativos ─────────────────────────────────────────────────────────────────────────────────────

def _por_token(consulta, _tabla, _rango, txid):
    """Reversa PLANTADA: «ya lo trabajó el TO-BE» decidido por el token de concurrencia (xmin): sólo borra las filas
    que nadie tocó después de la carga. Una escritura informativa del sistema saca la fila de la reversa."""
    from psycopg import sql
    return sql.SQL('{} AND xmin::text::bigint = {}').format(consulta, sql.Literal(int(txid) % 2 ** 32))


def _negado(funcion, *args, **kwargs) -> tuple[bool, str]:
    try:
        funcion(*args, **kwargs)
    except (Negado, NoCuadra) as error:
        return True, f'{type(error).__name__}: {error}'
    return False, 'no falló'


def controles(ms, p: dict, corte: dict, base: str = CONTROLES_BASE) -> dict:
    import psycopg
    primero, segundo = carga.MESES[0], carga.MESES[1]
    r: dict = {}
    with runbook.conectar_destino(base, crear=True) as pg:
        runbook.preparar(pg, ms, recrear=True)
        vacio = runbook.huella_destino(pg)

        # 1. la grieta UTC (criterio 6)
        t0 = time.monotonic()
        grieta = runbook.leer_plan(ms, corte, grieta=carga.GRIETA)
        globales, globales_grieta = carga.totales_del_plan(p), carga.totales_del_plan(grieta)
        origen = {t: {'filas': d['origen']['filas'], 'monto': d['origen']['monto'], 'hasta': d['origen']['max_id'],
                      'cubre_sin_huecos': True} for t, d in p['tablas'].items()}
        mueve = {t: p['tablas'][t]['meses'][carga.GRIETA]['filas'] - grieta['tablas'][t]['meses'][carga.GRIETA]['filas']
                 for t in p['tablas']}            # las de la última noche que el plan con la grieta manda a noviembre
        # el ensayo pasa por encima de la falta del plan (sólo en el control) para que se vea el cuadre del mes
        visto, como = _negado(runbook.cargar_mes, pg, ms, grieta, carga.GRIETA, corte, confirmar=False,
                              sin_guarda=True)
        r['grieta_utc'] = {
            'mes': carga.GRIETA, 'ventana': {k: str(v) for k, v in carga.ventana_grieta(carga.GRIETA).items()},
            'filas_que_cambian_de_mes': mueve, 'cuadre_del_mes': como, 'el_plan': grieta['faltas'] or 'contiguo',
            'totales_globales_iguales': globales == globales_grieta == origen,
            'totales_globales': {'plan': globales, 'plan_con_grieta': globales_grieta, 'origen': origen},
            'detectado': visto and globales == globales_grieta == origen and any(mueve.values()),
            'regla': 'el fin de octubre calculado en UTC manda la última noche a noviembre: el cuadre mes a mes '
                     '(huella del mes por sello contra el rango del plan) falla y los totales globales cuadran; en '
                     'operacion, además, los rangos del plan se enciman',
            'segundos': round(time.monotonic() - t0, 1)}

        # 2. reversa plantada que NO restaura el setval
        runbook.cargar_mes(pg, ms, p, primero, corte, confirmar=False)
        runbook.cargar_mes(pg, ms, p, primero, corte, confirmar=True)
        visto, como = _negado(runbook.revertir, pg, primero, restaurar_secuencias=False)
        limpia = runbook.revertir(pg, primero)
        r['reversa_sin_setval'] = {
            'resultado': como, 'detectado': visto and 'secuencia' in como,
            'despues_la_reversa_buena': limpia['huella'],
            'regla': 'una reversa que borra las filas pero no regresa las secuencias deja otra huella: no confirma'}

        # 3. escritura informativa del sistema sobre una fila cargada
        runbook.cargar_mes(pg, ms, p, primero, corte, confirmar=True)
        fila = p['tablas']['orden_pago']['meses'][primero]['desde'] + 1
        pg.execute('UPDATE legado.orden_pago SET estatus = estatus WHERE id = %s', (fila,))   # re-guarda la fila
        sin_evento = runbook.no_retorno(pg) is None
        visto, como = _negado(runbook.revertir, pg, primero, excluir=_por_token)
        buena = runbook.revertir(pg, primero)
        incluida = pg.execute('SELECT count(*) FROM legado.orden_pago WHERE id = %s', (fila,)).fetchone()[0] == 0
        r['escritura_informativa'] = {
            'fila': f'legado.orden_pago #{fila}', 'reversa_por_token': como,
            'reversa_buena': {'borradas': buena['borradas'], 'la_incluye': incluida},
            'no_cruzo_el_punto_de_no_retorno': sin_evento,
            'detectado': visto and 'orden_pago' in como and incluida and sin_evento,
            'regla': 'lo trabajado lo dice la bitácora de ACCIONES de negocio: una escritura informativa cambia el '
                     'token y no saca la fila de la reversa; decidirlo por el token la deja fuera y la huella lo ve'}

        # 4. una fila con id ≤ corte
        runbook.cargar_mes(pg, ms, p, primero, corte, confirmar=True)
        tope = p['tablas']['operacion']['meses'][primero]['hasta']
        plantada = {'operacion': runbook.filas_por_rango(ms, 'operacion', tope - 1, tope)}
        antes = runbook.huella_destino(pg)
        por_guarda, como_guarda = _negado(runbook.cargar_mes, pg, ms, p, segundo, corte, confirmar=False,
                                          plantar=plantada)
        try:
            runbook.cargar_mes(pg, ms, p, segundo, corte, confirmar=False, plantar=plantada, sin_guarda=True)
            por_indice, como_indice = False, 'no chocó'
        except psycopg.errors.UniqueViolation as error:
            por_indice, como_indice = True, f'UniqueViolation: {str(error).splitlines()[0]}'
        detenido, como_detenido = _negado(runbook.cargar_mes, pg, ms, p, segundo, corte, confirmar=True)
        igual = runbook.huella_destino(pg) == antes
        r['fila_con_id_hasta_el_corte'] = {
            'fila': f'legado.operacion #{tope} (ya cargada en {primero}) dentro del lote de {segundo}',
            'guarda': como_guarda, 'indice_unico_del_ensayo': como_indice, 'aplicar_despues': como_detenido,
            'destino_sin_cambios': igual,
            'detectado': por_guarda and por_indice and detenido and igual,
            'regla': 'sólo ids > corte: la guarda la niega; sin la guarda, el índice único choca en el ensayo y, sin '
                     'ensayo verde, aplicar se niega'}

        # 5. aplicar con un automatismo del TO-BE encendido
        runbook.cargar_mes(pg, ms, p, segundo, corte, confirmar=False)
        pg.execute('UPDATE corte.interruptor SET encendido = true, cambiado_en = clock_timestamp() WHERE nombre = %s',
                   (INTERRUPTOR_DEL_CONTROL,))
        antes = runbook.huella_destino(pg)
        visto, como = _negado(runbook.cargar_mes, pg, ms, p, segundo, corte, confirmar=True)
        igual = runbook.huella_destino(pg) == antes
        pg.execute('UPDATE corte.interruptor SET encendido = false, cambiado_en = clock_timestamp() WHERE nombre = %s',
                   (INTERRUPTOR_DEL_CONTROL,))
        ya_apagado = runbook.cargar_mes(pg, ms, p, segundo, corte, confirmar=True)
        r['automatismo_encendido'] = {
            'interruptor': INTERRUPTOR_DEL_CONTROL, 'aplicar': como, 'destino_sin_cambios': igual,
            'apagado_aplica': ya_apagado['verbo'] == 'aplicar',
            'detectado': visto and INTERRUPTOR_DEL_CONTROL in como and igual,
            'regla': 'aplicar se niega si hay automatismos del TO-BE encendidos'}

        # 6. reversa después del punto de no retorno: primero un aviso al exterior (en una transacción que se
        #    revierte), luego una acción de negocio sobre una fila cargada (confirmada)
        antes = runbook.huella_destino(pg)
        with pg.transaction(force_rollback=True):
            pg.execute('INSERT INTO corte.aviso_exterior (destino, referencia) VALUES (%s, %s)',
                       ('corresponsal', 'confirmación de prueba del control'))
            punto_aviso = runbook.no_retorno(pg)
            por_aviso, como_aviso = _negado(runbook.revertir, pg, segundo)
        sin_punto = runbook.no_retorno(pg) is None
        orden = p['tablas']['orden_pago']['meses'][segundo]['desde'] + 1
        pg.execute('INSERT INTO corte.accion_negocio (tabla, fila, accion) VALUES (%s, %s, %s)',
                   ('legado.orden_pago', orden, 'cancelar'))
        punto = runbook.no_retorno(pg)
        visto, como = _negado(runbook.revertir, pg, segundo)
        igual = runbook.huella_destino(pg) == antes
        r['reversa_tras_no_retorno'] = {
            'por_aviso_al_exterior': {'punto': punto_aviso, 'reversa': como_aviso},
            'por_accion_de_negocio': {'punto': punto, 'reversa': como}, 'destino_sin_cambios': igual,
            'detectado': por_aviso and visto and sin_punto and punto is not None and igual,
            'regla': 'el punto de no retorno lo registra el sistema con la primera acción de negocio o el primer aviso '
                     'al exterior; desde ahí la reversa se niega'}
        r['destino_vacio_al_empezar'] = _sha(_huella(vacio))
    return r


# ── el resumen ──────────────────────────────────────────────────────────────────────────────────────────────────

def resumen(informe: dict) -> str:
    titulo = f"## Carga histórica por mes ({informe['modo']}: {informe['verdes']} de {len(informe['meses'])} meses)"
    origen = (f"Origen: `{informe['origen']['base']}` restaurado de `{informe['origen']['archivo']}` "
              f"(sha256 `{informe['origen']['sha256'][:16]}…`, {informe['origen']['verificado']}). "
              f"Plan `{informe['plan']['sha'][:12]}`: {len(informe['plan']['meses'])} meses en rangos contiguos, "
              f"{len(informe['plan']['faltas'])} faltas. Índices únicos iguales al origen: "
              f"{informe['preparar']['indices_unicos_iguales']}.")
    columnas = ('mes', 'operacion', 'orden_pago', 'partida_solicitada', 'partida_liquidada', 'bitacora',
                'origen = destino', 'reversa = previa', 's')
    encabezado = '| ' + ' | '.join(columnas) + ' |'
    lineas = [titulo, '', origen, '', encabezado, '|---|---|---|---|---|---|---|---|---|']
    for m in informe['meses']:
        if 'filas' not in m:
            lineas.append(f"| {m['mes']} | ✘ {m.get('error', '')[:200]} | | | | | | | {m['segundos_total']} |")
            continue
        f = m['filas']
        lineas.append(f"| {m['mes']} | {f['operacion']:,} | {f['orden_pago']:,} | {f['partida_solicitada']:,} | "
                      f"{f['partida_liquidada']:,} | {f['bitacora']:,} | {'sí' if m['origen_igual_destino'] else 'NO'} "
                      f"| {'sí' if m['reversa']['igual'] else 'NO'} | {m['segundos_total']} |")
    if informe.get('cierre'):
        c = informe['cierre']
        lineas += ['', '**Cierre:** ' + (c.get('error') or ' · '.join(
            f"{t}: {v['destino']['filas']:,} filas = origen, setval {v['origen']['ident_current']:,} (IDENT_CURRENT)"
            for t, v in c['totales'].items()) + ' · folios: ' + ', '.join(
            f"{s} {v['origen']:,} → {v['destino']:,} (el vivo usa hasta {v['legado_vivo_ya_usa_hasta']})"
            for s, v in c['consumibles'].items()))]
    lineas += ['', '| control negativo | detectado | cómo |', '|---|---|---|']
    for nombre, c in informe['controles'].items():
        if isinstance(c, dict) and 'detectado' in c:
            lineas.append(f"| {nombre} | {'sí' if c['detectado'] else 'NO'} | {_como(c)} |")
    lineas += ['', f"Tiempos: total {informe['segundos']['total']} s · restaurar {informe['origen']['segundos']} s · "
                   f"plan {informe['segundos']['plan']} s · meses {informe['segundos']['meses']} s · controles "
                   f"{informe['segundos']['controles']} s."]
    return '\n'.join(lineas) + '\n'


def _como(c: dict) -> str:
    """Lo que hizo fallar a un control, en un renglón."""
    if 'cuadre_del_mes' in c:
        plan = c['el_plan'] if isinstance(c['el_plan'], str) else '; '.join(c['el_plan'])
        return (f"cuadre del mes: {c['cuadre_del_mes'][:220]} · plan: {plan[:160]} · totales globales iguales: "
                f"{'sí' if c['totales_globales_iguales'] else 'NO'}")
    if 'indice_unico_del_ensayo' in c:
        return (f"{c['guarda'][:140]} · sin la guarda: {c['indice_unico_del_ensayo'][:120]} · "
                f"{c['aplicar_despues'][:120]}")
    if 'por_aviso_al_exterior' in c:
        return (f"por aviso: {c['por_aviso_al_exterior']['reversa'][:150]} · por acción: "
                f"{c['por_accion_de_negocio']['reversa'][:150]}")
    if 'reversa_por_token' in c:
        return f"{c['reversa_por_token'][:200]} · la reversa buena la incluye: {c['reversa_buena']['la_incluye']}"
    return (c.get('resultado') or c.get('aplicar') or '')[:300]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.carga_ci', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--meses', default='pr', help="'pr', 'todos' o una lista separada por comas")
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--manifiesto', type=Path, default=None)
    parser.add_argument('--resumen', type=Path, default=None)
    parser.add_argument('--margen-folios', type=int, default=10_000)
    parser.add_argument('--volcar', type=Path, default=None,
                        help='carpeta donde dejar el volcado de la base cerrada (sólo con los 36 meses y el cierre)')
    parser.add_argument('--contenedor', default='decant-pg-carga', help='el contenedor de PostgreSQL (pg_dump)')
    args = parser.parse_args(argv)
    t0 = time.monotonic()
    meses = {'pr': carga.MESES_PR, 'todos': carga.MESES}.get(args.meses) or tuple(args.meses.split(','))
    acumular = args.meses == 'todos'
    manifiesto = args.manifiesto or runbook._ultimo_manifiesto()
    if manifiesto is None:
        raise SystemExit('falta el manifiesto del respaldo: corre antes ./ciclo.sh')
    args.salida.mkdir(parents=True, exist_ok=True)
    informe: dict = {'version': 1, 'modo': 'cada noche, acumulando' if acumular else 'PR', 'segundos': {}}
    informe['origen'] = restaurar_corte(manifiesto)
    corte = runbook.cortes(manifiesto)
    informe['corte'] = corte
    with runbook.conectar_origen() as ms:
        t1 = time.monotonic()
        p = runbook.leer_plan(ms, corte)
        informe['segundos']['plan'] = round(time.monotonic() - t1, 1)
        informe['plan'] = {'sha': p['sha'], 'meses': p['meses'], 'faltas': p['faltas'],
                           'tablas': {t: {'corte': d['corte'], 'origen': d['origen']} for t, d in p['tablas'].items()},
                           'por_mes': {m: {t: d['meses'][m] for t, d in p['tablas'].items()} for m in p['meses']}}
        t2 = time.monotonic()
        with runbook.conectar_destino(crear=True) as pg:
            prep = runbook.preparar(pg, ms, recrear=True)
            informe['preparar'] = prep
            informe['meses'] = [un_mes(pg, ms, p, m, corte, acumular, args.salida / 'reversas') for m in meses]
            if acumular and meses == carga.MESES:
                try:
                    informe['cierre'] = runbook.cerrar(pg, ms, p, corte, args.margen_folios)
                except (Negado, NoCuadra) as error:
                    informe['cierre'] = {'error': f'{type(error).__name__}: {error}'}
                cuadran = all(m.get('verde') for m in informe['meses']) and not p['faltas']
                if args.volcar and cuadran and 'error' not in informe['cierre']:
                    informe['base'] = {k: v for k, v in base.volcar(pg, args.contenedor, runbook.DESTINO_BASE,
                                                                    args.volcar, informe).items() if k != 'huella'}
        informe['segundos']['meses'] = round(time.monotonic() - t2, 1)
        t3 = time.monotonic()
        informe['controles'] = controles(ms, p, corte)
        informe['segundos']['controles'] = round(time.monotonic() - t3, 1)
    informe['verdes'] = sum(1 for m in informe['meses'] if m.get('verde'))
    informe['segundos']['total'] = round(time.monotonic() - t0, 1)
    faltas = [f"{m['mes']}: {m.get('error', 'no cuadra')}" for m in informe['meses'] if not m.get('verde')]
    faltas += [f'plan: {f}' for f in p['faltas']]
    faltas += [f'control {n} no detectado' for n, c in informe['controles'].items()
               if isinstance(c, dict) and 'detectado' in c and not c['detectado']]
    if informe.get('cierre', {}).get('error'):
        faltas.append(f"cierre: {informe['cierre']['error']}")
    informe['faltas'] = faltas
    informe['verde'] = not faltas
    (args.salida / 'carga.json').write_text(json.dumps(informe, ensure_ascii=False, indent=1, default=str) + '\n',
                                            encoding='utf-8')
    texto = resumen(informe)
    print(texto)
    for f in faltas:
        print(f'✘ {f}')
    if args.resumen:
        with args.resumen.open('a', encoding='utf-8') as salida:
            salida.write(texto)
    return 0 if informe['verde'] else 1


if __name__ == '__main__':
    sys.exit(main())
