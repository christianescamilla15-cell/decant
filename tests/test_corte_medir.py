"""La medición del corte y su veredicto (S3, criterios 3, 7 y 8), sin base: las consultas las contesta un legado
falso armado con las filas REALES del generador (periodo corto) más un delta y un posterior plantados como los deja
el legado vivo: un pendiente re-registrado el día del corte, un alta fechada hacia atrás y lo que se escribe después
del congelamiento. Cada prueba trae su control negativo."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

import pytest

from corte import caminos, cifras, codigo, medir, veredicto
from legado.vivo import __main__ as vivo_main

TABLAS = ('operacion', 'orden_pago', 'partida_liquidada', 'partida_solicitada', 'bitacora')


class CursorFalso:
    """Contesta cada consulta de corte/medir.py (por su texto) con una función de los parámetros."""

    def __init__(self, respuestas: dict):
        self.respuestas = respuestas
        self.filas: list = []

    def execute(self, sql, parametros=None):
        self.filas = list(self.respuestas[sql](parametros))

    def fetchall(self):
        return self.filas

    def fetchone(self):
        return self.filas[0]

    def __iter__(self):
        return iter(self.filas)


@pytest.fixture(scope='module')
def legado(datos_chicos):
    t = {n: [list(f) for f in filas] for n, filas in datos_chicos.tablas.items()}
    corte = {n: len(t[n]) for n in TABLAS}
    dia = datos_chicos.config.fecha_respaldo
    cambios = []

    def bitacora(llave, accion, antes, despues):
        t['bitacora'].append([len(t['bitacora']) + 1, 'orden_pago', llave, accion, antes, despues, 'sa',
                              datetime(2026, 11, 26, 10, 0, len(t['bitacora']) % 60)])
        if accion == 'U':
            cambios.append((len(t['bitacora']), llave, antes, despues))

    def orden(base: list, nuevo_uetr: str | None, operacion_id: int, registro: datetime) -> list:
        fila = list(base)
        fila[0], fila[1], fila[5], fila[16] = len(t['orden_pago']) + 1, operacion_id, registro, 'ENVIADA'
        if nuevo_uetr:
            fila[3], fila[2] = nuevo_uetr, f'OP-{9_000_000 + fila[0]:09d}'
        t['orden_pago'].append(fila)
        for p in [p for p in datos_chicos.tablas['partida_liquidada'] if p[1] == base[0]]:
            t['partida_liquidada'].append([len(t['partida_liquidada']) + 1, fila[0], *p[2:6], registro, fila[2]])
        bitacora(fila[0], 'I', None, 'ENVIADA')
        return fila

    def operacion(fecha: datetime) -> list:
        fila = list(t['operacion'][-1])
        fila[0] = len(t['operacion']) + 1
        fila[1], fila[2] = f'FX-{fila[0]:09d}', fecha
        t['operacion'].append(fila)
        return fila

    # delta: el pendiente re-registrado a las 07:00 (mismo documento, otro id; el viejo sale) y el alta de ayer
    viejo = next(f for f in t['orden_pago'] if f[16] == 'ENVIADA')
    orden(viejo, None, viejo[1], datetime.combine(dia, datetime.min.time()).replace(hour=7))
    viejo[16] = 'REEMPLAZADA'
    bitacora(viejo[0], 'U', 'ENVIADA', 'REEMPLAZADA')
    atras = operacion(datetime.combine(dia - timedelta(days=1), datetime.min.time()).replace(hour=11))
    congelamiento = {n: len(t[n]) for n in TABLAS}
    # posterior al congelamiento: una operación nueva y su orden
    nueva = operacion(datetime.combine(dia, datetime.min.time()).replace(hour=18, minute=30))
    orden(viejo, '00000000-0000-4000-8000-000000000001', nueva[0], nueva[2])

    def foto(tope: dict, servidor: str) -> dict:
        f = {n: {'filas': tope[n], 'max_id': tope[n]} for n in TABLAS}
        f.update(moneda={'filas': len(t['moneda']), 'max_id': None}, folio={'filas': 2, 'max_id': None},
                 folios={'FX': tope['operacion'] + 1, 'OP': 9_000_000}, servidor=servidor)
        return f

    vivo = {'al_respaldo': foto(corte, '2026-11-26 10:00:00.003'),
            'al_congelamiento': foto(congelamiento, '2026-11-26 10:00:30.000'),
            'choques': {'altas_fechadas_hacia_atras': {'filas': [
                {'id': atras[0], 'folio': atras[1], 'sucursal': atras[3], 'fecha_operacion': str(atras[2])}]}}}
    delta = {'respaldo_utc': datos_chicos.config.respaldo.isoformat(),
             'congelamiento_utc': datos_chicos.config.congelamiento.isoformat(),
             'pasos': [{'fase': 'delta', 'accion': 'orden', 'args': {'uetr': viejo[3], 'reregistro': True}}]}

    def origen_ordenes(_p):
        sucursal = {f[0]: f[3] for f in t['operacion']}
        primero: dict = {}
        for f in t['orden_pago']:
            k = (f[3], sucursal.get(f[1]))
            primero[k] = min(primero.get(k, f[5]), f[5])
        return Counter(f'{x:%Y-%m}' for x in primero.values()).items()

    respuestas = {
        medir.Q_MONEDAS: lambda _p: [(f[0], f[4]) for f in t['moneda']],
        medir.Q_OPERACIONES: lambda _p: [tuple(f) for f in t['operacion']],
        medir.Q_ORDENES: lambda _p: [tuple(f) for f in t['orden_pago']],
        medir.Q_CAMBIOS: lambda p: [c for c in cambios if c[0] > p[0]],
        medir.Q_PARTIDAS_CLIENTE: lambda _p: [tuple(f) for f in t['partida_liquidada']],
        medir.Q_PARTIDAS_CORRESPONSAL: lambda _p: [tuple(f) for f in t['partida_solicitada']],
        medir.Q_ORIGEN_OPERACIONES: lambda _p: Counter(f'{f[2]:%Y-%m}' for f in t['operacion']).items(),
        medir.Q_ORIGEN_ORDENES: origen_ordenes,
        medir.Q_FOLIOS: lambda _p: [('FX', len(t['operacion']) + 1), ('OP', 9_000_000)],
    }
    leido = medir.leer_documentos(CursorFalso(respuestas), vivo)
    return {'t': t, 'vivo': vivo, 'delta': delta, 'leido': leido, 'viejo': viejo, 'atras': atras}


def test_el_re_registro_del_dia_es_un_documento_y_lo_posterior_queda_pendiente(legado):
    documentos = legado['leido']['documentos']
    ordenes = [d for d in documentos if d.tipo == 'orden']
    assert len(ordenes) == len({f[3] for f in legado['t']['orden_pago']})
    assert cifras.duplicados_por_documento(documentos) == []
    re_registrado = next(d for d in ordenes if d.documento == legado['viejo'][3])
    assert re_registrado.destino == cifras.CARGADO and re_registrado.estado == 'ENVIADA'
    pendientes = sorted((d.tipo, d.motivo) for d in documentos if d.destino == 'pendiente')
    assert pendientes == [('operacion', 'registrada después del congelamiento'),
                          ('orden', 'registrada después del congelamiento')]
    # el alta fechada hacia atrás viaja en el mes de su fecha de negocio (el de ayer), no en el del corte
    atras = next(d for d in documentos if d.documento == legado['atras'][1])
    assert atras.destino == cifras.CARGADO and atras.fecha == legado['atras'][2]


def test_las_cifras_de_control_salen_verdes_con_sus_controles_negativos_detectados(legado, tmp_path):
    sha = medir.escribir_huellas(legado['leido']['documentos'], tmp_path / medir.HUELLAS)
    control = medir.cifras_de_control(legado['leido'], legado['vivo'], legado['delta'], {}, sha)
    assert control['faltas'] == [] and control['verde']
    con = control['conciliacion']
    assert con['re_registros_del_dia']['de_documentos_del_corte'] == 1
    assert (con['por_llave']['duplicados'], con['por_llave']['registros_que_salen'], con['por_id']['duplicados']) \
        == (0, 1, 1)
    assert con['por_llave']['muestra_registros_que_salen'] == [legado['viejo'][0]]
    negativos = control['controles_negativos']
    assert {n: r['detectado'] for n, r in negativos.items()} == {'un_centavo': True, 'duplicado': True,
                                                                 'grieta_utc': True}
    assert negativos['un_centavo']['documento'].startswith(legado['viejo'][3])     # el pendiente re-registrado
    assert control['origen_independiente']['coincide']


def test_si_el_delta_por_llave_no_saca_al_registro_viejo_las_cifras_fallan(legado, tmp_path):
    """Control negativo de la conciliación: si el guion dice que hubo un re-registro de un documento del corte que la
    base no muestra, el conteo no cuadra y las cifras salen en rojo."""
    delta = {**legado['delta'], 'pasos': [*legado['delta']['pasos'], {
        'fase': 'delta', 'accion': 'orden', 'args': {'uetr': 'otro-documento', 'reregistro': True}}]}
    control = medir.cifras_de_control(legado['leido'], legado['vivo'], delta, {}, 'x')
    assert not control['verde']
    assert any('conciliación por llave' in f for f in control['faltas'])


def corte_sintetico(control_negativo: bool = True) -> dict:
    """Un corte.json mínimo y coherente con el inventario del código de hoy: cada camino coincide."""
    tablas = codigo.inventario()['tablas']
    coincide = caminos.comparar(caminos.por_identidad([11], 10, 11), caminos.por_sello([(11, 1)], 0, 5))
    t = {}
    for nombre, d in tablas.items():
        if not d['identidad']:
            t[nombre] = {'identidad': False, 'filas_ahora': 2, 'fotos_inconsistentes': []}
            continue
        t[nombre] = {'identidad': True, 'filas_ahora': 11, 'fotos_inconsistentes': [],
                     'por_identidad': {'corte': 10, 'congelamiento': 11, 'delta': 1, 'posterior': 0},
                     'huecos': {'cuantos': 0},
                     'caminos': [{'nombre': c.nombre, 'reloj': c.reloj, 'control_negativo': c.control_negativo,
                                  'delta': 1, 'posterior': 0, 'comparacion': coincide}
                                 for c in caminos.CAMINOS if c.tabla == nombre]}
    return {'ci': {'corrida': '1', 'sha': 'abc'},
            'fotos': {'respaldo_servidor': 'a', 'congelamiento_servidor': 'b', 'respaldo_utc': 'c',
                      'congelamiento_utc': 'd'},
            'cobertura': caminos.cobertura(tablas), 'tablas': t, 'faltas': [], 'coincide': True,
            'control_negativo': {'detectado': control_negativo, 'nombradas': 1, 'esperadas': 1,
                                 'perdidos_por_el_camino': 1, 'altas_fechadas_hacia_atras': ['11 (FX-000000011)']}}


@pytest.fixture
def medido(legado, tmp_path):
    directorio = tmp_path / 'medido'
    directorio.mkdir()
    sha = medir.escribir_huellas(legado['leido']['documentos'], directorio / medir.HUELLAS)
    control = medir.cifras_de_control(legado['leido'], legado['vivo'], legado['delta'], {}, sha)
    (directorio / medir.CIFRAS).write_text(json.dumps(control, ensure_ascii=False), encoding='utf-8')
    (directorio / medir.CORTE).write_text(json.dumps(corte_sintetico(), ensure_ascii=False), encoding='utf-8')
    return directorio


def test_el_veredicto_recuenta_desde_el_csv_y_exige_lo_versionado(medido, tmp_path):
    versionado = tmp_path / 'versionado'
    r = veredicto.evaluar(medido, versionado)
    assert r['verde'] and r['faltas'] == [] and 'primera' in r['avisos'][0]
    veredicto.versionar(medido, None, versionado)
    assert {p.name for p in versionado.iterdir()} == {medir.CIFRAS, medir.CORTE, 'huella.json', 'CIFRAS.md'}
    r = veredicto.evaluar(medido, versionado)
    assert r['verde'] and r['avisos'] == []
    assert '# Corte medido por dos caminos' in (versionado / 'CIFRAS.md').read_text(encoding='utf-8')
    # control negativo: otro legado (aquí, las cifras versionadas de otra corrida) ya no es el versionado
    huella = json.loads((versionado / 'huella.json').read_text(encoding='utf-8'))
    huella['archivos'][medir.HUELLAS] = '0' * 64
    (versionado / 'huella.json').write_text(json.dumps(huella), encoding='utf-8')
    r = veredicto.evaluar(medido, versionado)
    assert not r['verde'] and any(medir.HUELLAS in f and 'versionado' in f for f in r['faltas'])


def test_un_csv_alterado_no_pasa_aunque_las_cifras_digan_otra_cosa(medido, tmp_path):
    ruta = medido / medir.HUELLAS
    renglones = ruta.read_text(encoding='utf-8').splitlines(keepends=True)
    tipo, documento, sucursal, estado, mes, destino, huella = renglones[1].rstrip('\n').split(',')
    renglones[1] = ','.join((tipo, documento, sucursal, estado, '1999-01', destino, huella)) + '\n'
    ruta.write_text(''.join(renglones), encoding='utf-8')
    r = veredicto.evaluar(medido, tmp_path / 'sin-versionar')
    assert not r['verde']
    assert any('no es el que declaran las cifras' in f for f in r['faltas'])
    assert any('1999-01' in f for f in r['faltas'])                 # el recuento nombra el grupo que no existe


def test_el_veredicto_falla_si_el_corte_no_coincide_o_el_control_negativo_no_falla(medido, tmp_path):
    corte = corte_sintetico(control_negativo=False)
    camino = corte['tablas']['dbo.orden_pago']['caminos'][0]
    camino['comparacion'] = caminos.comparar(caminos.por_identidad([11, 12], 10, 12),
                                             caminos.por_sello([(11, 1)], 0, 5))
    (medido / medir.CORTE).write_text(json.dumps(corte), encoding='utf-8')
    faltas = veredicto.evaluar(medido, tmp_path / 'sin-versionar')['faltas']
    assert any('dbo.orden_pago · bitácora (alta): los dos caminos no coinciden' in f for f in faltas)
    assert any('control negativo por fecha_operacion' in f for f in faltas)


def test_el_digest_del_artefacto_publicado_es_el_sha256_del_archivo(medido):
    sha = veredicto.sha256(medido / medir.HUELLAS)
    faltas, filas = veredicto.revisar_artefactos(medido, [f'{medir.HUELLAS}=sha256:{sha}', f'{medir.HUELLAS}={sha}'])
    assert faltas == [] and all(f['coincide'] for f in filas)      # con o sin «sha256:», como lo da cada fuente
    faltas, _ = veredicto.revisar_artefactos(medido, [f'{medir.CIFRAS}=sha256:{sha}', f'{medir.HUELLAS}='])
    assert len(faltas) == 2


class CursorReloj:
    """GETDATE() que avanza cuando se le dice; COUNT/MAX y folios fijos."""

    def __init__(self, instantes):
        self.instantes = list(instantes)
        self.pedidos = 0
        self.fila: list = []

    def execute(self, sql, parametros=None):
        if 'GETDATE' in sql:
            self.pedidos += 1
            self.fila = [self.instantes.pop(0) if len(self.instantes) > 1 else self.instantes[0]]
        else:
            self.fila = [5, 5]

    def fetchone(self):
        return self.fila

    def fetchall(self):
        return [('FX', 10), ('OP', 3)]


def test_la_foto_del_vivo_no_regresa_hasta_que_el_reloj_del_servidor_avanza():
    reloj = CursorReloj(['2026-11-26 10:00:00.003', '2026-11-26 10:00:00.003', '2026-11-26 10:00:00.003',
                         '2026-11-26 10:00:00.007'])
    foto = vivo_main.foto(reloj, espera=0)
    assert foto['servidor'] == '2026-11-26 10:00:00.003' and reloj.pedidos == 4
    assert foto['operacion'] == {'filas': 5, 'max_id': 5} and foto['folios'] == {'FX': 10, 'OP': 3}
    # control: si el reloj ya avanzó al terminar la foto, no espera
    reloj = CursorReloj(['2026-11-26 10:00:00.003', '2026-11-26 10:00:00.010'])
    vivo_main.foto(reloj, espera=0)
    assert reloj.pedidos == 2


def test_lo_versionado_es_coherente_y_su_vista_esta_al_dia():
    """corte/cifras/ es una corrida del CI: el sha de las cifras versionadas es el de huella.json (que el job `corte`
    exige en cada corrida) y CIFRAS.md es la vista que sale de esos archivos."""
    huella = json.loads((veredicto.VERSIONADO / 'huella.json').read_text(encoding='utf-8'))
    assert veredicto.sha256(veredicto.VERSIONADO / medir.CIFRAS) == huella['archivos'][medir.CIFRAS]
    for nombre, artefacto in huella.get('artefactos', {}).items():
        assert artefacto['digest'] == f"sha256:{huella['archivos'][nombre]}"
    from corte import vista_cifras
    assert (veredicto.VERSIONADO / 'CIFRAS.md').read_text(encoding='utf-8') == vista_cifras.markdown(
        veredicto.VERSIONADO)
    control = json.loads((veredicto.VERSIONADO / medir.CIFRAS).read_text(encoding='utf-8'))
    assert control['verde'] and control['huellas_por_documento']['sha256'] == huella['archivos'][medir.HUELLAS]
