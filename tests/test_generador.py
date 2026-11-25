"""Generador del legado: determinismo, volumen medido y que cada trampa del catálogo EXISTA en los datos.

Las cifras mínimas no son metas: si una trampa desaparece de los datos (cero filas), la radiografía y la paridad
dejarían de tener qué detectar y estas pruebas lo dirían primero.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal

from legado.generador import Config, generar
from legado.generador.catalogos import digito_clabe
from legado.generador.simulacion import COLUMNAS, _comision, _horas
from legado.generador.zonas import CDMX, local
from radiografia.datos import es_mojibake
from tests.conftest import CHICO

OP = {c: i for i, c in enumerate(COLUMNAS['operacion'])}
OR = {c: i for i, c in enumerate(COLUMNAS['orden_pago'])}


# ── determinismo ─────────────────────────────────────────────────────────────────────────────────────────────

def test_la_misma_semilla_produce_exactamente_los_mismos_datos(datos_chicos):
    assert generar(CHICO).huella() == datos_chicos.huella()


def test_otra_semilla_produce_otros_datos(datos_chicos):
    otra = Config(**{**CHICO.__dict__, 'semilla': CHICO.semilla + 1})
    assert generar(otra).huella() != datos_chicos.huella()


def test_huella_fijada_del_periodo_corto(datos_chicos):
    # Cambia sólo si cambia el generador (o tzdata): entonces se actualiza A PROPÓSITO y se dice en el commit.
    assert datos_chicos.huella() == HUELLA_CHICO


HUELLA_CHICO = 'defe2830211c49ed5f9cde3ea6622a793c7f8e422f11a2d4e1bddb678351f72f'


# ── volumen (medido en legado/VOLUMEN.md) ───────────────────────────────────────────────────────────────────

def test_el_volumen_por_omision_es_el_que_midio_el_control_negativo(datos):
    # Con 250 operaciones/día el reporte mensual salió idéntico en todas las corridas; con 400 ya no.
    assert Config().operaciones_por_dia == 400
    assert len(datos.tablas['operacion']) > 400_000
    assert datos.conteos()['orden_pago'] > 250_000


def test_los_ids_simulados_son_consecutivos_como_los_asignaria_la_identidad(datos):
    for tabla, filas in datos.tablas.items():
        if COLUMNAS[tabla][0] == 'id':
            assert [f[0] for f in filas[:5]] == [1, 2, 3, 4, 5]
            assert filas[-1][0] == len(filas)


# ── T1 · TOP sin ORDER BY con empates ───────────────────────────────────────────────────────────────────────

def test_t1_la_fecha_al_minuto_tiene_empates_reales(datos):
    minutos = Counter(f[OP['fecha_operacion']] for f in datos.tablas['operacion'])
    empatadas = sum(n for n in minutos.values() if n > 1)
    assert empatadas / len(datos.tablas['operacion']) > 0.30
    assert max(minutos.values()) >= 10


def test_t1_el_orden_por_id_no_es_el_orden_por_fecha(datos):
    # el archivo de sucursales se carga a las 22:00 con horas de la mañana: sus ids van después
    ops = datos.tablas['operacion']
    retrocesos = sum(1 for a, b in zip(ops, ops[1:]) if b[OP['fecha_operacion']] < a[OP['fecha_operacion']])
    assert retrocesos > 1000


# ── T2 · INNER JOIN que pierde hijos ────────────────────────────────────────────────────────────────────────

def test_t2_hay_ordenes_vigentes_sin_partidas_del_corresponsal(datos):
    con_partidas = {f[1] for f in datos.tablas['partida_solicitada']}
    vigentes = [f for f in datos.tablas['orden_pago'] if f[OR['estatus']] != 'REEMPLAZADA']
    perdidas = [f for f in vigentes if f[0] not in con_partidas]
    assert len(perdidas) > 1000
    assert {f[OR['estatus']] for f in perdidas} >= {'VENCIDA', 'ENVIADA'}


# ── T3 · centinelas en vez de NULL ──────────────────────────────────────────────────────────────────────────

def test_t3_centinelas_na_y_cero_en_columnas_que_no_usan_null(datos):
    ops, ordenes = datos.tablas['operacion'], datos.tablas['orden_pago']
    assert sum(1 for f in ops if f[OP['cuenta_clabe']] == 'NA') > 10_000
    assert sum(1 for f in ops if f[OP['tipo_cambio_referencia']] == 0) > 10_000
    assert sum(1 for f in ordenes if f[OR['bic_intermediario']] == 'NA') > 10_000
    for columna in ('cuenta_clabe', 'tipo_cambio_referencia'):
        assert all(f[OP[columna]] is not None for f in ops)


def test_t3_las_clabe_reales_traen_digito_de_control_valido(datos):
    for f in datos.tablas['operacion'][:5000]:
        clabe = f[OP['cuenta_clabe']]
        if clabe != 'NA':
            assert len(clabe) == 18 and digito_clabe(clabe[:17]) == clabe[17]


def test_digito_clabe_coincide_con_ejemplos_publicos():
    # ejemplos de CLABE que publica la documentación bancaria (formato real)
    assert digito_clabe('03218000011835971') == '9'
    assert digito_clabe('00201007777777777') == '1'


# ── T4 · lados invertidos en el detalle ─────────────────────────────────────────────────────────────────────

def test_t4_la_tabla_llamada_solicitada_guarda_lo_que_liquido_el_corresponsal(datos):
    solicitada = Counter(f[3] for f in datos.tablas['partida_solicitada'])
    liquidada = Counter(f[3] for f in datos.tablas['partida_liquidada'])
    assert set(solicitada) == {'ABONO', 'COMISION_CORRESPONSAL'}
    assert set(liquidada) == {'PRINCIPAL', 'COMISION', 'IVA', 'GASTOS_OUR'}


def test_t4_la_pantalla_pinta_cada_tabla_en_la_rejilla_del_otro_nombre():
    from legado.pantalla.app import REJILLAS
    sql = open('legado/sql/05_procedimientos.sql', encoding='utf-8').read()
    detalle = sql[sql.index('CREATE OR ALTER PROCEDURE dbo.sp_detalle_operacion'):]
    detalle = detalle[:detalle.index('\nGO')]
    # sp_detalle_operacion: conjunto 1 = partida_solicitada, conjunto 2 = partida_liquidada
    assert detalle.index('dbo.partida_solicitada') < detalle.index('dbo.partida_liquidada')
    conjunto = {r['titulo']: r['conjunto'] for r in REJILLAS}
    assert conjunto['Liquidado por el corresponsal'] == 1
    assert conjunto['Solicitado por el cliente'] == 2


# ── T5 · horario de verano ──────────────────────────────────────────────────────────────────────────────────

def test_t5_hay_operaciones_en_la_hora_que_se_repite_al_terminar_el_horario_de_verano(datos):
    for dia in (date(2021, 10, 31), date(2022, 10, 30)):
        segunda_vuelta = [op for op in datos.operaciones if op.id and local(op.insercion).date() == dia
                          and op.insercion.astimezone(CDMX).fold == 1]
        assert segunda_vuelta, f'sin operaciones en la 1:00–1:59 repetida del {dia}'


def test_t5_el_legado_cuenta_una_hora_de_mas_cuando_nueva_york_ya_cambio_y_mexico_no(datos):
    errores = Counter()
    for d in datos.documentos:
        fila = d.filas[-1] if d.filas else None
        if fila is None or fila[OR['horas_liquidacion']] is None:
            continue
        real = (d.t_liquidacion - d.t_envio).total_seconds() / 3600
        errores[round(float(fila[OR['horas_liquidacion']]) - real)] += 1
    assert errores[0] > 10_000 and errores[1] > 10_000
    assert set(errores) == {0, 1}


def test_horas_de_liquidacion_con_la_formula_del_procedimiento():
    # sp_conciliar: DATEDIFF(minute, fecha_envio, DATEADD(hour, -1, ultima)) / 60.0
    # 15-mar-2023: Nueva York ya está en verano (UTC-4) y México ya no tiene (UTC-6): la diferencia real es 2 h.
    envio = datetime(2023, 3, 15, 10, 0, 30)          # hora local de la Ciudad de México
    liquidacion_ny = datetime(2023, 3, 15, 13, 0, 0)  # hora local de Nueva York = 11:00 en México
    assert _horas(envio, liquidacion_ny) == Decimal('2.00')   # el legado dice 2 h; en realidad fue 1 h


# ── T6 · columna que nadie imprime ──────────────────────────────────────────────────────────────────────────

def test_t6_codigo_de_proposito_tiene_datos_reales(datos):
    ordenes = datos.tablas['orden_pago']
    con_valor = [f[OR['codigo_proposito']] for f in ordenes if f[OR['codigo_proposito']] is not None]
    assert len(con_valor) / len(ordenes) > 0.9
    assert set(con_valor) <= {'SUPP', 'GDDS', 'SCVE', 'TRAD', 'INTC', 'EDUC', 'MDCS', 'SALA'}


# ── T7 · acentos latin-1 en columnas Unicode ────────────────────────────────────────────────────────────────

def test_t7_hay_nombres_danados_y_nombres_sanos(datos):
    clientes = [f[OP['cliente']] for f in datos.tablas['operacion']]
    danados = [c for c in clientes if es_mojibake(c)]
    assert len(danados) > 10_000
    assert any('Í' in c or 'É' in c for c in clientes)          # acentos bien escritos


def test_t7_hay_beneficiarios_con_letras_fuera_de_latin1(datos):
    fuera = [f for f in datos.tablas['orden_pago'] if any(ord(ch) > 255 for ch in f[OR['beneficiario']])]
    assert len(fuera) > 1000


# ── T8 · GETDATE() dentro de una regla ──────────────────────────────────────────────────────────────────────

def test_t8_hay_ordenes_pendientes_que_un_reproceso_con_el_reloj_de_hoy_venceria(datos):
    ordenes = datos.tablas['orden_pago']
    estatus = Counter(f[OR['estatus']] for f in ordenes)
    assert estatus['VENCIDA'] > 1000
    respaldo = local(datos.config.respaldo)
    recientes = [f for f in ordenes if f[OR['estatus']] == 'ENVIADA'
                 and (respaldo - f[OR['fecha_envio']]).days < 3]
    assert recientes      # el job de esa noche no las vencía; correrlo hoy (GETDATE() de 2026) sí


# ── T9 · re-registro ────────────────────────────────────────────────────────────────────────────────────────

def test_t9_el_mismo_documento_se_registra_con_otra_llave_cada_manana(datos):
    por_uetr: dict[str, list[tuple]] = {}
    for f in datos.tablas['orden_pago']:
        por_uetr.setdefault(f[OR['uetr']], []).append(f)
    repetidos = [filas for filas in por_uetr.values() if len(filas) > 1]
    assert len(repetidos) > 10_000
    for filas in repetidos[:2000]:
        assert [f[0] for f in filas] == sorted(f[0] for f in filas)
        assert [f[OR['fecha_registro']] for f in filas] == sorted(f[OR['fecha_registro']] for f in filas)
        assert all(f[OR['estatus']] == 'REEMPLAZADA' for f in filas[:-1])
        assert filas[-1][OR['estatus']] != 'REEMPLAZADA'
        assert len({f[OR['folio']] for f in filas}) == 1


def test_t9_el_delta_del_dia_trae_re_registros_que_un_tope_de_ayer_perderia(datos):
    reregistros = [p for p in datos.pasos if p['accion'] == 'orden' and p['args']['reregistro']]
    assert len(reregistros) > 50
    assert all(p['args']['fecha_registro'].startswith(datos.config.fecha_respaldo.isoformat()) for p in reregistros)


# ── defectos adicionales (decisión de negocio en S2) ────────────────────────────────────────────────────────

def test_d1_la_comision_se_trunca_en_lugar_de_redondear():
    # ROUND(@monto_mxn * 0.0025, 2, 1): 100,003.99 × 0.0025 = 250.009975 → 250.00 (redondeando serían 250.01)
    assert _comision(Decimal('100003.99')) == Decimal('250.00')
    assert _comision(Decimal('1000.00')) == Decimal('150.00')       # mínimo


def test_d2_ordenes_en_yenes_con_centavos_salen_en_diferencia(datos):
    jpy = [f for f in datos.tablas['orden_pago'] if f[OR['moneda']] == 'JPY' and f[OR['estatus']] != 'REEMPLAZADA']
    con_centavos = [f for f in jpy if f[OR['monto']] != f[OR['monto']].to_integral_value()]
    assert len(con_centavos) / len(jpy) > 0.9
    assert Counter(f[OR['estatus']] for f in con_centavos)['DIFERENCIA'] > 1000


def test_d3_liquidaciones_que_llegaron_despues_del_vencimiento_se_pierden(datos):
    descartadas = [d for d in datos.documentos if d.t_liquidacion is not None and not d.aceptada
                   and d.t_liquidacion < datos.config.respaldo]
    assert len(descartadas) > 1000
    con_partidas = {f[1] for f in datos.tablas['partida_solicitada']}
    assert all(d.filas[-1][0] not in con_partidas for d in descartadas[:500])


# ── legado vivo: el guion del mismo día ─────────────────────────────────────────────────────────────────────

def test_el_delta_trae_operaciones_catalogo_y_escrituras_despues_del_congelamiento(datos):
    acciones = Counter((p['fase'], p['accion']) for p in datos.pasos)
    assert acciones[('delta', 'operacion')] > 100
    assert acciones[('delta', 'liquidacion')] > 50
    assert acciones[('delta', 'alta_moneda')] == 1 and acciones[('delta', 'baja_moneda')] == 1
    assert acciones[('posterior_congelamiento', 'operacion')] > 0
    instantes = [p['instante_utc'] for p in datos.pasos]
    assert instantes == sorted(instantes)
