"""Delta del mismo día (S3 paso 4, ADR 0013 y 0016; criterios 5, 7, 8 y 12), sin base. Lo que necesita el legado vivo y
la base cerrada (ensayo, aplicar, reversa y los 6 controles negativos) corre en el CI (`corte/delta_ci.py`).

El oráculo de los cambios sobre las filas del corte NO es `corte/delta.py`: se reproduce aquí lo que escriben los
procedimientos del legado (sp_registrar_orden: «I» de la orden nueva y «U» del registro ENVIADA de su uetr a
REEMPLAZADA; sp_registrar_liquidacion: «U» del registro ENVIADA a LIQUIDADA) al correr el guion REAL del delta sobre los
tres años del generador, y se contrasta con lo medido por dos caminos y versionado en el paso 2."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from corte import carga, cifras, delta, runbook, runbook_delta
from corte.cifras import Contexto, Operacion, Partida, Registro

RAIZ = Path(__file__).resolve().parent.parent
DELTA_SQL = (RAIZ / 'corte' / 'delta.sql').read_text(encoding='utf-8')
PROCEDIMIENTOS = (RAIZ / 'legado' / 'sql' / '05_procedimientos.sql').read_text(encoding='utf-8')
MEDIDO = json.loads((RAIZ / 'corte' / 'cifras' / 'corte.json').read_text(encoding='utf-8'))
PASO_2 = json.loads((RAIZ / 'corte' / 'cifras' / 'cifras-de-control.json').read_text(encoding='utf-8'))
I_ESTATUS = carga.TABLAS['orden_pago'].nombres.index('estatus')


def bitacora_del_dia(datos) -> dict:
    """Las escrituras del legado durante el día del corte, reproducidas sobre el guion real: los «U» de orden_pago con
    su id de bitácora, el congelamiento de cada tabla (al pasar a la fase posterior) y el estatus final de cada orden.
    sp_registrar_orden escribe 3 partidas del cliente (4 con gastos OUR); sp_registrar_liquidacion, 1 del corresponsal
    (2 con comisión)."""
    t = datos.tablas
    enviada = {f[3]: f[0] for f in t['orden_pago'] if f[I_ESTATUS] == 'ENVIADA'}
    estatus = {f[0]: f[I_ESTATUS] for f in t['orden_pago']}
    sig = {n: len(t[n]) for n in ('operacion', 'orden_pago', 'partida_solicitada', 'partida_liquidada', 'bitacora')}
    filas, tope = [], {}
    for paso in datos.pasos:
        if paso['fase'] == 'posterior_congelamiento' and not tope:
            tope = dict(sig)
        a = paso['args']
        if paso['accion'] == 'operacion':
            sig['operacion'] += 1
        elif paso['accion'] == 'orden':
            sig['orden_pago'] += 1
            sig['bitacora'] += 1                                   # «I» de la orden nueva
            sig['partida_liquidada'] += 4 if a['gastos'] == 'OUR' else 3
            estatus[sig['orden_pago']] = 'ENVIADA'
            anterior = enviada.get(a['uetr'])
            if anterior is not None:
                sig['bitacora'] += 1
                filas.append((sig['bitacora'], anterior, 'ENVIADA', 'REEMPLAZADA'))
                estatus[anterior] = 'REEMPLAZADA'
            enviada[a['uetr']] = sig['orden_pago']
        elif paso['accion'] == 'liquidacion' and a['uetr'] in enviada:
            sig['partida_solicitada'] += 2 if a['comision'] else 1
            sig['bitacora'] += 1
            orden = enviada.pop(a['uetr'])
            filas.append((sig['bitacora'], orden, 'ENVIADA', 'LIQUIDADA'))
            estatus[orden] = 'LIQUIDADA'
    return {'filas': filas, 'reproducido': tope or dict(sig), 'estatus': estatus}


@pytest.fixture(scope='module')
def dia(datos):
    b = bitacora_del_dia(datos)
    medido = {t.removeprefix('dbo.'): v['por_identidad']['congelamiento'] for t, v in MEDIDO['tablas'].items()
              if v.get('por_identidad')}
    return {**b, 'corte': runbook.cortes(None), 'tope': medido}


# ── qué entra y cómo cambian las filas del corte ────────────────────────────────────────────────────────────────

def test_el_oraculo_reproduce_el_congelamiento_medido_en_el_paso_2(dia):
    """Antes de usarlo: lo reproducido llega exactamente al congelamiento medido por dos caminos, en las 5 tablas
    (operación 421 + corte, orden 270, partidas 271 y 893, bitácora 571)."""
    assert dia['reproducido'] == dia['tope'] == {'bitacora': 685_847, 'operacion': 412_546, 'orden_pago': 270_886,
                                                 'partida_liquidada': 894_067, 'partida_solicitada': 245_140}
    assert {t: dia['tope'][t] - dia['corte'][t] for t in dia['tope']} == {
        'bitacora': 571, 'operacion': 421, 'orden_pago': 270, 'partida_liquidada': 893, 'partida_solicitada': 271}


def test_los_cambios_al_corte_salen_de_la_bitacora_138_re_registros_del_corte(dia):
    cambios = delta.cambios_por_bitacora(dia['filas'], dia['corte'], dia['tope'])
    resumen = delta.resumen_de_cambios(cambios)
    esperados = PASO_2['conciliacion']['re_registros_del_dia']
    assert cambios['faltas'] == [] and cambios['posteriores'] == []
    assert resumen['al_corte']['REEMPLAZADA'] == esperados['de_documentos_del_corte'] == 138
    assert resumen['del_delta'].get('REEMPLAZADA', 0) == esperados['de_documentos_nuevos_del_dia'] == 1
    # las liquidaciones del día: 162 documentos LIQUIDADA en el paso 2, repartidos entre filas del corte y del delta
    liquidadas = resumen['al_corte'].get('LIQUIDADA', 0) + resumen['del_delta'].get('LIQUIDADA', 0)
    grupos = [g for g in PASO_2['cifras']['grupos'] if g['tipo'] == 'orden' and g['estado'] == 'LIQUIDADA']
    assert liquidadas == sum(g['origen']['documentos'] for g in grupos) == 162
    # los registros viejos que salen son los que el paso 2 vio salir al conciliar por llave
    viejos = sorted(k for k, c in cambios['al_corte'].items() if c[-1].nuevo == 'REEMPLAZADA')
    muestra = PASO_2['conciliacion']['por_llave']['muestra_registros_que_salen']
    assert viejos[:len(muestra)] == muestra


def test_la_bitacora_separa_lo_posterior_y_nombra_una_cadena_rota():
    corte = {'bitacora': 100, 'orden_pago': 10}
    tope = {'bitacora': 200, 'orden_pago': 20}
    filas = [(90, 5, 'ENVIADA', 'LIQUIDADA'),            # antes del corte: ya está en la foto
             (101, 5, 'ENVIADA', 'REEMPLAZADA'),          # fila del corte
             (102, 15, 'ENVIADA', 'LIQUIDADA'),           # fila del delta
             (201, 6, 'ENVIADA', 'LIQUIDADA'),            # después del congelamiento: al barrido
             (202, 25, 'ENVIADA', 'REEMPLAZADA')]         # fila posterior: ni se mira
    cambios = delta.cambios_por_bitacora(filas, corte, tope)
    assert list(cambios['al_corte']) == [5] and list(cambios['del_delta']) == [15]
    assert [c.bitacora for c in cambios['posteriores']] == [201] and cambios['faltas'] == []
    # control negativo: dos pasos que no encadenan (ENVIADA → LIQUIDADA y luego ENVIADA → REEMPLAZADA)
    roto = delta.cambios_por_bitacora([(101, 5, 'ENVIADA', 'LIQUIDADA'), (102, 5, 'ENVIADA', 'REEMPLAZADA')],
                                      corte, tope)
    assert roto['faltas'] and 'cadena rota' in roto['faltas'][0]


def test_las_actualizaciones_son_exactamente_las_que_la_bitacora_anota(datos, dia):
    """Origen al congelamiento contra la foto del corte: las filas distintas son las de la bitácora, sólo en las
    columnas mutables. Cada desvío se nombra."""
    cambios = delta.cambios_por_bitacora(dia['filas'], dia['corte'], dia['tope'])
    foto = datos.tablas['orden_pago']
    origen = [(*f[:I_ESTATUS], dia['estatus'][f[0]], *f[I_ESTATUS + 1:]) for f in foto]
    actualizar, faltas = delta.actualizaciones(origen, foto, cambios['al_corte'])
    assert faltas == [] and sorted(actualizar) == sorted(cambios['al_corte'])
    assert Counter(v['estatus'] for v in actualizar.values()) == Counter(
        c[-1].nuevo for c in cambios['al_corte'].values())
    k = min(actualizar)
    i_monto = carga.TABLAS['orden_pago'].nombres.index('monto')
    # control negativo 1: una columna que el legado no escribe sobre una orden registrada
    otro = [(*f[:i_monto], f[i_monto] + Decimal('0.01'), *f[i_monto + 1:]) if f[0] == k else f for f in origen]
    assert any("cambió ['monto']" in x for x in delta.actualizaciones(otro, foto, cambios['al_corte'])[1])
    # control negativo 2: un estatus que cambió sin bitácora
    sin = next(f[0] for f in foto if f[0] not in actualizar and f[I_ESTATUS] == 'CONCILIADA')
    otro = [(*f[:I_ESTATUS], 'VENCIDA', *f[I_ESTATUS + 1:]) if f[0] == sin else f for f in origen]
    assert f"orden {sin}: cambió ['estatus'] (CONCILIADA → VENCIDA) y la bitácora no lo anota" in \
        delta.actualizaciones(otro, foto, cambios['al_corte'])[1]
    # control negativo 3: el destino no está en la foto del corte (ya trae el valor nuevo)
    destino = [(*f[:I_ESTATUS], 'REEMPLAZADA', *f[I_ESTATUS + 1:]) if f[0] == k else f for f in foto]
    assert any('no está en la foto del corte' in x for x in delta.actualizaciones(origen, destino,
                                                                                  cambios['al_corte'])[1])


def test_el_estado_es_el_del_congelamiento_y_lo_del_job_no_se_reconstruye():
    fila = tuple(range(carga.TABLAS['orden_pago'].nombres.index('estatus'))) + ('LIQUIDADA', None)
    foto, faltas = delta.al_congelamiento([fila], [delta.Cambio(900, 0, 'ENVIADA', 'LIQUIDADA')])
    assert faltas == [] and foto[0][I_ESTATUS] == 'ENVIADA'
    conciliada = fila[:I_ESTATUS] + ('CONCILIADA', Decimal('3.50'))
    _foto, faltas = delta.al_congelamiento([conciliada], [delta.Cambio(900, 0, 'LIQUIDADA', 'CONCILIADA')])
    assert faltas and 'horas_liquidacion' in faltas[0]


def test_el_congelamiento_es_el_del_paso_2_y_el_destino_tiene_que_llegar_justo_al_corte(dia):
    vivo = {'al_congelamiento': {t: {'max_id': n} for t, n in dia['tope'].items()}}
    assert delta.congelamiento(MEDIDO, vivo)[1] == []
    vivo['al_congelamiento']['operacion'] = {'max_id': 412_547}
    assert delta.congelamiento(MEDIDO, vivo)[1] == [
        'operacion: el congelamiento medido en el paso 2 es 412546 y la foto del vivo dice 412547']
    corte = dia['corte']
    assert delta.guarda_del_corte(corte, corte) == []
    # repetir el delta: el destino ya llega al congelamiento
    assert delta.guarda_del_corte({**corte, 'operacion': 412_546}, corte) == [
        'operacion: el destino llega al id 412546 y el corte es 412125']


# ── el catálogo ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_el_catalogo_del_congelamiento_alta_de_sle_y_baja_de_sll(datos):
    destino = [tuple(f) for f in datos.tablas['moneda']]
    sll = next(f for f in destino if f[0] == 'SLL')
    foto = [f if f[0] != 'SLL' else (*sll[:4], 0) for f in destino] + [('SLE', '925', 'Leone de Sierra Leona', 2, 1)]
    cat = delta.catalogo(foto, destino, foto)
    assert [f[0] for f in cat['insertar']] == ['SLE'] and cat['actualizar'] == {'SLL': {'activa': 0}}
    assert cat['faltas'] == [] and cat['posteriores'] == []
    assert len(foto) == PASO_2['catalogos']['monedas'] == 12
    # lo que cambió después del congelamiento queda para el barrido, no entra
    ahora = [f if f[0] != 'SLE' else (*f[:4], 0) for f in foto]
    assert delta.catalogo(foto, destino, ahora)['posteriores'] == ['SLE']
    # controles negativos: otra columna, una moneda que desaparece, una foto sin catálogo
    renombrada = [f if f[0] != 'USD' else (f[0], f[1], 'Otro nombre', *f[3:]) for f in foto]
    assert "moneda USD: cambió ['nombre']" in delta.catalogo(renombrada, destino, renombrada)['faltas'][0]
    sin_usd = [f for f in foto if f[0] != 'USD']
    assert 'moneda USD: está en el destino' in delta.catalogo(sin_usd, destino, sin_usd)['faltas'][0]
    assert 'no trae el catálogo' in delta.catalogo(None, destino, foto)['faltas'][0]


# ── la selección por id y los folios ────────────────────────────────────────────────────────────────────────────

def test_un_delta_por_fecha_pierde_las_altas_fechadas_hacia_atras_y_las_nombra(datos):
    """Las altas del reenvío de la sucursal: id nuevo (después del corte) y fecha de negocio anterior al respaldo."""
    corte = runbook.cortes(None)['operacion']
    altas = [p for p in datos.pasos if p['fase'] == 'delta' and p['accion'] == 'operacion']
    respaldo = datetime.fromisoformat(MEDIDO['fotos']['respaldo_utc']).astimezone(cifras.CDMX).replace(tzinfo=None)
    por_id = list(range(corte + 1, corte + len(altas) + 1))
    por_fecha = [i for i, p in zip(por_id, altas) if datetime.fromisoformat(p['args']['fecha_operacion']) > respaldo]
    nombres = {i: f"sucursal {p['args']['sucursal']}" for i, p in zip(por_id, altas)}
    comparacion = delta.comparar_seleccion(por_id, por_fecha, nombres)
    assert comparacion['faltan'] == 5 and not comparacion['coincide']
    assert comparacion['muestra_faltan'] == [f'{i} (sucursal 0012)' for i in range(412_185, 412_190)]
    assert delta.comparar_seleccion(por_id, por_id)['coincide']


def test_con_otra_seleccion_el_plan_cambia_de_sha_y_anota_lo_que_trae_de_mas():
    lote = [(1, 'FX-1'), (2, 'FX-2'), (3, 'FX-3')]
    d = {'corte': {}, 'congelamiento': {}, 'rangos': {'operacion': {'desde': 0, 'hasta': 3, 'filas': 3}},
         'lotes': {'operacion': lote}, 'huellas_origen': {'operacion': 'x'}, 'actualizar': {}, 'catalogo': {},
         'secuencias': {}}
    d['sha'] = delta.plan_sha(d)
    otro = delta.con_seleccion(d, 'operacion', [1, 3, 9], 'fecha')
    assert [f[0] for f in otro['lotes']['operacion']] == [1, 3] and otro['rangos']['operacion']['filas'] == 2
    assert otro['seleccion_ids'] == {'operacion': [1, 3, 9]} and otro['sha'] != d['sha']
    assert d['lotes']['operacion'] == lote                         # el plan original no se toca


def test_un_folio_sin_margen_choca_con_los_posteriores_al_congelamiento():
    """Los números del paso 2: el legado vivo deja FX en 412,557 y OP en 150,855; el cierre los subió a 422,126 y
    160,720. Sin margen, aun subido por encima de los folios del delta (412,547 y 150,851), choca."""
    usados = PASO_2['consumibles']['folios']['ahora']
    assert usados == {'FX': 412_557, 'OP': 150_855}
    con_margen = {'FX': 422_126, 'OP': 160_720}
    assert delta.choques_de_folio(con_margen, usados, {'FX': 412_546, 'OP': 150_850}) == []
    posteriores = {'OP': [f'OP-{n:09d}' for n in range(150_851, 150_855)]}
    choques = delta.choques_de_folio({'FX': 412_547, 'OP': 150_851}, usados, {'FX': 412_546, 'OP': 150_850},
                                     posteriores)
    assert choques[0].startswith('folio FX: el TO-BE numeraría desde FX-000412547') and '10 folios' in choques[0]
    assert '4 folios chocan' in choques[1] and all(f in choques[1] for f in posteriores['OP'])
    # el borde: el siguiente justo después del último usado no choca; uno menos, sí
    assert delta.choques_de_folio({'OP': 150_855}, usados, {}) == []
    assert '1 folios chocan' in delta.choques_de_folio({'OP': 150_854}, usados, {})[0]


# ── la reversa ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_la_reversa_se_genera_antes_con_los_valores_previos_de_cada_update():
    d = {'sha': 'a' * 64, 'rangos': {'operacion': {'desde': 10, 'hasta': 15, 'filas': 5},
                                     'bitacora': {'desde': 7, 'hasta': 7, 'filas': 0}},
         'actualizar': {4: {'estatus': 'REEMPLAZADA', 'horas_liquidacion': None},
                        2: {'estatus': 'CONCILIADA', 'horas_liquidacion': Decimal('12.50')}},
         'catalogo': {'insertar': [('SLE', '925', 'Leone', 2, True)], 'actualizar': {'SLL': {'activa': False}}}}
    previa = {'tablas': {'operacion': {'filas': 10}},
              'secuencias': {'operacion': {'last_value': 10, 'is_called': True}},
              'folios': {'FX': {'siguiente': 99, 'actualizado': None}}}
    anteriores = {'orden_pago': {4: {'estatus': 'ENVIADA', 'horas_liquidacion': None},
                                 2: {'estatus': 'LIQUIDADA', 'horas_liquidacion': Decimal('0.50')}},
                  'moneda': {'SLL': {'activa': True}}}
    rev = delta.reversa(d, previa, anteriores)
    assert rev['borrar'] == {'operacion': {'desde': 10, 'hasta': 15}}       # sin filas, nada que borrar
    assert rev['restaurar']['orden_pago'] == {'2': {'estatus': 'LIQUIDADA', 'horas_liquidacion': '0.50'},
                                              '4': {'estatus': 'ENVIADA', 'horas_liquidacion': None}}
    assert rev['catalogo'] == {'borrar': ['SLE'], 'restaurar': {'SLL': {'activa': True}}}
    assert rev['secuencias'] == previa['secuencias'] and rev['folios'] == {'FX': 99}
    assert rev['huella_previa'] == previa and rev['plan_sha'] == d['sha']
    guardada = json.loads(json.dumps(rev))                                # se guarda tal cual (archivo y jsonb)
    # el valor previo vuelve con su tipo y su escala
    assert delta.valor_de('orden_pago', 'horas_liquidacion', guardada['restaurar']['orden_pago']['2'][
        'horas_liquidacion']) == Decimal('0.50')
    assert str(delta.valor_de('orden_pago', 'horas_liquidacion', '0.50')) == '0.50'
    assert delta.valor_de('orden_pago', 'estatus', 'ENVIADA') == 'ENVIADA'


def test_la_huella_previa_del_delta_tambien_compara_los_folios():
    a = {'tablas': {'x': 1}, 'secuencias': {}, 'folios': {'OP': {'siguiente': 1}}}
    assert delta.diferencias(a, a) == []
    assert delta.diferencias(a, {**a, 'folios': {'OP': {'siguiente': 2}}}) == [
        "folio OP: {'siguiente': 1} → {'siguiente': 2}"]


# ── las cifras de control contra las del paso 2 ─────────────────────────────────────────────────────────────────

def _documentos(t: dict, tope_ordenes: int) -> list[cifras.Documento]:
    operaciones = {f[0]: (f[1], f[3]) for f in t['operacion']}
    tope = {f'dbo.{n}': len(t[n]) for n in ('operacion', 'partida_liquidada', 'partida_solicitada', 'bitacora')}
    ctx = Contexto(operaciones, frozenset(f[0] for f in t['moneda']), {**tope, 'dbo.orden_pago': tope_ordenes})
    for f in t['partida_liquidada']:
        ctx.partidas_cliente.setdefault(f[1], []).append(Partida(*f))
    for f in t['partida_solicitada']:
        ctx.partidas_corresponsal.setdefault(f[1], []).append(Partida(*f))
    ops = [cifras.documento_de_operacion(Operacion(*f), tope['dbo.operacion'], ctx.monedas) for f in t['operacion']]
    return ops + cifras.documentos_de_orden([Registro(*f) for f in t['orden_pago']], ctx)


def test_el_destino_cuadra_con_lo_cargado_del_paso_2_y_cada_desvio_se_nombra(datos_chicos):
    """Con documentos REALES (el periodo corto): un «paso 2» donde las últimas órdenes son pendientes, y un destino que
    trae exactamente lo cargado. Destino = cargado y destino + no viaja = origen, por tipo y por grupo."""
    t = datos_chicos.tablas
    tope = len(t['orden_pago']) - 3
    origen = _documentos(t, tope)
    paso_2 = cifras.agregar(origen)
    assert paso_2['tipos']['orden']['no_viaja']['pendiente']['documentos'] >= 1
    cargados = [x for x in origen if x.destino == cifras.CARGADO]
    en_destino = [x for x in _documentos({**t, 'orden_pago': [f for f in t['orden_pago'] if f[0] <= tope]}, tope)]
    assert sorted(x.llave for x in en_destino) == sorted(x.llave for x in cargados)
    comparacion = delta.contra_el_paso_2(cifras.agregar(en_destino), paso_2)
    assert comparacion['faltas'] == [] and comparacion['cuadra']
    assert comparacion['tipos']['orden']['destino'] + comparacion['tipos']['orden']['no_viaja_paso_2'][
        'pendiente'] == comparacion['tipos']['orden']['origen_paso_2']
    # control negativo 1: un documento que falta en el destino se nombra por su grupo
    falta = cargados[-1]
    sin_uno = delta.contra_el_paso_2(cifras.agregar([x for x in en_destino if x.llave != falta.llave]), paso_2)
    grupo = f'{falta.tipo} · {falta.estado} · {falta.mes}'
    assert not sin_uno['cuadra'] and grupo in sin_uno['grupos_distintos']
    # control negativo 2: un documento con otra cifra (un centavo en su huella) cambia la huella de su grupo
    alterado = [x if x.llave != falta.llave else cifras.Documento(
        x.tipo, x.documento, x.sucursal, x.estado, x.fecha, 'f' * 64, x.montos, x.destino) for x in en_destino]
    assert grupo in delta.contra_el_paso_2(cifras.agregar(alterado), paso_2)['grupos_distintos']
    # control negativo 3: un documento del destino que no clasifica como cargado (un duplicado)
    doble = [x if x.llave != falta.llave else cifras.Documento(
        x.tipo, x.documento, x.sucursal, x.estado, x.fecha, x.huella, x.montos, 'duplicado') for x in en_destino]
    assert any('no clasifican como cargados' in f for f in delta.contra_el_paso_2(cifras.agregar(doble),
                                                                                   paso_2)['faltas'])


def test_las_cifras_del_paso_2_que_se_comparan_son_las_versionadas():
    huella = json.loads((RAIZ / 'corte' / 'cifras' / 'huella.json').read_text(encoding='utf-8'))
    assert runbook_delta._sha256(runbook_delta.CIFRAS_PASO_2) == huella['archivos']['cifras-de-control.json']
    tipos = PASO_2['cifras']['tipos']
    cargados = sum(b['cargado']['documentos'] for b in tipos.values())
    pendientes = sum(b['no_viaja']['pendiente']['documentos'] for b in tipos.values())
    assert (cargados, pendientes, cargados + pendientes) == (563_396, 14, 563_410)


# ── lo derivado por id se re-arma ───────────────────────────────────────────────────────────────────────────────

def test_lo_derivado_por_id_se_rearma_y_no_se_reusa():
    """Hoy no hay derivados en el destino (valores crudos; los parches del ADR 0007 van al TO-BE). El gancho: uno que
    se indexa por id (el registro vigente de cada documento), armado antes del delta, apunta al registro viejo si se
    reusa; re-armado, al nuevo."""
    assert delta.DERIVADOS == ()
    registros = [(10, 'u-1', 'ENVIADA'), (11, 'u-2', 'ENVIADA')]
    llamadas = []

    def vigente_por_documento(conexion) -> int:
        llamadas.append(1)
        conexion['vigente'] = {u: i for i, u, e in conexion['registros'] if e != 'REEMPLAZADA'}
        return len(conexion['vigente'])

    derivado = delta.Derivado('vigente_por_documento', 'id de orden_pago', vigente_por_documento)
    destino = {'registros': list(registros)}
    antes = delta.rearmar(destino, (derivado,))
    reusado = dict(destino['vigente'])
    # el delta: el documento u-1 se re-registra con id nuevo y el viejo sale
    destino['registros'] = [(10, 'u-1', 'REEMPLAZADA'), (11, 'u-2', 'ENVIADA'), (12, 'u-1', 'ENVIADA')]
    despues = delta.rearmar(destino, (derivado,))
    hoy = delta.rearmar(destino)                                          # el gancho de hoy corre vacío
    assert antes == despues == {'vigente_por_documento': 2} and len(llamadas) == 2 and hoy == {}
    assert reusado['u-1'] == 10 and destino['vigente']['u-1'] == 12        # reusarlo apuntaría al registro viejo


# ── permisos y lo que el legado escribe ─────────────────────────────────────────────────────────────────────────

def test_el_rol_del_delta_actualiza_solo_lo_que_el_legado_escribe_y_la_reversa_va_aparte():
    concesiones = re.findall(r'GRANT ([^;]*?) ON ([^;]*?) TO ([^;]*);', DELTA_SQL, re.S)

    def de(rol: str) -> list[tuple[str, str]]:
        return [(p.strip(), o.strip()) for p, o, a in concesiones if rol in [x.strip() for x in a.split(',')]]
    aplica, revierte = de('decant_corte_delta_aplica'), de('decant_corte_delta_revierte')
    assert not [o for p, o in aplica if 'DELETE' in p]
    assert not [o for p, o in revierte if 'INSERT' in p and 'legado' in o]
    actualiza = {o: p for p, o in aplica if p.startswith('UPDATE (')}
    assert actualiza == {o: p for p, o in revierte if p.startswith('UPDATE (')}
    columnas = {o.removeprefix('legado.'): tuple(c.strip() for c in p[len('UPDATE ('):-1].split(','))
                for o, p in actualiza.items()}
    assert columnas == {**delta.MUTABLES, 'folio': ('siguiente',)}
    assert not [o for p, o in aplica + revierte if p.startswith('UPDATE') and '(' not in p and 'legado' in o]
    assert not re.search(r'GRANT[^;]*(no_retorno|accion_negocio|aviso_exterior)', DELTA_SQL)
    assert 'CREATE UNIQUE INDEX ux_carga_delta_un_aplicado' in DELTA_SQL and "WHERE estado = 'aplicado'" in DELTA_SQL


def test_las_columnas_mutables_son_las_que_los_procedimientos_actualizan_sobre_una_orden():
    """Cada UPDATE del legado sobre orden_pago (directo o por alias) asigna sólo columnas de `MUTABLES`; y la baja
    de moneda del vivo sólo `activa`."""
    asignadas = set()
    for cuerpo in re.findall(r'UPDATE dbo\.orden_pago\s+SET (.*?)\s+WHERE', PROCEDIMIENTOS, re.S):
        asignadas |= set(re.findall(r'(\w+)\s*=', cuerpo))
    conciliar = re.search(r'PROCEDURE dbo\.sp_conciliar.*?UPDATE o\s+SET (.*?)\s+FROM dbo\.orden_pago o',
                          PROCEDIMIENTOS, re.S).group(1)
    asignadas |= set(re.findall(r'^\s*(\w+)\s*=', conciliar, re.M)) | set(re.findall(r'SET (\w+)\s*=', conciliar))
    assert asignadas == set(delta.MUTABLES['orden_pago'])
    vivo = (RAIZ / 'legado' / 'vivo' / '__main__.py').read_text(encoding='utf-8')
    assert re.search(r"_BAJA_MONEDA = 'UPDATE dbo\.moneda SET (\w+) = 0", vivo).group(1) == 'activa'
    assert delta.MUTABLES['moneda'] == ('activa',)


def test_las_consultas_del_delta_son_literales_sobre_las_tablas_del_legado():
    for consulta in (delta.CAMBIOS, delta.ORDENES_POSTERIORES, delta.OPERACIONES_POSTERIORES,
                     *delta.POSTERIORES.values()):
        assert 'dbo.' in consulta and '{' not in consulta
    assert set(delta.POSTERIORES) | {'orden_pago', 'operacion'} == {t.nombre for t in carga.CON_IDENTIDAD}
    assert delta.ORDEN_INSERTAR[:2] == ('operacion', 'orden_pago') and delta.ORDEN_BORRAR[-2:] == ('orden_pago',
                                                                                                    'operacion')
