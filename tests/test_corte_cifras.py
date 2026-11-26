"""Cifras de control por documento y conciliación por llave de negocio (S3, criterios 7 y 8), sin base. Los
documentos salen de las filas REALES del generador (el periodo corto de las pruebas: las mismas columnas, en el mismo
orden, que lee `corte/medir.py`); cada prueba trae su control negativo."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal

import pytest

from corte import cifras
from corte.cifras import Contexto, Operacion, Partida, Registro, Vigencia
from legado.generador.simulacion import COLUMNAS


def contexto(t: dict, congelamiento: dict | None = None) -> Contexto:
    operaciones = {f[0]: (f[1], f[3]) for f in t['operacion']}
    tope = {f'dbo.{n}': len(t[n]) for n in ('operacion', 'orden_pago', 'partida_liquidada', 'partida_solicitada',
                                             'bitacora')}
    ctx = Contexto(operaciones, frozenset(f[0] for f in t['moneda']), {**tope, **(congelamiento or {})})
    for f in t['partida_liquidada']:
        ctx.partidas_cliente.setdefault(f[1], []).append(Partida(*f))
    for f in t['partida_solicitada']:
        ctx.partidas_corresponsal.setdefault(f[1], []).append(Partida(*f))
    return ctx


@pytest.fixture(scope='module')
def real(datos_chicos):
    t = datos_chicos.tablas
    ctx = contexto(t)
    registros = [Registro(*f) for f in t['orden_pago']]
    ordenes = cifras.documentos_de_orden(registros, ctx)
    operaciones = [cifras.documento_de_operacion(Operacion(*f), ctx.congelamiento['dbo.operacion'], ctx.monedas)
                   for f in t['operacion']]
    por_llave: dict = {}
    for r in registros:
        por_llave.setdefault(cifras.llave_de_orden(r, ctx), []).append(r)
    return {'t': t, 'ctx': ctx, 'registros': registros, 'ordenes': ordenes, 'operaciones': operaciones,
            'documentos': operaciones + ordenes, 'por_llave': por_llave}


def test_las_columnas_que_lee_el_corte_son_las_del_legado_en_su_orden():
    assert Operacion._fields == COLUMNAS['operacion']
    assert Registro._fields == COLUMNAS['orden_pago']
    assert Partida._fields == COLUMNAS['partida_liquidada'] == COLUMNAS['partida_solicitada']


def test_un_documento_por_llave_de_negocio_aunque_tenga_varios_registros(real, datos_chicos):
    usados = {f[3] for f in real['t']['orden_pago']}
    assert len(real['ordenes']) == len(usados)                            # un documento por uetr registrado
    varios = [k for k, regs in real['por_llave'].items() if len(regs) > 1]
    assert len(varios) > 100                                              # hay re-registros de verdad
    assert cifras.duplicados_por_documento(real['documentos']) == []
    assert Counter(d.destino for d in real['ordenes']) == {cifras.CARGADO: len(real['ordenes'])}
    # el oráculo del generador: cada documento con el estatus de su último registro
    estatus = {d.uetr: d.filas[-1][16] for d in datos_chicos.documentos if d.filas}
    assert {d.documento: d.estado for d in real['ordenes']} == estatus


def test_la_huella_no_depende_del_id_y_si_de_un_centavo(real):
    llave = next(k for k, regs in sorted(real['por_llave'].items()) if len(regs) > 1)
    regs = real['por_llave'][llave]
    original = cifras.documento_de_orden(regs, real['ctx'])
    # mismo documento con otros ids internos (como los daría otra base): la huella no cambia
    corridos = [r._replace(id=r.id + 10_000_000) for r in regs]
    ctx = real['ctx']
    for r, c in zip(regs, corridos):
        ctx.partidas_cliente[c.id] = [p._replace(id=p.id + 10_000_000, orden_id=c.id)
                                      for p in ctx.partidas_cliente.get(r.id, [])]
        ctx.partidas_corresponsal[c.id] = [p._replace(orden_id=c.id) for p in ctx.partidas_corresponsal.get(r.id, [])]
    tope = dict(ctx.congelamiento)
    ctx.congelamiento.update({k: v + 10_000_000 for k, v in tope.items()})
    try:
        assert cifras.documento_de_orden(corridos, ctx).huella == original.huella
    finally:
        ctx.congelamiento.update(tope)
    # control negativo: un centavo cambia la huella del documento, la de su mes y los montos, no los conteos
    alterado = cifras.documento_de_orden(cifras.alterar_un_centavo(regs), real['ctx'])
    assert alterado.huella != original.huella
    antes = cifras.agregar(real['documentos'])
    despues = cifras.agregar(cifras.sustituir(real['documentos'], alterado))
    dif = cifras.diferencias(antes, despues)
    assert [(g['tipo'], g['estado'], g['mes']) for g in dif['por_grupo']] == [('orden', original.estado,
                                                                              original.mes)]
    assert [g['distinto'] for g in dif['globales']] == [['huella', 'montos']]
    por_doc = cifras.diferencias_por_documento(real['documentos'], cifras.sustituir(real['documentos'], alterado))
    assert por_doc['distintos'] == 1 and por_doc['muestra_distintos'] == [list(original.llave)]


def test_la_grieta_utc_cuadra_en_totales_y_no_por_mes(real):
    mueven = [d for d in real['documentos'] if d.mes != d.mes_utc]
    assert mueven and all(d.fecha.hour >= 18 for d in mueven)            # la noche del último día del mes
    local, utc = cifras.agregar(real['documentos']), cifras.agregar(real['documentos'], utc=True)
    dif = cifras.diferencias(local, utc)
    assert dif['globales'] == [] and dif['por_grupo']
    meses = {(g['tipo'], g['mes']) for g in dif['por_grupo']}
    assert {(d.tipo, d.mes) for d in mueven} <= meses and {(d.tipo, d.mes_utc) for d in mueven} <= meses
    # control negativo: sin los documentos de esas noches, el mes en UTC da las mismas cifras
    quietos = [d for d in real['documentos'] if d.mes == d.mes_utc]
    assert cifras.diferencias(cifras.agregar(quietos), cifras.agregar(quietos, utc=True)) == {
        'globales': [], 'por_grupo': []}


def test_un_duplicado_por_documento_falla_nombrandolo(real):
    llave, regs = next((k, v) for k, v in sorted(real['por_llave'].items()) if len(v) == 1)
    ctx = real['ctx']
    nuevo_id = max(r.id for r in real['registros']) + 1
    # el registro plantado entra en la foto del congelamiento (si no, sería posterior y no duplicaría nada)
    en_foto = Contexto(ctx.operaciones, ctx.monedas, {**ctx.congelamiento, 'dbo.orden_pago': nuevo_id},
                       ctx.partidas_cliente, ctx.partidas_corresponsal)
    doble = cifras.documento_de_orden(cifras.duplicar_vigente(regs, nuevo_id), en_foto)
    assert doble.destino == 'duplicado' and f'{regs[0].id}, {nuevo_id}' in doble.motivo
    # fuera de la foto, el mismo registro es posterior: el documento sigue cargado con su único registro
    assert cifras.documento_de_orden(cifras.duplicar_vigente(regs, nuevo_id), ctx).destino == cifras.CARGADO
    assert cifras.duplicados_por_documento(cifras.sustituir(real['documentos'], doble)) == ['/'.join(('orden',
                                                                                                      *llave))]
    # la misma llave dos veces en la lista (dos documentos) también cuenta
    otra = cifras.documento_de_orden(regs, real['ctx'])
    assert cifras.duplicados_por_documento([otra, otra]) == ['/'.join(otra.llave)]


def test_cargado_mas_lo_que_no_viaja_es_el_origen_por_tipo_y_por_grupo(real):
    t, ctx = real['t'], real['ctx']
    tope = len(t['orden_pago']) - 5                   # las últimas 5 filas, «posteriores» al congelamiento
    posterior = Contexto(ctx.operaciones, ctx.monedas, {**ctx.congelamiento, 'dbo.orden_pago': tope},
                         ctx.partidas_cliente, ctx.partidas_corresponsal)
    documentos = cifras.documentos_de_orden(real['registros'], posterior)
    destinos = Counter(d.destino for d in documentos)
    assert destinos['pendiente'] >= 1 and destinos[cifras.CARGADO] == len(documentos) - destinos['pendiente']
    # sin detalle: una orden vigente sin partidas del cliente; dato sucio: una moneda fuera del catálogo
    llave = next(k for k, v in sorted(real['por_llave'].items()) if len(v) == 1)
    solo = real['por_llave'][llave][0]
    sin_partidas = Contexto(ctx.operaciones, ctx.monedas, ctx.congelamiento,
                            {k: v for k, v in ctx.partidas_cliente.items() if k != solo.id}, ctx.partidas_corresponsal)
    assert cifras.documento_de_orden([solo], sin_partidas).destino == 'sin_detalle'
    assert cifras.documento_de_orden([solo._replace(moneda='XXX')], ctx).destino == 'dato_sucio'
    mezcla = cifras.sustituir(documentos, cifras.documento_de_orden([solo], sin_partidas))
    agregado = cifras.agregar(mezcla)
    assert cifras.cuadre(agregado) == []
    b = agregado['tipos']['orden']
    assert b['origen']['documentos'] == len(mezcla) == b['cargado']['documentos'] + sum(
        v['documentos'] for v in b['no_viaja'].values())
    assert b['no_viaja']['sin_detalle']['documentos'] == 1
    # control negativo: un grupo cuyo cargado no suma el origen no cuadra
    roto = cifras.agregar(mezcla)
    roto['grupos'][0]['cargado']['documentos'] += 1
    assert len(cifras.cuadre(roto)) == 1


def test_el_estatus_al_congelamiento_se_reconstruye_con_la_bitacora():
    actual = {1: 'LIQUIDADA', 2: 'REEMPLAZADA', 3: 'ENVIADA'}
    cambios = [(10, 1, 'ENVIADA', 'LIQUIDADA'), (11, 2, 'ENVIADA', 'REEMPLAZADA')]
    assert cifras.estatus_en(actual, cambios) == {1: 'ENVIADA', 2: 'ENVIADA', 3: 'ENVIADA'}
    assert cifras.estatus_en(actual, cambios[1:]) == {1: 'LIQUIDADA', 2: 'ENVIADA', 3: 'ENVIADA'}
    # control negativo: un cambio que la bitácora no explica, o uno del job (horas_liquidacion), no se reconstruye
    with pytest.raises(ValueError, match='cambio sin bitácora'):
        cifras.estatus_en(actual, [(10, 3, 'ENVIADA', 'LIQUIDADA')])
    with pytest.raises(ValueError, match='horas_liquidacion'):
        cifras.estatus_en({1: 'CONCILIADA'}, [(12, 1, 'LIQUIDADA', 'CONCILIADA')])


def test_el_re_registro_del_dia_se_concilia_por_llave_y_por_id_queda_dos_veces(real):
    """El pendiente re-registrado el día del corte: su registro viejo es de la foto del corte (vigente ENTONCES) y el
    nuevo viene en el delta con otro id y el mismo documento."""
    llave, regs = next((k, v) for k, v in sorted(real['por_llave'].items()) if len(v) >= 2)
    viejo, nuevo = regs[-2], regs[-1]
    al_corte = [Vigencia(r.id, llave, 'ENVIADA' if r.id == viejo.id else r.estatus) for r in regs[:-1]]
    otros = [Vigencia(10 ** 6 + i, (f'otro-{i}', '0001'), 'ENVIADA') for i in range(3)]
    delta = [Vigencia(nuevo.id, llave, 'ENVIADA'), Vigencia(10 ** 6 + 9, ('nuevo', '0001'), 'ENVIADA')]
    por_llave = cifras.conciliar(al_corte + otros, delta, 'llave')
    assert por_llave['duplicados'] == 0 and por_llave['muestra_registros_que_salen'] == [viejo.id]
    assert por_llave['documentos'] == 5
    por_id = cifras.conciliar(al_corte + otros, delta, 'id')
    assert por_id['llaves_duplicadas'] == ['/'.join(llave)]
    assert por_id['muestra_duplicados'][0]['ids'] == [viejo.id, nuevo.id]
    # control negativo: un delta que trae DOS registros vigentes del mismo documento falla también por llave
    doble = cifras.conciliar(al_corte, [*delta, Vigencia(nuevo.id + 10 ** 7, llave, 'ENVIADA')], 'llave')
    assert doble['llaves_duplicadas'] == ['/'.join(llave)]
    with pytest.raises(ValueError):
        cifras.conciliar([], [], 'fecha')


def test_el_mes_es_el_de_la_hora_local_y_la_grieta_lo_pasa_a_utc():
    assert cifras.mes(datetime(2023, 1, 31, 17, 59)) == cifras.mes(datetime(2023, 1, 31, 17, 59), utc=True) == '2023-01'
    assert cifras.mes(datetime(2023, 1, 31, 18, 0), utc=True) == '2023-02'          # UTC-6 sin horario de verano
    assert cifras.mes(datetime(2022, 5, 31, 18, 30), utc=True) == '2022-05'         # UTC-5: con horario de verano
    assert cifras.mes(datetime(2022, 5, 31, 19, 0), utc=True) == '2022-06'


def test_la_forma_canonica_conserva_la_escala_y_las_milesimas():
    a = cifras.huella({'monto': Decimal('10.50'), 'f': datetime(2023, 1, 1, 0, 0, 0, 3000)})
    assert a != cifras.huella({'monto': Decimal('10.5'), 'f': datetime(2023, 1, 1, 0, 0, 0, 3000)})
    assert a != cifras.huella({'monto': Decimal('10.50'), 'f': datetime(2023, 1, 1)})
    with pytest.raises(TypeError):
        cifras.huella({'x': object()})


def test_el_csv_de_huellas_es_determinista_y_rechaza_valores_con_coma(real):
    uno = ''.join(cifras.renglones_csv(real['documentos']))
    dos = ''.join(cifras.renglones_csv(list(reversed(real['documentos']))))
    assert uno == dos and uno.splitlines()[0] == ','.join(cifras.CSV_COLUMNAS)
    assert len(uno.splitlines()) == len(real['documentos']) + 1
    raro = cifras.Documento('orden', 'a,b', '0001', 'ENVIADA', datetime(2023, 1, 1), 'x', (), cifras.CARGADO)
    with pytest.raises(ValueError):
        list(cifras.renglones_csv([raro]))
