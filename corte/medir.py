"""Mide, sobre el legado VIVO que deja `./ciclo.sh`, el corte por dos caminos y las cifras de control por documento
(S3, criterios 3, 7 y 8; ADR 0013 y 0016). Sólo lee.

    python -m corte.medir --salida corte/medido-ci

Necesita el legado arriba (DECANT_SA_PASSWORD, DECANT_PUERTO), el registro del vivo (`legado/datos/vivo_*.json`,
con las fotos del respaldo y del congelamiento), el guion del delta y el manifiesto del respaldo. Deja:
- `corte.json`: por cada tabla del inventario, los ids mayores al corte por identidad y por cada camino de sellos,
  su diferencia de conjuntos, los huecos de identidad y el control negativo por `fecha_operacion`;
- `cifras-de-control.json`: totales de las tablas y de los consumibles, cifras por documento (tipo + estado + mes,
  cargado y lo que no viaja por motivo), la conciliación del delta por llave de negocio y los controles negativos;
- `huellas-por-documento.csv`: la huella sha256 de cada documento, con su llave, estado, mes y destino.

Las dos últimas no dependen del reloj de la corrida: si el legado y el código no cambian, salen idénticas byte a byte
(su sha se versiona en `corte/cifras/huella.json` y el job `corte` lo verifica).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from corte import caminos, cifras, codigo
from corte.cifras import Contexto, Operacion, Partida, Registro, Vigencia

APLICACION = 'decant-corte'
DATOS = codigo.RAIZ / 'legado' / 'datos'
RESPALDOS = codigo.RAIZ / 'respaldos'
CORTE, CIFRAS, HUELLAS = 'corte.json', 'cifras-de-control.json', 'huellas-por-documento.csv'

# Identificadores: el nombre de la tabla viaja como PARÁMETRO y se cita con QUOTENAME en el servidor; la columna de
# identidad sale del catálogo, no del cliente.
Q_IDS = """DECLARE @t nvarchar(300) = QUOTENAME(PARSENAME(%s, 2)) + N'.' + QUOTENAME(PARSENAME(%s, 1));
DECLARE @c sysname = (SELECT name FROM sys.identity_columns WHERE object_id = OBJECT_ID(@t));
IF @c IS NULL THROW 50000, N'la tabla no tiene identidad', 1;
DECLARE @sql nvarchar(max) = N'SELECT ' + QUOTENAME(@c) + N' FROM ' + @t + N' WHERE ' + QUOTENAME(@c) + N' > @corte';
EXEC sp_executesql @sql, N'@corte bigint', @corte = %s;"""
Q_TOTALES = """DECLARE @t nvarchar(300) = QUOTENAME(PARSENAME(%s, 2)) + N'.' + QUOTENAME(PARSENAME(%s, 1));
DECLARE @c sysname = (SELECT name FROM sys.identity_columns WHERE object_id = OBJECT_ID(@t));
DECLARE @sql nvarchar(max) = N'SELECT COUNT_BIG(*), '
    + CASE WHEN @c IS NULL THEN N'NULL' ELSE N'MAX(' + QUOTENAME(@c) + N')' END
    + N', IDENT_CURRENT(@nombre) FROM ' + @t;
EXEC sp_executesql @sql, N'@nombre nvarchar(300)', @nombre = @t;"""
Q_OPERACIONES = """SELECT id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda,
       monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus
FROM dbo.operacion ORDER BY id"""
Q_ORDENES = """SELECT id, operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio, fecha_valor,
       bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, gastos, codigo_proposito,
       estatus, horas_liquidacion
FROM dbo.orden_pago ORDER BY id"""
Q_PARTIDAS_CLIENTE = """SELECT id, orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia
FROM dbo.partida_liquidada ORDER BY id"""
Q_PARTIDAS_CORRESPONSAL = """SELECT id, orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia
FROM dbo.partida_solicitada ORDER BY id"""
Q_CAMBIOS = """SELECT id, llave, estatus_anterior, estatus_nuevo FROM dbo.bitacora
WHERE tabla = N'orden_pago' AND accion = 'U' AND id > %s"""
Q_MONEDAS = 'SELECT codigo, activa FROM dbo.moneda ORDER BY codigo'
Q_FOLIOS = 'SELECT serie, siguiente FROM dbo.folio ORDER BY serie'
# El origen por mes contado por otro lado (SQL, no la clasificación de Python): documentos por mes de negocio.
Q_ORIGEN_OPERACIONES = """SELECT CONVERT(char(7), fecha_operacion, 126), COUNT_BIG(*) FROM dbo.operacion
GROUP BY CONVERT(char(7), fecha_operacion, 126)"""
Q_ORIGEN_ORDENES = """SELECT CONVERT(char(7), d.primero, 126), COUNT_BIG(*)
FROM (SELECT o.uetr, p.sucursal, MIN(o.fecha_registro) AS primero
      FROM dbo.orden_pago o LEFT JOIN dbo.operacion p ON p.id = o.operacion_id
      GROUP BY o.uetr, p.sucursal) d
GROUP BY CONVERT(char(7), d.primero, 126)"""


def _ultimo(directorio: Path, patron: str) -> Path:
    candidatos = sorted(directorio.glob(patron))
    if not candidatos:
        raise SystemExit(f'falta {directorio}/{patron}: corre antes ./ciclo.sh')
    return candidatos[-1]


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


def conectar():
    import pymssql

    from legado.conexion import BASE, contrasena
    return pymssql.connect(
        server=os.environ.get('DECANT_SQL_HOST', '127.0.0.1'), port=int(os.environ.get('DECANT_PUERTO', '14330')),
        user='sa', password=contrasena(), database=BASE, autocommit=True, appname=APLICACION, tds_version='7.4',
        charset='UTF-8', login_timeout=15, timeout=900)


def _sin_esquema(tabla: str) -> str:
    return tabla.split('.', 1)[1] if '.' in tabla else tabla


# ── criterio 3: el corte por dos caminos ────────────────────────────────────────────────────────────────────────

def medir_corte(cursor, tablas: dict, vivo: dict, delta: dict, manifiesto: dict) -> dict:
    """Por cada tabla del inventario: la identidad, cada camino por sellos y su diferencia de conjuntos."""
    cobertura = caminos.cobertura(tablas)
    resultado: dict = {'cobertura': cobertura, 'tablas': {}}
    identidades: dict[str, caminos.Clases] = {}
    for tabla in sorted(tablas):
        nombre = _sin_esquema(tabla)
        cursor.execute(Q_TOTALES, (tabla, tabla))
        filas, maximo, actual = cursor.fetchone()
        t: dict = {'identidad': bool(tablas[tabla].get('identidad')), 'filas_ahora': int(filas),
                   'max_id_ahora': None if maximo is None else int(maximo),
                   'ident_current': None if actual is None else int(actual), 'fotos_inconsistentes': []}
        foto_r, foto_c = vivo['al_respaldo'].get(nombre), vivo['al_congelamiento'].get(nombre)
        en_manifiesto = manifiesto.get('tablas', {}).get(tabla)
        if foto_r is None or foto_c is None:
            t['fotos_inconsistentes'].append('las fotos del legado vivo no la traen')
            resultado['tablas'][tabla] = t
            continue
        t['fotos'] = {'respaldo': foto_r, 'congelamiento': foto_c, 'manifiesto_del_respaldo': en_manifiesto}
        if en_manifiesto is None or en_manifiesto != foto_r:
            t['fotos_inconsistentes'].append(f'la foto del vivo al respaldo {foto_r} no es la del manifiesto '
                                             f'{en_manifiesto}: algo escribió entre el respaldo y el delta')
        if not t['identidad']:
            t['nota'] = 'sin identidad (catálogo o consumible): no tiene corte por id; se compara completo'
            resultado['tablas'][tabla] = t
            continue
        corte_id, congelamiento_id = foto_r['max_id'] or 0, foto_c['max_id'] or 0
        cursor.execute(Q_IDS, (tabla, tabla, corte_id))
        ids = [int(i) for (i,) in cursor.fetchall()]
        identidad = caminos.por_identidad(ids, corte_id, congelamiento_id)
        identidades[tabla] = identidad
        t['por_identidad'] = {'corte': corte_id, 'congelamiento': congelamiento_id,
                              'delta': len(identidad.delta), 'posterior': len(identidad.posterior)}
        # Totales: lo contado en cada foto + lo que el camino por identidad ve entre ellas = lo de ahora.
        if foto_r['filas'] + len(identidad.delta) != foto_c['filas']:
            t['fotos_inconsistentes'].append(f"respaldo {foto_r['filas']} + delta {len(identidad.delta)} ≠ "
                                             f"congelamiento {foto_c['filas']}")
        if foto_c['filas'] + len(identidad.posterior) != t['filas_ahora']:
            t['fotos_inconsistentes'].append(f"congelamiento {foto_c['filas']} + posterior "
                                             f"{len(identidad.posterior)} ≠ ahora {t['filas_ahora']}")
        hasta = max(t['max_id_ahora'] or 0, corte_id)
        vacios = caminos.huecos(ids, corte_id, hasta)
        t['huecos'] = {'cuantos': len(vacios), 'muestra': vacios[:caminos.MUESTRA],
                       'cuenta_ingenua': hasta - corte_id, 'filas_mayores_al_corte': len(ids),
                       'nota': 'MAX(id) - corte cuenta también los huecos: por eso se comparan conjuntos'}
        t['caminos'] = []
        for camino in (c for c in caminos.CAMINOS if c.tabla == tabla):
            limite = caminos.limites(camino.reloj, vivo, delta)
            cursor.execute(camino.consulta, (limite['parametro'],))
            sellados = caminos.por_sello(((i, caminos.sello(camino.reloj, s)) for i, s in cursor.fetchall()),
                                         limite['desde'], limite['hasta'])
            t['caminos'].append({
                'nombre': camino.nombre, 'reloj': camino.reloj, 'que_sella': camino.que_sella,
                'control_negativo': camino.control_negativo,
                'limites': {'desde': str(limite['desde']), 'hasta': str(limite['hasta']), 'fuente': limite['fuente']},
                'delta': len(sellados.delta), 'posterior': len(sellados.posterior),
                'comparacion': caminos.comparar(identidad, sellados),
                '_conjuntos': sellados})
        resultado['tablas'][tabla] = t
    resultado['control_negativo'] = _control_fecha_operacion(resultado, identidades, vivo)
    for t in resultado['tablas'].values():
        for c in t.get('caminos', []):
            c.pop('_conjuntos')
    resultado['faltas'] = caminos.veredicto(resultado)
    resultado['coincide'] = not resultado['faltas']
    return resultado


def _control_fecha_operacion(resultado: dict, identidades: dict, vivo: dict) -> dict | None:
    """El camino por fecha de negocio PIERDE las altas fechadas hacia atrás: debe fallar nombrándolas todas."""
    tabla = resultado['tablas'].get('dbo.operacion', {})
    negativo = next((c for c in tabla.get('caminos', []) if c['control_negativo']), None)
    if negativo is None or 'dbo.operacion' not in identidades:
        return None
    perdidos = identidades['dbo.operacion'].mayores_al_corte() - negativo['_conjuntos'].mayores_al_corte()
    atras = vivo['choques']['altas_fechadas_hacia_atras']['filas']
    esperadas = {f['id']: f"{f['folio']} · sucursal {f['sucursal']} · fecha {f['fecha_operacion']}" for f in atras}
    nombradas = sorted(set(esperadas) & perdidos)
    return {'camino': negativo['nombre'], 'esperadas': len(esperadas), 'nombradas': len(nombradas),
            'altas_fechadas_hacia_atras': caminos.nombres(nombradas, esperadas),
            'perdidos_por_el_camino': len(perdidos), 'muestra_perdidos': sorted(perdidos)[:caminos.MUESTRA],
            'detectado': bool(esperadas) and len(nombradas) == len(esperadas) and not negativo['comparacion'][
                'coincide'],
            'regla': 'el camino por fecha_operacion falla y nombra las altas que la sucursal reenvió fechadas hacia '
                     'atrás (oráculo: choques.altas_fechadas_hacia_atras del registro del vivo)'}


# ── criterios 7 y 8: las cifras de control por documento ────────────────────────────────────────────────────────

def leer_documentos(cursor, vivo: dict) -> dict:
    """Lee el legado y arma los documentos al congelamiento, más lo que necesitan la conciliación y los controles."""
    congelamiento = {f'dbo.{t}': (f.get('max_id') or 0) for t, f in vivo['al_congelamiento'].items()
                     if isinstance(f, dict) and 'max_id' in f}
    corte = {f'dbo.{t}': (f.get('max_id') or 0) for t, f in vivo['al_respaldo'].items()
             if isinstance(f, dict) and 'max_id' in f}
    cursor.execute(Q_MONEDAS)
    catalogo = [(c.strip(), bool(a)) for c, a in cursor.fetchall()]
    monedas = frozenset(c for c, _ in catalogo)

    documentos: list[cifras.Documento] = []
    operaciones: dict[int, tuple[str, str]] = {}
    cursor.execute(Q_OPERACIONES)
    for fila in cursor:
        op = Operacion(*fila)
        operaciones[op.id] = (op.folio, op.sucursal.rstrip(' '))
        documentos.append(cifras.documento_de_operacion(op, congelamiento['dbo.operacion'], monedas))

    cursor.execute(Q_ORDENES)
    actuales = [Registro(*fila) for fila in cursor]
    cursor.execute(Q_CAMBIOS, (corte['dbo.bitacora'],))
    cambios = [(int(i), int(llave), a, n) for i, llave, a, n in cursor.fetchall()]
    estatus = {r.id: r.estatus for r in actuales}
    al_respaldo = cifras.estatus_en(estatus, cambios)
    al_congelamiento = cifras.estatus_en(estatus, [c for c in cambios if c[0] > congelamiento['dbo.bitacora']])
    tope = congelamiento['dbo.orden_pago']
    registros = [r._replace(estatus=al_congelamiento[r.id]) if r.id <= tope else r for r in actuales]
    vigentes = {r.id for r in registros if r.estatus != cifras.REEMPLAZADA}

    ctx = Contexto(operaciones, monedas, congelamiento)
    cursor.execute(Q_PARTIDAS_CLIENTE)
    for fila in cursor:
        p = Partida(*fila)
        if p.orden_id in vigentes:
            ctx.partidas_cliente.setdefault(p.orden_id, []).append(p)
    cursor.execute(Q_PARTIDAS_CORRESPONSAL)
    for fila in cursor:
        p = Partida(*fila)
        ctx.partidas_corresponsal.setdefault(p.orden_id, []).append(p)

    por_llave: dict[tuple[str, str], list[Registro]] = defaultdict(list)
    for r in registros:
        por_llave[cifras.llave_de_orden(r, ctx)].append(r)
    documentos += [cifras.documento_de_orden(regs, ctx) for _llave, regs in sorted(por_llave.items())]

    corte_op = corte['dbo.orden_pago']
    conciliacion = {
        'al_corte': [Vigencia(r.id, cifras.llave_de_orden(r, ctx), al_respaldo[r.id])
                     for r in actuales if r.id <= corte_op],
        'delta': [Vigencia(r.id, cifras.llave_de_orden(r, ctx), al_congelamiento[r.id])
                  for r in actuales if corte_op < r.id <= tope],
    }
    origen = {}
    for tipo, consulta in (('operacion', Q_ORIGEN_OPERACIONES), ('orden', Q_ORIGEN_ORDENES)):
        cursor.execute(consulta)
        origen[tipo] = {m: int(n) for m, n in sorted(cursor.fetchall())}
    cursor.execute(Q_FOLIOS)
    folios = {s.strip(): int(n) for s, n in cursor.fetchall()}
    return {'documentos': documentos, 'por_llave': por_llave, 'ctx': ctx, 'conciliacion': conciliacion,
            'origen_sql': origen, 'catalogo': catalogo, 'folios': folios, 'corte': corte,
            'congelamiento': congelamiento}


def origen_por_mes(documentos: list[cifras.Documento]) -> dict[str, dict[str, int]]:
    resultado: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in documentos:
        resultado[d.tipo][d.mes] += 1
    return {t: dict(sorted(m.items())) for t, m in sorted(resultado.items())}


def elegir(leido: dict) -> tuple[tuple[str, str], list[Registro]] | None:
    """El documento de los controles: el primer pendiente re-registrado el día del corte (su registro viejo es del
    corte y el nuevo del delta) o, si no hubiera, la primera orden cargada."""
    corte_op, tope = leido['corte']['dbo.orden_pago'], leido['congelamiento']['dbo.orden_pago']
    candidatos = sorted(k for k, regs in leido['por_llave'].items()
                        if any(r.id <= corte_op for r in regs) and any(corte_op < r.id <= tope for r in regs))
    if not candidatos:
        cargadas = {d.llave[1:] for d in leido['documentos'] if d.tipo == 'orden' and d.destino == cifras.CARGADO}
        candidatos = sorted(cargadas)
    return (candidatos[0], leido['por_llave'][candidatos[0]]) if candidatos else None


def controles(leido: dict, base: dict) -> dict:
    """Los controles negativos sobre los documentos REALES: cada uno debe detectarse donde se dice."""
    documentos, ctx = leido['documentos'], leido['ctx']
    elegido = elegir(leido)
    resultado: dict = {}
    if elegido is not None:
        llave, registros = elegido
        original = cifras.documento_de_orden(registros, ctx)
        alterado = cifras.documento_de_orden(cifras.alterar_un_centavo(registros), ctx)
        otros = cifras.sustituir(documentos, alterado)
        dif = cifras.diferencias(base, cifras.agregar(otros))
        por_doc = cifras.diferencias_por_documento(documentos, otros)
        grupo = ['orden', original.estado, original.mes]
        resultado['un_centavo'] = {
            'documento': '/'.join(llave), 'grupo': grupo,
            'huella_antes': original.huella, 'huella_despues': alterado.huella,
            'documentos_distintos': por_doc['distintos'], 'grupos_distintos': [
                [g['tipo'], g['estado'], g['mes']] for g in dif['por_grupo']],
            'globales_distintos': {g['tipo']: g['distinto'] for g in dif['globales']},
            'detectado': (por_doc['distintos'] == 1 and por_doc['muestra_distintos'] == [list(original.llave)]
                          and [[g['tipo'], g['estado'], g['mes']] for g in dif['por_grupo']] == [grupo]),
            'regla': 'un centavo en el monto de UN documento cambia su huella y la de su mes (tipo + estado + mes)'}
        nuevo_id = max(r.id for regs in leido['por_llave'].values() for r in regs) + 1
        # el registro plantado entra en la foto del congelamiento: si no, sería posterior y no duplicaría nada
        en_foto = Contexto(ctx.operaciones, ctx.monedas, {**ctx.congelamiento, 'dbo.orden_pago': nuevo_id},
                           ctx.partidas_cliente, ctx.partidas_corresponsal)
        duplicado = cifras.documento_de_orden(cifras.duplicar_vigente(registros, nuevo_id), en_foto)
        nombrados = cifras.duplicados_por_documento(cifras.sustituir(documentos, duplicado))
        delta_doble = [*leido['conciliacion']['delta'],
                       *[Vigencia(nuevo_id, llave, r.estatus) for r in registros[-1:]]]
        por_llave = cifras.conciliar(leido['conciliacion']['al_corte'], delta_doble, 'llave')
        resultado['duplicado'] = {
            'documento': '/'.join(llave), 'id_agregado': nuevo_id, 'destino': duplicado.destino,
            'duplicados_por_documento': nombrados, 'conciliacion_por_llave_duplicados': por_llave['llaves_duplicadas'],
            'detectado': nombrados == ['/'.join(('orden', *llave))] and duplicado.destino == 'duplicado'
            and por_llave['llaves_duplicadas'] == ['/'.join(llave)],
            'regla': 'un segundo registro vigente del MISMO documento (otro id, la misma llave) sale como duplicado '
                     'y hace fallar «duplicados por documento = 0»'}
    utc = cifras.agregar(documentos, utc=True)
    dif = cifras.diferencias(base, utc)
    mueven = [d for d in documentos if d.mes != d.mes_utc]
    meses: dict[str, int] = defaultdict(int)
    for d in mueven:
        meses[f'{d.tipo} {d.mes}→{d.mes_utc}'] += 1
    resultado['grieta_utc'] = {
        'documentos_que_cambian_de_mes': len(mueven), 'por_mes': dict(sorted(meses.items())),
        'globales_distintos': len(dif['globales']), 'grupos_distintos': len(dif['por_grupo']),
        'muestra_grupos': [[g['tipo'], g['estado'], g['mes']] for g in dif['por_grupo'][:caminos.MUESTRA]],
        'detectado': bool(mueven) and not dif['globales'] and bool(dif['por_grupo']),
        'regla': 'el mes calculado en UTC mueve lo de la noche del último día al mes siguiente: los totales '
                 'globales cuadran y el mes no'}
    return resultado


def escribir_huellas(documentos: list[cifras.Documento], ruta: Path) -> str:
    """Escribe el CSV de huellas por documento y devuelve su sha256 (el del archivo tal cual queda)."""
    h = hashlib.sha256()
    with ruta.open('w', encoding='utf-8', newline='') as archivo:
        for renglon in cifras.renglones_csv(documentos):
            archivo.write(renglon)
            h.update(renglon.encode('utf-8'))
    return h.hexdigest()


def re_registros_del_dia(delta: dict) -> dict:
    """El oráculo de la conciliación, del GUION del delta (no de la base): los re-registros del día y, de ésos, los
    de documentos que ya estaban en la foto del corte. Un documento que la interfaz registró después del respaldo y
    re-registró a las 07:00 del mismo día vive entero en el delta: no tiene registro viejo en el corte."""
    ordenes = [p for p in delta['pasos'] if p['fase'] == 'delta' and p['accion'] == 'orden']
    nuevos = {p['args']['uetr'] for p in ordenes if not p['args'].get('reregistro')}
    rereg = [p['args']['uetr'] for p in ordenes if p['args'].get('reregistro')]
    del_corte = sorted({u for u in rereg if u not in nuevos})
    return {'llamadas': len(rereg), 'de_documentos_del_corte': len(del_corte),
            'de_documentos_nuevos_del_dia': len({u for u in rereg if u in nuevos}),
            'regla': 'del guion del delta: re-registros (misma uetr, otra fila) del día del corte; «del corte» = '
                     'la uetr no se dio de alta ese mismo día'}


def cifras_de_control(leido: dict, vivo: dict, delta: dict, totales: dict, sha: str) -> dict:
    documentos = leido['documentos']
    base = cifras.agregar(documentos)
    por_llave = cifras.conciliar(leido['conciliacion']['al_corte'], leido['conciliacion']['delta'], 'llave')
    por_id = cifras.conciliar(leido['conciliacion']['al_corte'], leido['conciliacion']['delta'], 'id')
    oraculo = re_registros_del_dia(delta)
    esperados = oraculo['de_documentos_del_corte']
    motivos: dict[str, list] = defaultdict(list)
    for d in documentos:
        if d.destino != cifras.CARGADO and len(motivos[d.destino]) < caminos.MUESTRA:
            motivos[d.destino].append({'documento': '/'.join(d.llave), 'estado': d.estado, 'mes': d.mes,
                                       'motivo': d.motivo})
    calculado = origen_por_mes(documentos)
    origen = {'sql': leido['origen_sql'], 'documentos': calculado,
              'coincide': leido['origen_sql'] == calculado,
              'regla': 'documentos por tipo y mes contados en SQL (GROUP BY) = los que clasifica Python'}
    duplicados = cifras.duplicados_por_documento(documentos)
    negativos = controles(leido, base)
    resultado = {
        'version': 1,
        'que_es': 'cifras de control por documento del legado vivo al congelamiento (corte/medir.py)',
        'huellas_por_documento': {'archivo': HUELLAS, 'sha256': sha, 'documentos': len(documentos),
                                  'columnas': list(cifras.CSV_COLUMNAS)},
        'tablas': totales,
        'consumibles': {'folios': {'respaldo': vivo['al_respaldo']['folios'],
                                   'congelamiento': vivo['al_congelamiento']['folios'], 'ahora': leido['folios']},
                        'identidades': {t: v['ident_current'] for t, v in totales.items()
                                        if v.get('ident_current') is not None}},
        'catalogos': {'monedas': len(leido['catalogo']),
                      'activas': sum(1 for _c, a in leido['catalogo'] if a),
                      'codigos': [c for c, _a in leido['catalogo']]},
        'cifras': base,
        'cuadre': cifras.cuadre(base),
        'origen_independiente': origen,
        'duplicados_por_documento': duplicados,
        'no_viaja_muestra': dict(sorted(motivos.items())),
        'conciliacion': {
            're_registros_del_dia': oraculo,
            'por_llave': por_llave, 'por_id': por_id,
            'regla': 'por llave de negocio: 0 duplicados y sale el registro viejo de cada re-registro del día; por id '
                     '(control negativo): el documento queda dos veces, tantas como re-registros'},
        'controles_negativos': negativos,
    }
    faltas = list(resultado['cuadre'])
    if not origen['coincide']:
        faltas.append('el origen por mes contado en SQL no es el que clasifica Python')
    if duplicados:
        faltas.append(f'duplicados por documento: {len(duplicados)} ({duplicados[:10]})')
    if por_llave['duplicados'] or por_llave['registros_que_salen'] != esperados:
        faltas.append(f"conciliación por llave: {por_llave['duplicados']} duplicados y "
                      f"{por_llave['registros_que_salen']} registros que salen; se esperaban 0 y {esperados}")
    if por_id['duplicados'] != esperados:
        faltas.append(f"el control por id debía duplicar los {esperados} documentos del corte re-registrados el día "
                      "y duplicó "
                      f"{por_id['duplicados']}")
    for nombre in ('un_centavo', 'duplicado', 'grieta_utc'):
        if not negativos.get(nombre, {}).get('detectado'):
            faltas.append(f'control negativo «{nombre}» no detectado')
    resultado['faltas'] = faltas
    resultado['verde'] = not faltas
    return resultado


def totales_de_tablas(corte: dict) -> dict:
    """Totales de todas las tablas del inventario, por foto: lo que no depende del reloj de la corrida."""
    resultado = {}
    for tabla, t in corte['tablas'].items():
        fotos = t.get('fotos', {})
        r = {'identidad': t['identidad'], 'ahora': t['filas_ahora'],
             'respaldo': fotos.get('respaldo', {}).get('filas'),
             'congelamiento': fotos.get('congelamiento', {}).get('filas'),
             'ident_current': t.get('ident_current')}
        if 'por_identidad' in t:
            r.update(delta=t['por_identidad']['delta'], posterior=t['por_identidad']['posterior'],
                     huecos=t['huecos']['cuantos'])
        resultado[tabla] = r
    return resultado


def _ci() -> dict:
    return {k: os.environ.get(v) for k, v in (('repositorio', 'GITHUB_REPOSITORY'), ('corrida', 'GITHUB_RUN_ID'),
                                               ('intento', 'GITHUB_RUN_ATTEMPT'), ('sha', 'GITHUB_SHA'),
                                               ('rama', 'GITHUB_HEAD_REF'))}


def medir(salida: Path, datos: Path = DATOS, respaldos: Path = RESPALDOS) -> tuple[dict, dict]:
    t0 = time.monotonic()
    vivo = _json(_ultimo(datos, 'vivo_*.json'))
    delta = _json(_ultimo(datos, 'delta_*.json'))
    manifiesto = _json(_ultimo(respaldos, 'respaldo_*.json'))
    inv = codigo.inventario()
    with conectar() as conexion:
        cursor = conexion.cursor()
        corte = medir_corte(cursor, inv['tablas'], vivo, delta, manifiesto)
        t1 = time.monotonic()
        leido = leer_documentos(cursor, vivo)
    t2 = time.monotonic()
    salida.mkdir(parents=True, exist_ok=True)
    sha = escribir_huellas(leido['documentos'], salida / HUELLAS)
    control = cifras_de_control(leido, vivo, delta, totales_de_tablas(corte), sha)
    corte = {'version': 1, 'que_es': 'el corte medido por dos caminos sobre el legado vivo (corte/medir.py)',
             'ci': _ci(), 'fotos': {'respaldo_servidor': vivo['al_respaldo'].get('servidor'),
                                    'congelamiento_servidor': vivo['al_congelamiento'].get('servidor'),
                                    'respaldo_utc': delta['respaldo_utc'],
                                    'congelamiento_utc': delta['congelamiento_utc']},
             **corte, 'segundos': {'corte': round(t1 - t0, 1), 'lectura': round(t2 - t1, 1),
                                   'cifras': round(time.monotonic() - t2, 1)}}
    (salida / CORTE).write_text(json.dumps(corte, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (salida / CIFRAS).write_text(json.dumps(control, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return corte, control


def resumen(corte: dict, control: dict) -> str:
    lineas = ['Corte por dos caminos (criterio 3):']
    for tabla, t in corte['tablas'].items():
        if 'por_identidad' not in t:
            lineas.append(f"  {tabla}: sin identidad · {t['filas_ahora']:,} filas")
            continue
        p = t['por_identidad']
        caminos_txt = ' · '.join(
            f"{c['nombre']} {c['delta']}+{c['posterior']} {'✔' if c['comparacion']['coincide'] else '✘'}"
            for c in t['caminos'])
        lineas.append(f"  {tabla}: corte {p['corte']:,} · delta {p['delta']} · posterior {p['posterior']} · "
                      f"huecos {t['huecos']['cuantos']} · {caminos_txt}")
    n = corte.get('control_negativo') or {}
    lineas.append(f"  control negativo (fecha_operacion): nombra {n.get('nombradas')} de {n.get('esperadas')} altas "
                  f"fechadas hacia atrás · detectado={n.get('detectado')}")
    lineas += [f'  ✘ {f}' for f in corte['faltas']]
    c = control
    lineas.append(f"Cifras de control (criterios 7 y 8): {c['huellas_por_documento']['documentos']:,} documentos · "
                  f"sha256 {c['huellas_por_documento']['sha256'][:16]}…")
    for tipo, b in c['cifras']['tipos'].items():
        nv = ' · '.join(f"{m} {v['documentos']:,}" for m, v in b['no_viaja'].items())
        lineas.append(f"  {tipo}: origen {b['origen']['documentos']:,} = cargado {b['cargado']['documentos']:,} + {nv}")
    lineas.append(f"  duplicados por documento: {len(c['duplicados_por_documento'])} · conciliación por llave: "
                  f"{c['conciliacion']['por_llave']['duplicados']} duplicados, "
                  f"{c['conciliacion']['por_llave']['registros_que_salen']} registros viejos salen · por id: "
                  f"{c['conciliacion']['por_id']['duplicados']} duplicados")
    for nombre, r in c['controles_negativos'].items():
        lineas.append(f"  control negativo {nombre}: detectado={r['detectado']}")
    lineas += [f'  ✘ {f}' for f in c['faltas']]
    return '\n'.join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.medir', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--salida', type=Path, required=True)
    parser.add_argument('--datos', type=Path, default=DATOS)
    parser.add_argument('--respaldos', type=Path, default=RESPALDOS)
    args = parser.parse_args(argv)
    corte, control = medir(args.salida, args.datos, args.respaldos)
    print(resumen(corte, control))
    return 0 if corte['coincide'] and control['verde'] else 1


if __name__ == '__main__':
    sys.exit(main())
