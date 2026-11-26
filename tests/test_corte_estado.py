"""Paridad de estado de los que escriben (S3 paso 5, ADR 0015; criterios 2 y 9), sin base. Lo que necesita el respaldo
restaurado y la base cerrada (la copia temporal, los escenarios en transacciones revertidas, la guarda, los controles
negativos y las 6 trampas) corre en el CI (`corte/estado_ci.py`, job `estado` de `carga.yml`)."""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from corte import codigo, estado, estado_ci, trampas
from corte.carga import TABLAS
from corte.estado import Diferencia, Efecto, NoSeCopia, Refs
from corte.sql import leer_scripts
from legado.conexion import lotes
from legado.generador import Config
from radiografia.veredictos import revertida

RAIZ = Path(__file__).resolve().parent.parent
TOBE_SQL = (RAIZ / 'corte' / 'estado_tobe.sql').read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def inv():
    return codigo.inventario()


@pytest.fixture(scope='module')
def modulos():
    return {m.id: m for m in leer_scripts(sorted(codigo.SQL.glob('*.sql')), codigo.RAIZ, codigo.PRINCIPAL).modulos}


@pytest.fixture(scope='module')
def conocidos(inv):
    return {f'dbo.{t}' for t in TABLAS} | {e for e in inv['escritores'] if '/paso:' not in e}


@pytest.fixture(scope='module')
def guion(datos):
    cfg = Config()
    return {'fecha_negocio': cfg.fecha_respaldo.isoformat(), 'congelamiento_utc': cfg.congelamiento.isoformat(),
            'pasos': datos.pasos}


# ── N de N: los escritores salen del inventario ─────────────────────────────────────────────────────────────────

def test_los_8_escritores_del_inventario_tienen_donde_correr(inv):
    """6 procedimientos, el disparador y el paso del job: cada uno con su etapa o corriendo dentro de otro."""
    assert len(inv['escritores']) == 8
    donde = estado.cubiertos()
    assert set(inv['escritores']) <= set(donde)
    assert donde['dbo.sp_reflejar_estatus_operacion'] == 'B1' and donde['dbo.sp_alta_manual_orden'] == 'C1'
    assert donde['dbo.sp_registrar_operacion'] == 'A1'          # la primera etapa que lo corre
    assert set(estado.ANIDADOS) == set(estado.ANIDADOS_EN)


def test_el_n_de_n_falla_nombrando_al_que_no_corre_o_no_tiene_escenario(inv):
    evidencia = {e: {'ejecuciones': 1} for e in inv['escritores']}
    assert estado.n_de_n(inv['escritores'], evidencia)['verde']
    # control negativo 1: uno que no corrió (el servidor no lo vio)
    sin = {**evidencia, 'dbo.sp_alta_manual_orden': {'ejecuciones': 0}}
    r = estado.n_de_n(inv['escritores'], sin)
    assert not r['verde'] and r['no_corrieron'] == ['dbo.sp_alta_manual_orden'] and r['corridos'] == 7
    assert r['faltas'] == ['dbo.sp_alta_manual_orden: tiene escenario (C1) y el servidor no lo vio correr']
    # control negativo 2: el inventario agrega un escritor y ningún escenario lo corre
    nuevo = [*inv['escritores'], 'dbo.sp_nuevo_que_escribe']
    r = estado.n_de_n(nuevo, {**evidencia, 'dbo.sp_nuevo_que_escribe': {'ejecuciones': 5}})
    assert not r['verde'] and r['sin_escenario'] == ['dbo.sp_nuevo_que_escribe']
    assert r['escritores'] == 9 and r['corridos'] == 8


def test_cada_escritor_que_devuelve_una_identidad_tiene_su_tabla(inv):
    """La verificación fija (id devuelto = fila insertada) necesita saber qué tabla insertó cada uno."""
    con_identidad = {o['id'] for o in inv['objetos'] if o['identidad'] and o['acceso'] == 'escribe'}
    assert con_identidad == set(estado.DEVUELVE)
    for e, tabla in estado.DEVUELVE.items():
        assert f'dbo.{tabla}' in next(o for o in inv['objetos'] if o['id'] == e)['escribe']


# ── efectos fuera de la base ────────────────────────────────────────────────────────────────────────────────────

def test_los_efectos_fuera_de_la_base_se_declaran_por_objeto(inv):
    d = estado.efectos_declarados(inv['objetos'], inv['escritores'])
    assert set(d) == set(inv['escritores']) and not any(x['se_niega'] for x in d.values())
    assert d['dbo.sp_registrar_orden']['efectos'] == {'ninguno': 'el inventario no le ve efectos fuera de la base'}
    paso = d[estado.JOB]['efectos']['arranque del job (su horario)']
    assert 'Agent' in paso and 'sp_start_job' in paso and '23:30' in paso
    # un correo se emula; un servidor enlazado detiene la corrida
    falso = [{**next(o for o in inv['objetos'] if o['id'] == 'dbo.sp_conciliar'), 'id': 'dbo.sp_x'}]
    falso[0] = {**falso[0], 'efectivo': {**falso[0]['efectivo'],
                                         'efectos_externos': ['correo', 'servidor enlazado: srv']}}
    d = estado.efectos_declarados(falso, ['dbo.sp_x'])['dbo.sp_x']
    assert d['efectos']['correo'].startswith('emulado') and d['se_niega'] == ['servidor enlazado: srv']


# ── la copia temporal ───────────────────────────────────────────────────────────────────────────────────────────

def test_la_copia_de_cada_escritor_no_nombra_ningun_objeto_de_dbo_y_lleva_el_reloj_inyectado(inv, modulos,
                                                                                            conocidos):
    for e in inv['escritores']:
        if '/paso:' in e:
            continue
        original = modulos[e].texto.strip()
        c = estado.copiar(original, conocidos)
        restos = [n for n in conocidos if re.search(rf'\bdbo\.{n.split(".")[1]}\b', c.texto)]
        assert restos == [], (e, restos)
        assert 'GETDATE' not in c.texto.upper()
        assert c.texto.count(estado.RELOJ_SQL) == c.cuenta['reloj'] == len(re.findall(r'GETDATE\(\)', original))
        cabecera = next(x for x in c.texto.splitlines() if x.startswith('CREATE'))
        assert cabecera.startswith(('CREATE PROCEDURE estado.', 'CREATE TRIGGER estado.')), cabecera
    disparador = estado.copiar(modulos['dbo.tr_orden_pago_bitacora'].texto, conocidos).texto
    assert 'ON estado.orden_pago' in disparador and 'INSERT INTO estado.bitacora' in disparador
    paso = estado.unidad(inv['objetos'], estado.JOB)['comando']
    assert estado.copiar(paso, conocidos).texto == 'EXEC estado.sp_conciliar;'


def test_la_copia_no_toca_cadenas_ni_comentarios_y_se_niega_a_lo_que_no_puede_redirigir():
    texto = ("-- dbo.orden_pago y GETDATE() en un comentario\nCREATE OR ALTER PROCEDURE dbo.sp_x AS "
             "SELECT 'dbo.orden_pago', N'GETDATE()', GETDATE(), CURRENT_TIMESTAMP FROM dbo.orden_pago")
    c = estado.copiar(texto, {'dbo.orden_pago', 'dbo.sp_x'})
    assert c.texto.startswith('-- dbo.orden_pago y GETDATE() en un comentario\nCREATE PROCEDURE estado.sp_x AS')
    assert "'dbo.orden_pago', N'GETDATE()'" in c.texto and c.texto.endswith('FROM estado.orden_pago')
    assert c.cuenta == Counter({'cabecera': 1, 'nombres': 2, 'reloj': 2})
    assert estado.copiar('SELECT * FROM dbo.otra', {'dbo.orden_pago'}).texto == 'SELECT * FROM dbo.otra'
    for malo, motivo in (('SELECT SYSDATETIME()', 'no sabe inyectar'),
                         ("SELECT * FROM OPENQUERY(srv, 'x')", 'servidor enlazado'),
                         ('SELECT * FROM BFN_DIVISAS.dbo.orden_pago', 'tres partes'),
                         ("EXEC sp_addlinkedserver @server = N'x'", 'no se emula')):
        with pytest.raises(NoSeCopia, match=motivo):
            estado.copiar(malo, {'dbo.orden_pago'})


def test_un_correo_se_emula_con_los_mismos_parametros_y_por_posicion_se_niega():
    c = estado.copiar("EXEC msdb.dbo.sp_send_dbmail @recipients = N'a@b', @subject = N'x';", set())
    assert c.texto == "EXEC estado.emulado_sp_send_dbmail @recipients = N'a@b', @subject = N'x';"
    assert c.emulados == {'emulado_sp_send_dbmail': ['@recipients', '@subject']}
    ddl = estado.emulador('estado', 'emulado_sp_send_dbmail', ['@recipients', '@subject'], 'dbo.sp_x')
    assert ddl.startswith('CREATE PROCEDURE estado.emulado_sp_send_dbmail @recipients sql_variant = NULL')
    assert 'INSERT INTO estado.efecto_emulado' in ddl
    with pytest.raises(NoSeCopia, match='por posición'):
        estado.copiar("EXEC msdb.dbo.sp_send_dbmail N'perfil', N'a@b';", set())
    with pytest.raises(NoSeCopia, match='emulador no válido'):
        estado.emulador('estado', 'emulado_x; DROP', [], 'dbo.sp_x')


def test_los_parches_del_tobe_entran_una_sola_vez_en_el_texto_original(modulos, conocidos):
    for e, (viejo, nuevo, _que) in estado.PARCHES.items():
        original = modulos[e].texto
        assert original.count(viejo) == 1
        c = estado.copiar(original, conocidos, parche=(viejo, nuevo))
        assert nuevo.replace('dbo.', 'estado.') in c.texto
    with pytest.raises(NoSeCopia, match='exactamente una vez'):
        estado.copiar('SELECT 1', set(), parche=('no está', 'x'))


def test_el_esquema_de_la_copia_es_el_que_nombran_las_sentencias_literales():
    """Algunas sentencias del arnés van literales (sin armar SQL con texto): tienen que nombrar el mismo esquema."""
    assert estado.ESQUEMA == 'estado'
    assert 'estado.sp_control_con_rollback' in estado_ci.CONTROL_ROLLBACK
    assert all(f'{estado.ESQUEMA}.' in q for q in estado_ci.LLAMADAS_MS.values())


def test_la_copia_de_las_tablas_sale_del_codigo_y_conserva_sus_identidades():
    ddl = estado.ddl_tablas(lotes((codigo.SQL / '02_tablas.sql').read_text(encoding='utf-8')),
                            {f'dbo.{t}' for t in TABLAS})
    assert not any(x.lstrip().upper().startswith('USE') for x in ddl)
    creadas = {m for x in ddl for m in re.findall(r'CREATE TABLE estado\.(\w+)', x)}
    assert creadas == set(TABLAS)
    assert any('REFERENCES estado.moneda' in x for x in ddl) and not any('dbo.' in x for x in ddl)
    assert 'SET IDENTITY_INSERT estado.bitacora ON' in estado.copiar_datos(TABLAS['bitacora'])
    assert 'IDENTITY_INSERT' not in estado.copiar_datos(TABLAS['moneda'])


def test_el_volcado_compara_tambien_los_bytes_de_cada_texto():
    """SQL Server compara 'X' = 'X   ' y sin mayúsculas: la diferencia también se busca en los bytes."""
    q = estado.DESPUES_MS['partida_solicitada']
    assert 'CAST([referencia] AS varbinary(35))' in q and 'EXCEPT' in q and q.count('FROM') == 2
    assert 'CAST([cliente] AS varbinary(240))' in estado.DESPUES_MS['operacion']
    assert 'CAST([usuario] AS varbinary(256))' in estado.ANTES_MS['bitacora']
    t = TABLAS['folio']
    efecto = estado.efecto_de(t, [('FX', 11, None, b'FX')], [('FX', 10, None, b'FX'), ('OP', 5, None, b'OP')])
    assert efecto.despues == {'FX': ('FX', 11, None)} and efecto.borradas == {'OP'}


# ── las entradas: las llamadas reales del guion ─────────────────────────────────────────────────────────────────

def test_el_dia_por_escritor_conserva_el_orden_que_importa(guion):
    """El escenario A corre el día por escritor (operaciones, órdenes, liquidaciones). Eso sólo es válido si ninguna
    liquidación precede al registro de su orden y ningún re-registro sigue a la liquidación de su documento."""
    etapas = estado.llamadas(guion)
    n = Counter(p['accion'] for p in guion['pasos'] if p['fase'] == 'delta')
    assert [len(etapas[k]) for k in ('A1', 'A2', 'A3')] == [n['operacion'], n['orden'], n['liquidacion']]
    assert len(etapas['A0']) == 2 and n['operacion'] == 421
    vistos, liquidados = set(), set()
    for p in (p for p in guion['pasos'] if p['fase'] == 'delta'):
        a = p['args']
        if p['accion'] == 'orden':
            assert a['uetr'] not in liquidados, a['uetr']
            vistos.add(a['uetr'])
        elif p['accion'] == 'liquidacion':
            liquidados.add(a['uetr'])
    assert all(isinstance(x['reloj'], datetime) and x['reloj'].microsecond == 0 for x in etapas['A2'])


def test_la_contingencia_usa_la_primera_orden_nueva_del_dia_y_su_operacion(guion, inv):
    m = estado.alta_manual(guion)
    a = m['orden']['args']
    assert m['orden']['accion'] == 'orden' and not a['reregistro']
    if isinstance(a['operacion_id'], str):
        assert m['operacion']['ref'] == a['operacion_id'] and m['operacion']['accion'] == 'operacion'
    assert estado.noche_del_corte(guion, inv['objetos']) == datetime(2023, 12, 29, 23, 30)


# ── la comparación por llave de negocio ─────────────────────────────────────────────────────────────────────────

def _orden(id_, uetr, estatus, operacion=1):
    return (id_, operacion, 'OP-1', uetr, 'R', datetime(2023, 1, 1), datetime(2023, 1, 1), datetime(2023, 1, 1).date(),
            'BIC', 'NA', 'B', 'C', 'USD', None, 'SHA', None, estatus, None)


def test_la_etapa_se_compara_por_llave_de_negocio_no_por_id():
    """Las dos inserciones llevan id distinto en cada lado (otro orden de inserción) y son la misma orden: (uetr,
    número de registro). Una columna distinta sí es diferencia, con su columna."""
    refs_l = Refs({10: ('u1', 1), 11: ('u2', 1)}, {1: ('FX-1', '0001')})
    refs_t = Refs({10: ('u2', 1), 11: ('u1', 1)}, {1: ('FX-1', '0001')})
    legado = {'orden_pago': Efecto({10: _orden(10, 'u1', 'ENVIADA'), 11: _orden(11, 'u2', 'ENVIADA')})}
    tobe = {'orden_pago': Efecto({10: _orden(10, 'u2', 'ENVIADA'), 11: _orden(11, 'u1', 'ENVIADA')})}
    lado_l, _ = estado.lado_de_etapa({}, legado, {}, refs_l)
    lado_t, _ = estado.lado_de_etapa({}, tobe, {}, refs_t)
    assert estado.comparar(lado_l, lado_t) == []
    tobe['orden_pago'].despues[11] = _orden(11, 'u1', 'LIQUIDADA')
    lado_t, _ = estado.lado_de_etapa({}, tobe, {}, refs_t)
    d = estado.comparar(lado_l, lado_t)
    assert [(x.tabla, x.llave, x.tipo, x.columnas) for x in d] == [('orden_pago', ('u1', 1), 'distinta',
                                                                     ('estatus',))]
    # una fila sólo en un lado
    lado_t.filas['orden_pago'].pop(('u2', 1))
    tipos = Counter(x.tipo for x in estado.comparar(lado_l, lado_t))
    assert tipos == Counter({'distinta': 1, 'sólo en el legado': 1})


def test_la_etapa_es_lo_que_cambio_en_ella_y_el_otro_lado_aporta_su_valor_inicial():
    inicial = {'orden_pago': {5: _orden(5, 'u5', 'ENVIADA')}}
    refs = Refs({5: ('u5', 1)}, {1: ('FX-1', '0001')})
    previo = {'orden_pago': Efecto({5: _orden(5, 'u5', 'LIQUIDADA')})}
    actual = {'orden_pago': Efecto({5: _orden(5, 'u5', 'LIQUIDADA')})}
    lado, tocadas = estado.lado_de_etapa(previo, actual, inicial, refs)
    assert tocadas['orden_pago'] == set() and lado.filas['orden_pago'] == {}      # no cambió EN esta etapa
    # el otro lado la tocó: aquí vale lo acumulado
    lado, _ = estado.lado_de_etapa(previo, actual, inicial, refs, otras={'orden_pago': {5}})
    assert dict(lado.filas['orden_pago'][('u5', 1)])['estatus'] == 'LIQUIDADA'
    lado, _ = estado.lado_de_etapa({}, {}, inicial, refs, otras={'orden_pago': {5}})
    assert dict(lado.filas['orden_pago'][('u5', 1)])['estatus'] == 'ENVIADA'


def test_la_bitacora_es_un_multiconjunto():
    fila = (1, 'orden_pago', 5, 'U', 'ENVIADA', 'VENCIDA', 'sa', datetime(2023, 12, 29, 23, 30))
    otra = (2, *fila[1:])
    refs = Refs({5: ('u5', 1)})
    a, _ = estado.lado_de_etapa({}, {'bitacora': Efecto({1: fila, 2: otra})}, {}, refs)
    b, _ = estado.lado_de_etapa({}, {'bitacora': Efecto({7: fila})}, {}, refs)
    d = estado.comparar(a, b)
    assert len(d) == 1 and d[0].tipo == 'sólo en el legado' and d[0].llave[-1] == 2


# ── árbitros ────────────────────────────────────────────────────────────────────────────────────────────────────

def _dif(legado, tobe, llave=('FX-1', '0001')):
    return Diferencia('operacion', llave, 'distinta', ('estatus',), (('estatus', legado),), (('estatus', tobe),))


def test_el_arbitro_del_1_n_audita_cada_diferencia():
    """r3-T1 sin leer el catálogo: el TO-BE refleja la orden vigente; el legado, otra de sus órdenes."""
    ordenes = {('FX-1', '0001'): [(1, 'REEMPLAZADA'), (2, 'CONCILIADA')]}
    d = [_dif('EN_PROCESO', 'PAGADA')]
    estado.arbitrar_1_n(d, ordenes)
    assert d[0].clase == estado.DEFECTO_LEGADO and 'vigente (2, CONCILIADA)' in d[0].explicacion
    # controles: sin varias órdenes, con un valor que ninguna orden explica, o el TO-BE que no es el de la vigente
    for caso, o in ((_dif('EN_PROCESO', 'PAGADA'), {('FX-1', '0001'): [(2, 'CONCILIADA')]}),
                    (_dif('RECHAZADA', 'PAGADA'), ordenes),
                    (_dif('EN_PROCESO', 'RECHAZADA'), ordenes)):
        estado.arbitrar_1_n([caso], o)
        assert caso.clase == estado.DEFECTO_NUESTRO


def test_el_id_devuelto_se_cruza_con_la_fila_insertada():
    bien = {'n': 1, 'escritor': 'dbo.sp_alta_manual_orden', 'devuelto': 270_617,
            'insertadas': {'orden_pago': [270_617], 'bitacora': [685_277]}}
    assert estado.revisar_identidad(bien, 'orden_pago') is None
    trampa = {**bien, 'devuelto': 685_277}
    r = estado.revisar_identidad(trampa, 'orden_pago')
    assert r['clase'] == estado.DEFECTO_LEGADO and r['el_id_es_de'] == ['bitacora']
    assert 'devolvió 685277 y la fila de orden_pago quedó con 270617' in r['explicacion']
    otro = {**bien, 'devuelto': 9}
    assert estado.revisar_identidad(otro, 'orden_pago')['clase'] == estado.DEFECTO_NUESTRO


def test_la_guarda_de_trancount_y_las_inserciones_por_llamada():
    assert estado.guarda_trancount('dbo.sp_x', 1, 1) is None
    assert '@@TRANCOUNT 1 → 0' in estado.guarda_trancount('dbo.sp_x', 1, 0)
    assert estado.guarda_trancount('dbo.sp_x', 1, 2)
    assert estado.inserciones((10, 20, None, 5, 7), (11, 20, 3, 5, 9)) == {
        'operacion': [11], 'partida_solicitada': [1, 2, 3], 'bitacora': [8, 9]}


def test_la_transaccion_revertida_de_los_veredictos_siempre_revierte():
    class Cursor:
        def __init__(self):
            self.sentencias = []

        def execute(self, sql, *_):
            self.sentencias.append(sql)
    c = Cursor()
    with pytest.raises(RuntimeError), revertida(c):
        c.execute('EXEC dbo.sp_x')
        raise RuntimeError('falló a medias')
    assert c.sentencias == ['BEGIN TRANSACTION', 'EXEC dbo.sp_x', 'IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION']


# ── el TO-BE en PostgreSQL ──────────────────────────────────────────────────────────────────────────────────────

def test_el_tobe_tiene_una_funcion_por_llamada_y_sus_parches():
    funciones = set(re.findall(r'CREATE FUNCTION tobe_estado\.(\w+)\(', TOBE_SQL))
    llamadas = {m for q in estado_ci.LLAMADAS_PG.values() for m in re.findall(r'tobe_estado\.(\w+)\(', q)}
    assert llamadas <= funciones
    assert "estatus <> 'REEMPLAZADA' ORDER BY operacion_id, id DESC" in TOBE_SQL      # r3-T1
    assert 'RETURNING id INTO v_id;\n    RETURN v_id;' in TOBE_SQL                     # r3-T3
    assert 'GETDATE' not in TOBE_SQL.upper() and 'now()' not in TOBE_SQL and 'lastval' not in TOBE_SQL
    assert TOBE_SQL.count("current_setting('decant.reloj')") == 1
    # las constantes del dominio .NET (R02, R05, R10) son las del TO-BE
    dominio = (RAIZ / 'src' / 'Decant.Domain').rglob('*.cs')
    texto = '\n'.join(p.read_text(encoding='utf-8') for p in dominio)
    for constante in ('1.0035m', '0.9965m', '0.0025m', '150.00m', '0.16m', '25.00m', 'DiasDeEspera = 3'):
        assert constante in texto
    for constante in ('1.0035', '0.9965', '0.0025', '150', '0.16', '25.00', "interval '3 days'", 'LIMIT 5000'):
        assert constante in TOBE_SQL


def test_las_llamadas_del_legado_y_del_tobe_piden_los_mismos_argumentos():
    for accion, q in estado_ci.LLAMADAS_PG.items():
        if accion == 'job':
            continue
        legado = set(re.findall(r'%\((\w+)\)s', estado_ci.LLAMADAS_MS[accion])) - {'reloj'}
        assert set(re.findall(r'%\((\w+)\)s', q)) == legado, accion


def test_la_aceptacion_exige_que_falle_con_la_trampa_y_pase_sin_ella():
    cat = trampas.catalogo()
    estado_r = {'escenarios': {}, 'con_parche': {}, 'identidad': {'con_trampa': {}, 'con_parche': {}}}

    def caso(objeto, coincide=True, reloj=False):
        return {'id': f'{objeto} · x', 'objeto': objeto, 'inyectado': {'coincide': coincide},
                'depende_del_reloj': reloj, 'propio': {'coincide': not reloj,
                                                      'conjuntos': [{'solo_legado': 3, 'solo_tobe': 1,
                                                                     'filas_legado': 4, 'filas_tobe': 2}]}}
    oraculo_r = {'reloj_propio': '2023-12-29T18:00:00', 'casos': [caso('dbo.sp_ordenes_por_vencer', reloj=True),
                                                                   caso('dbo.sp_antiguedad_ordenes', False, True)]}
    a = estado_ci.aceptacion(estado_r, oraculo_r, cat)
    filas = {f['trampa']: f for f in a['filas']}
    assert filas['r1-T2']['detectada'] and 'r1-T2' in filas['r1-T2']['falla_con_la_trampa'][0]['nombre'][0]
    assert not filas['r3-T2']['detectada']         # falla con la trampa, pero tampoco pasa con el parche
    assert a['detectadas'] == 1 and 'r3-T2' in a['no_detectadas']
