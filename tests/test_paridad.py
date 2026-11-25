"""Paridad sin base: la separación universo/oráculo por columna, el mapeo y sus parches, la comparación de esquema
(con su control negativo de T6), el arbitraje, el cuadre por lado y el binding de la pantalla (T4)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from legado.generador import zonas as generador_zonas
from legado.generador.simulacion import COLUMNAS
from paridad import arbitraje, binding, esquema, mapeo, migracion, motor, oraculo, reporte, universo
from paridad import zonas as paridad_zonas
from universo.particion import PARTICION

RAIZ = Path(__file__).resolve().parent.parent


def _columnas_de_la_consulta(sql: str) -> list[str]:
    lista = re.search(r'SELECT (.*?) FROM', sql, re.S).group(1)
    return [c.strip().split(' ')[-1] if ' END' not in c else 'tipo_cambio' for c in lista.split(',')]


# ── universo y oráculo: por columna, en archivos y funciones distintos ───────────────────────────────────────

@pytest.mark.parametrize('tabla', sorted(universo.CONSULTAS))
def test_el_universo_pide_exactamente_llaves_internas_entradas_y_la_parte_de_entrada_de_las_mixtas(tabla):
    sql, columnas = universo.CONSULTAS[tabla]
    assert _columnas_de_la_consulta(sql) == columnas
    particion = PARTICION[tabla]
    esperadas = set(particion.get('llave_interna', {})) | set(particion.get('entrada', {})) | set(
        particion.get('mixta', {}))
    assert set(columnas) == esperadas
    assert not set(columnas) & set(particion.get('resultado', {}))


@pytest.mark.parametrize('tabla', sorted(oraculo.CONSULTAS))
def test_el_oraculo_pide_resultados_y_solo_la_llave_para_juntarlos(tabla):
    sql, columnas = oraculo.CONSULTAS[tabla]
    assert _columnas_de_la_consulta(sql) == columnas
    particion = PARTICION[tabla]
    resultados = set(particion.get('resultado', {})) | set(particion.get('mixta', {}))
    llave = {'id'} if 'id' in particion.get('llave_interna', {}) else {'serie'}
    assert set(columnas) == resultados | llave


def test_ninguna_tabla_queda_sin_lugar_entre_universo_oraculo_y_retencion():
    for tabla in PARTICION:
        assert tabla in universo.CONSULTAS or tabla in universo.SIN_ENTRADAS
        assert tabla in oraculo.CONSULTAS or tabla in oraculo.NO_SE_EXTRAEN or 'resultado' not in PARTICION[tabla]


# ── mapeo y parches ──────────────────────────────────────────────────────────────────────────────────────────

def test_el_mapeo_es_valido_y_cubre_cada_columna_del_legado():
    assert mapeo.validar() == []
    for tabla, columnas in COLUMNAS.items():
        assert set(mapeo.MAPEO[f'dbo.{tabla}'].columnas) == set(columnas), tabla


def test_parches_t3_centinelas():
    assert mapeo.aplicar(('char:11', 'T3_texto'), 'NA         ') is None
    assert mapeo.aplicar(('T3_texto',), '987320396284801163') == '987320396284801163'
    assert mapeo.aplicar(('T3_numero',), Decimal('0.000000')) is None
    assert mapeo.aplicar(('T3_numero',), Decimal('19.859734')) == Decimal('19.859734')


# ── parches EXACTOS: sólo el predicado del hallazgo; un defecto distinto sigue siendo diferencia ─────────────────

_REF = 'FICT220667399219'
_EN_VENTANA = {'fecha_hora': datetime(2022, 9, 1, 9, 30)}


def test_todas_las_listas_de_parches_del_codigo_son_validas():
    """Regresión (primera corrida de la retro): motor.py seguía con ('char',) sin ancho y la paridad completa cayó
    a los 15 minutos. Cada lista de parches del código se valida aquí, en el job de pruebas normal."""
    from paridad import gemelos
    listas = [p for _, _, p in migracion.COL_OPERACION + migracion.COL_ORDEN + migracion.COL_PARTIDA_CORRESPONSAL
              + migracion.COL_PARTIDA_CLIENTE]
    listas += [p for _, p in motor.PARTIDA_CLIENTE + motor.PARTIDA_CORRESPONSAL]
    listas += [r for _, r in list(gemelos.CAMPOS.values()) + list(gemelos.PARTIDA.values()) if isinstance(r, tuple)]
    listas += [c.parches for t in mapeo.MAPEO.values() for c in t.columnas.values()]
    invalidos = [p for lista in listas for p in lista if not mapeo.parche_valido(p)]
    assert invalidos == [] and len(listas) > 40
    assert not mapeo.parche_valido('char') and mapeo.parche_valido('char:3')


def test_r06_pasa_la_fecha_de_la_partida_a_ciega1_t3():
    """Sin la fecha de su renglón, ciega1_T3 no aplica y R06 marcaría 48 mil referencias como defecto."""
    columnas = dict(motor.PARTIDA_CORRESPONSAL)
    assert mapeo.aplicar(columnas['referencia'], _REF.ljust(35), fila=_EN_VENTANA) == _REF


def test_ciega1_t3_quita_el_relleno_de_ancho_fijo_dentro_de_la_ventana():
    assert mapeo.aplicar(('ciega1_T3',), _REF.ljust(35), fila=_EN_VENTANA) == _REF


@pytest.mark.parametrize('valor, fila, por_que', [
    (_REF.ljust(35), {'fecha_hora': datetime(2023, 3, 1, 9, 30)}, 'relleno fuera de la ventana'),
    ((_REF + '\t').ljust(35), _EN_VENTANA, 'tabulador antes del relleno'),
    (_REF + '   ', _EN_VENTANA, 'relleno que no llega al ancho fijo'),
    (_REF.ljust(36), _EN_VENTANA, 'más ancho que la interfaz'),
])
def test_ciega1_t3_no_absuelve_un_defecto_distinto(valor, fila, por_que):
    assert mapeo.aplicar(('ciega1_T3',), valor, fila=fila) == valor, por_que


def test_char_sólo_quita_el_relleno_del_tipo():
    assert mapeo.aplicar(('char:11', 'T3_texto'), 'NA'.ljust(11)) is None
    assert mapeo.aplicar(('char:11',), 'FICTUS33XXX') == 'FICTUS33XXX'
    assert mapeo.aplicar(('char:11', 'T3_texto'), 'NA ') == 'NA '            # no llena el ancho: no es del tipo
    assert mapeo.aplicar(('char:11', 'T3_texto'), 'NA\t'.ljust(11)) == 'NA\t'.ljust(11)   # intacto
    with pytest.raises(KeyError):
        mapeo.aplicar(('char',), 'X')                                        # el ancho es obligatorio


def test_los_centinelas_son_exactos():
    assert mapeo.aplicar(('T3_texto',), 'NA') is None
    for distinto in ('N/A', 'na', 'NA '):
        assert mapeo.aplicar(('T3_texto',), distinto) == distinto
    assert mapeo.aplicar(('T3_numero',), Decimal('0.000001')) == Decimal('0.000001')


def test_el_control_negativo_inyecta_otros_defectos_y_todos_fallan():
    c = migracion.Comparacion('prueba', 'llave')
    legado = {('u', 1): {'referencia': _REF.ljust(35), **_EN_VENTANA}}
    tobe = {('u', 1): {'referencia': _REF}}
    migracion._cruzar(c, legado, tobe, [('referencia', 'referencia', ('ciega1_T3',))])
    resumen = c.resumen()
    assert resumen['parches'] == {'ciega1_T3 → referencia': 1}
    assert len(resumen['controles_negativos']) == 4 and all(x['falla'] for x in resumen['controles_negativos'])


def test_lo_aplicado_debe_ser_igual_a_lo_medido_en_el_origen():
    c = migracion.Comparacion('prueba', 'llave')
    migracion._cruzar(c, {('u', 1): {'referencia': _REF.ljust(35), **_EN_VENTANA}}, {('u', 1): {'referencia': _REF}},
                      [('referencia', 'referencia', ('ciega1_T3',))])
    c.medidos = {'ciega1_T3 → referencia': 2}            # el origen dice 2: el parche aplicó 1
    assert not c.resumen()['cuadra'] and c.resumen()['parches_sin_cuadrar']


# ── la paridad no comparte código con la fuente de la verdad, pero debe dar lo mismo ─────────────────────────

def _horas_de_dias(dias: list[date]):
    for dia in dias:
        for minuto in range(0, 24 * 60, 10):
            yield datetime(dia.year, dia.month, dia.day) + timedelta(minutes=minuto)


@pytest.mark.parametrize('zona_paridad, zona_generador', [
    (paridad_zonas.CDMX, generador_zonas.CDMX), (paridad_zonas.NUEVA_YORK, generador_zonas.NUEVA_YORK)])
def test_la_conversion_de_la_paridad_coincide_con_la_del_generador_en_los_cambios_de_horario(zona_paridad,
                                                                                             zona_generador):
    cambios = [date(2021, 3, 14), date(2021, 4, 4), date(2021, 10, 31), date(2021, 11, 7), date(2022, 3, 13),
               date(2022, 4, 3), date(2022, 10, 30), date(2022, 11, 6), date(2023, 3, 12), date(2023, 11, 5)]
    revisadas = repetidas = 0
    for hora in _horas_de_dias(cambios):
        revisadas += 1
        assert paridad_zonas.a_utc(hora, zona_paridad) == generador_zonas.a_utc(hora, zona_generador), hora
        if paridad_zonas.es_ambigua(hora, zona_paridad):
            repetidas += 1
            assert paridad_zonas.a_utc(hora, zona_paridad, 1) == \
                hora.replace(tzinfo=zona_generador, fold=1).astimezone(timezone.utc), hora
    assert revisadas == 1440 and repetidas >= 6        # al menos una hora repetida al año, de 10 en 10 minutos


def test_parche_t5_convierte_la_hora_local_de_cada_zona():
    utc = timezone.utc
    assert mapeo.aplicar(('T5_cdmx',), datetime(2023, 12, 1, 10, 0)) == datetime(2023, 12, 1, 16, 0, tzinfo=utc)
    assert mapeo.aplicar(('T5_ny',), datetime(2023, 6, 1, 8, 2)) == datetime(2023, 6, 1, 12, 2, tzinfo=timezone.utc)


def test_en_la_hora_repetida_decide_el_orden_de_llegada_caso_real_de_r04():
    # orden_pago.id 68199 (01:41:59, primera vuelta) y 68200 (01:19:50, llegó después: segunda vuelta)
    filas = [{'id': 68199, 'uetr': 'e0a842db', 'fecha_registro': datetime(2021, 10, 31, 1, 41, 59)},
             {'id': 68200, 'uetr': '8cc57b58', 'fecha_registro': datetime(2021, 10, 31, 1, 19, 50)}]
    pisos = mapeo.pisos_por_llegada(filas)
    assert pisos[68199][1] == datetime(2021, 10, 31, 6, 41, 59, tzinfo=timezone.utc)
    assert pisos[68200][1] == datetime(2021, 10, 31, 7, 19, 50, tzinfo=timezone.utc)


def test_el_envio_se_ancla_al_primer_registro_del_documento_caso_real():
    # 3f4abf43…: alta el 30-oct-2022 01:30:27 (primera vuelta) y re-registro el 31 a las 07:01:32
    filas = [{'id': 159429, 'uetr': '3f4abf43', 'fecha_registro': datetime(2022, 10, 30, 1, 30, 27)},
             {'id': 159548, 'uetr': '3f4abf43', 'fecha_registro': datetime(2022, 10, 31, 7, 1, 32)}]
    pisos = mapeo.pisos_por_llegada(filas)
    envio = mapeo.aplicar(('T5_cdmx_llegada',), datetime(2022, 10, 30, 1, 30, 59), pisos[159548][2])
    assert envio == datetime(2022, 10, 30, 6, 30, 59, tzinfo=timezone.utc)


# ── esquema ──────────────────────────────────────────────────────────────────────────────────────────────────

def _esquemas():
    legado = {'dbo.orden_pago.codigo_proposito': {'tipo': 'char', 'largo': 4, 'precision': 0, 'escala': 0,
                                                  'nulable': True},
              'dbo.orden_pago.monto': {'tipo': 'decimal', 'largo': 9, 'precision': 18, 'escala': 2, 'nulable': False}}
    tobe = {'decant.orden_pago.codigo_proposito': {'tipo': 'character varying', 'largo': 4, 'precision': None,
                                                   'escala': None, 'nulable': True},
            'decant.orden_pago.monto': {'tipo': 'numeric', 'largo': None, 'precision': 18, 'escala': 2,
                                        'nulable': False}}
    return legado, tobe


def test_el_esquema_compatible_no_tiene_errores_de_columna():
    legado, tobe = _esquemas()
    errores = [e for e in esquema.comparar(legado, tobe)['errores'] if 'no está en el respaldo' not in e]
    assert errores == []


def test_control_negativo_t6_perder_codigo_proposito_falla_y_lo_nombra():
    legado, tobe = _esquemas()
    assert esquema.control_negativo_t6(legado, tobe)['caza_t6']


def test_el_esquema_caza_precision_distinta_nulos_y_columnas_sin_origen():
    legado, tobe = _esquemas()
    tobe['decant.orden_pago.monto'] = {**tobe['decant.orden_pago.monto'], 'escala': 4}
    tobe['decant.orden_pago.codigo_proposito'] = {**tobe['decant.orden_pago.codigo_proposito'], 'nulable': False}
    tobe['decant.orden_pago.columna_huerfana'] = {'tipo': 'integer', 'largo': None, 'precision': 32, 'escala': 0,
                                                  'nulable': True}
    errores = ' | '.join(esquema.comparar(legado, tobe)['errores'])
    assert 'decimal(18,2) → numeric(18,4)' in errores
    assert 'no admite NULL' in errores
    assert 'columna_huerfana' in errores


# ── arbitraje ────────────────────────────────────────────────────────────────────────────────────────────────

def _arbitro(categoria, auditoria_ok):
    return arbitraje.Arbitro('a', categoria, 'ADR', 'explicación', aplica=lambda d: d.regla == 'R',
                             audita=lambda d: (auditoria_ok, 'medido'))


def test_cada_diferencia_cae_en_una_categoria_y_sin_arbitro_es_defecto_nuestro():
    difs = [arbitraje.Diferencia('R', '1', 'a', 'b'), arbitraje.Diferencia('X', '2', 'a', 'b')]
    r = arbitraje.arbitrar(difs, [_arbitro(arbitraje.DISCREPANCIA, True)])
    assert r['por_categoria'][arbitraje.DISCREPANCIA] == 1 and r['por_categoria'][arbitraje.DEFECTO] == 1


def test_un_arbitro_que_no_pasa_su_auditoria_no_absuelve():
    r = arbitraje.arbitrar([arbitraje.Diferencia('R', '1', 'a', 'b')], [_arbitro(arbitraje.AVANCE, False)])
    assert r['por_categoria'][arbitraje.DEFECTO] == 1 and r['por_arbitro']['a']['auditoria_fallida'] == 1


# ── R08 / T5: la réplica y la corrección como hipótesis ──────────────────────────────────────────────────────

@pytest.mark.parametrize('envio, ultima, legado', [
    (datetime(2023, 12, 1, 0, 22, 41), datetime(2023, 12, 1, 10, 8, 5), '8.77'),    # 2da9c50b…
    (datetime(2023, 6, 1, 0, 39, 53), datetime(2023, 6, 1, 8, 30, 42), '6.85'),     # 469818d6…
    (datetime(2022, 3, 20, 5, 55, 9), datetime(2022, 3, 21, 8, 50, 6), '25.92'),    # 274cab37…
])
def test_la_formula_del_legado_sobre_columnas_crudas_da_lo_que_el_legado_guardo(envio, ultima, legado):
    assert motor.horas_fijas_del_legado(envio, ultima) == Decimal(legado)


def _fila_r08(id_, envio, ultima, legado):
    return id_, f'u{id_}', envio, Decimal(legado), ultima


def test_la_auditoria_de_t5_prueba_los_dos_sentidos_y_desglosa_por_ventana():
    desfase = {'u1': timedelta(hours=-5), 'u2': timedelta(hours=-4), 'u3': timedelta(hours=-4)}
    filas = [_fila_r08(1, datetime(2023, 12, 1, 0, 22, 41), datetime(2023, 12, 1, 10, 8, 5), '8.77'),
             _fila_r08(2, datetime(2023, 6, 1, 0, 39, 53), datetime(2023, 6, 1, 8, 30, 42), '6.85'),
             _fila_r08(3, datetime(2022, 3, 20, 5, 55, 9), datetime(2022, 3, 21, 8, 50, 6), '25.92')]
    r = motor.hipotesis_r08(filas, desfase, {1: (None, None, None), 2: (None, None, None), 3: (None, None, None)})
    fija, instantes = r['hipotesis']
    assert (fija['coinciden'], instantes['coinciden']) == (3, 1)
    a = r['auditoria']
    assert a['violaciones'] == 0 and a['diferencias'] == a['suma_de_ventanas'] == 2
    assert a['conteos']['extra = 0 y el legado coincide'] == 1
    assert set(a['ventanas']) == {'2023 (12-mar a 5-nov): Nueva York en horario de verano, México ya sin él',
                                  'primavera 2022: Nueva York ya en horario de verano, México todavía no'}


def test_la_auditoria_de_t5_detecta_una_diferencia_sin_desfase_extra():
    """El sentido inverso: en diciembre de 2023 no hay desfase extra; si el legado difiere, es violación."""
    filas = [_fila_r08(1, datetime(2023, 12, 1, 0, 22, 41), datetime(2023, 12, 1, 10, 8, 5), '9.77')]
    r = motor.hipotesis_r08(filas, {'u1': timedelta(hours=-5)}, {1: (None, None, None)})
    assert r['auditoria']['violaciones'] == 1


def test_la_regla_de_hora_local_sin_zona_audita_el_desfase():
    assert reporte._local('2023-12-01T10:15:00-06:00', reporte.ZONA_DE['fecha_envio']) == ('2023-12-01 10:15:00', True)
    assert reporte._local('2023-12-01T10:15:00-05:00', reporte.ZONA_DE['fecha_envio'])[1] is False


# ── cuadre por lado ──────────────────────────────────────────────────────────────────────────────────────────

def test_el_cuadre_por_lado_caza_una_lista_cruzada_y_un_desglose_en_cero():
    bien = [('u1', Decimal('100'), 'CONCILIADA', Decimal('100'), 3, Decimal('100'), 2),
            ('u2', Decimal('50'), 'VENCIDA', Decimal('50'), 3, None, 0)]
    assert migracion.evaluar_cuadre(bien)['cuadra']
    cruzada = [('u1', Decimal('100'), 'CONCILIADA', None, 2, Decimal('100'), 3)]
    assert migracion.evaluar_cuadre(cruzada)['documentos_con_violacion'] == 2
    en_cero = [('u1', Decimal('100'), 'CONCILIADA', Decimal('0'), 3, Decimal('100'), 2)]
    assert not migracion.evaluar_cuadre(en_cero)['cuadra']


# ── T4: el binding de la pantalla manda, no el nombre de la tabla ────────────────────────────────────────────

def test_el_binding_se_lee_del_codigo_de_la_pantalla():
    rejillas = {r['titulo']: r['conjunto'] for r in binding.rejillas()}
    assert rejillas == {'Liquidado por el corresponsal': 1, 'Solicitado por el cliente': 2}


def test_el_tobe_nombra_sus_listas_como_las_rejillas_que_ve_el_usuario():
    """El contrato del TO-BE (Presentacion.cs) debe tener un campo por rejilla, con el título de la rejilla."""
    codigo = (RAIZ / 'src' / 'Decant.Api' / 'Presentacion.cs').read_text(encoding='utf-8')
    detalle = re.search(r'record Detalle\((.*?)\);', codigo, re.S).group(1)
    propiedades = {p.split()[-1] for p in detalle.replace('\n', ' ').split(',')}
    for r in binding.rejillas():
        campo = binding.campo_json(r['titulo'])
        assert campo[0].upper() + campo[1:] in propiedades, campo


# ── piso del orden: el control negativo con el plan variado ──────────────────────────────────────────────────

class _CursorDelLegado:
    """Doble del cursor del legado: cada llamada al procedimiento devuelve la siguiente corrida."""

    def __init__(self, corridas):
        self._corridas = iter(corridas)
        self.preparaciones: list[str] = []
        self.description = None

    def execute(self, sentencia):
        self.preparaciones.append(sentencia)
        self.description = None

    def callproc(self, _nombre, _parametros):
        self._filas = next(self._corridas)
        self.description = [('uetr',), ('concepto',), ('fecha_valor',)]

    def fetchall(self):
        return self._filas

    def nextset(self):
        return False


def test_el_piso_no_se_conforma_con_una_corrida_que_reproduce_el_orden(tmp_path):
    """Regresión (clon limpio del 24-nov): una sola re-corrida reprodujo el orden publicado (0 %) y la paridad tomó
    los empates como contrato. El piso se mide con el plan variado y se queda con el mayor."""
    publicado = [['a', 'ABONO', '2023-12-01'], ['b', 'ABONO', '2023-12-01'], ['c', 'ABONO', '2023-12-02']]
    from paridad import formato
    formato.escribir(tmp_path / 'p.jsonl', ['uetr', 'concepto', 'fecha_valor'], publicado)
    invertido = [publicado[1], publicado[0], publicado[2]]
    cursor = _CursorDelLegado([publicado, invertido, publicado])
    cursor.description_columnas = ['uetr', 'concepto', 'fecha_valor']
    salida = {'archivo': 'p.jsonl', 'procedimiento': 'dbo.sp_reporte_ordenes', 'parametros': [], 'conjunto': 0,
              'llave_orden': ['fecha_valor']}
    piso = reporte.piso(cursor, salida, tmp_path)
    assert [m['pct_empatados_invertidos'] for m in piso['muestras']] == [0.0, 100.0, 0.0]
    assert piso['pct_empatados_invertidos'] == 100.0 and piso['inversiones_contrato'] == 0
    assert any('DBCC FREEPROCCACHE' in s for s in cursor.preparaciones)


# ── control negativo del comparador del reporte: mutantes que DEBEN fallar (fixture chico, sin base) ──────────

_COLUMNAS_REPORTE = ['folio', 'uetr', 'referencia_mt103', 'fecha_envio', 'fecha_valor', 'bic_corresponsal',
                     'beneficiario', 'moneda', 'monto', 'gastos', 'estatus', 'concepto', 'monto_partida',
                     'fecha_partida']


def _renglon(n: int, fecha_valor: str, envio_local: str, partida_local: str, monto: str) -> tuple[list, list]:
    uetr = f'3edcbeae-c21e-40f1-b309-430eca67e1{n:02d}'
    comun = [f'OP-0000000{n:02d}', uetr, f'BFN2312010000{n:02d}']
    legado = comun[:] + [envio_local, fecha_valor, 'FICTUS33XXX', 'Great Plains Seed Co.', 'USD', '1000.00', 'SHA',
                         'CONCILIADA', 'ABONO', monto, partida_local]
    tobe = comun[:] + [envio_local.replace(' ', 'T') + '-06:00', fecha_valor, 'FICTUS33XXX', 'Great Plains Seed Co.',
                       'USD', '1000.00', 'SHA', 'CONCILIADA', 'ABONO', monto,
                       partida_local.replace(' ', 'T') + '-05:00']
    return legado, tobe


class _LegadoVivoSinNada:
    """Doble del legado vivo: no tiene ninguna partida posterior al corte."""

    def cursor(self):
        return self

    def execute(self, *_):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


def _reporte_chico(tmp_path):
    from paridad import formato
    pares = [_renglon(1, '2023-12-01', '2023-12-01 10:05:30', '2023-12-01 12:15:42', '988.50'),
             _renglon(2, '2023-12-01', '2023-12-01 10:06:00', '2023-12-01 12:20:00', '1000.00'),
             _renglon(3, '2023-12-04', '2023-12-04 09:00:00', '2023-12-04 11:00:00', '500.25'),
             _renglon(4, '2023-12-04', '2023-12-04 09:30:00', '2023-12-04 11:30:00', '250.00')]
    formato.escribir(tmp_path / 'publicado.jsonl', _COLUMNAS_REPORTE, [p[0] for p in pares])
    formato.escribir(tmp_path / 'tobe.jsonl', _COLUMNAS_REPORTE, [p[1] for p in pares])
    publicada = {'archivo': 'publicado.jsonl', 'sha256': '0' * 64}
    corte = {'instante_utc': '2023-12-29T09:44:36+00:00', 'tablas': {'dbo.partida_solicitada': {'max_id': 100}}}
    return publicada, corte, {'pct_empatados_invertidos': 10.0}


def test_el_reporte_chico_sin_mutar_cumple(tmp_path):
    publicada, corte, piso = _reporte_chico(tmp_path)
    r = reporte.comparar(publicada, tmp_path, tmp_path / 'tobe.jsonl', piso, corte, _LegadoVivoSinNada(), {})
    assert r['cumple'] and r['arbitraje']['por_categoria'][arbitraje.REGLA] == 8   # 4 renglones × 2 horas


def test_cada_mutante_del_reporte_falla_como_debe(tmp_path):
    publicada, corte, piso = _reporte_chico(tmp_path)
    resultados = reporte.mutantes(publicada, tmp_path, tmp_path / 'tobe.jsonl', piso, corte, _LegadoVivoSinNada(), {},
                                  tmp_path / 'mutantes')
    assert len(resultados) == 6
    fallan = {m['mutante']: m['falla_como_debe'] for m in resultados}
    assert all(fallan.values()), fallan
    hora = next(m for m in resultados if m['mutante'].startswith('una hora corrida'))
    assert hora['defectos'] == 1               # «hora local sin zona» absorbe 8 celdas, pero no ésta


def test_el_punto_ciego_cuenta_las_celdas_de_la_hora_repetida(tmp_path):
    from paridad import formato
    legado, tobe = _renglon(1, '2022-10-31', '2022-10-30 01:30:00', '2022-11-06 01:30:00', '1.00')
    formato.escribir(tmp_path / 'publicado.jsonl', _COLUMNAS_REPORTE, [legado])
    formato.escribir(tmp_path / 'tobe.jsonl', _COLUMNAS_REPORTE, [tobe])
    r = reporte.comparar({'archivo': 'publicado.jsonl', 'sha256': ''}, tmp_path, tmp_path / 'tobe.jsonl',
                         {'pct_empatados_invertidos': 1.0}, {'instante_utc': '2023-12-29T09:44:36+00:00',
                                                             'tablas': {'dbo.partida_solicitada': {'max_id': 1}}},
                         None, {})
    assert r['punto_ciego']['celdas_en_hora_repetida'] == 2   # 01:30 del 30-oct (CDMX) y del 6-nov (NY)


def _raiz_falsa(tmp_path: Path) -> Path:
    from paridad import tobe
    for fuente in tobe.FUENTES_DE_LAS_CARGAS:
        ruta = tmp_path / fuente
        if '.' in ruta.name:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text('uno', encoding='utf-8')
        else:
            ruta.mkdir(parents=True, exist_ok=True)
            (ruta / 'a.cs').write_text('uno', encoding='utf-8')
    (tmp_path / 'respaldo.json').write_text('{}', encoding='utf-8')
    return tmp_path


def test_la_llave_de_las_cargas_cambia_con_el_codigo_y_no_con_lo_compilado(tmp_path):
    from paridad import tobe
    raiz = _raiz_falsa(tmp_path)
    manifiesto = raiz / 'respaldo.json'
    llave = tobe.llave_de_cargas(manifiesto, raiz)
    (raiz / 'src' / 'bin').mkdir()
    (raiz / 'src' / 'bin' / 'decant.dll').write_bytes(b'compilado')
    assert tobe.llave_de_cargas(manifiesto, raiz) == llave            # bin/obj no son código
    (raiz / 'src' / 'a.cs').write_text('dos', encoding='utf-8')
    assert tobe.llave_de_cargas(manifiesto, raiz) != llave            # un cambio en el TO-BE sí
    (raiz / 'src' / 'a.cs').write_text('uno', encoding='utf-8')
    manifiesto.write_text('{"otro": 1}', encoding='utf-8')
    assert tobe.llave_de_cargas(manifiesto, raiz) != llave            # otro respaldo también


def test_reusar_cargas_exige_la_llave_del_mismo_codigo(tmp_path):
    from paridad import tobe
    with pytest.raises(SystemExit, match='sin llave'):
        tobe.verificar_reuso(tmp_path, 'a' * 64)
    tobe.guardar_llave(tmp_path, 'b' * 64)
    with pytest.raises(SystemExit, match='otra versión del código'):
        tobe.verificar_reuso(tmp_path, 'a' * 64)
    tobe.verificar_reuso(tmp_path, 'b' * 64)



def test_cada_tabla_de_las_migraciones_tiene_origen_o_declaracion():
    """Sin esperar al job de paridad: una tabla nueva del TO-BE debe mapearse desde el legado o declararse en NUEVAS
    (el esquema tras cada carga la rechazaría a los diez minutos)."""
    from paridad.mapeo import NUEVAS, T, destinos
    carpeta = Path(__file__).resolve().parent.parent / 'src/Decant.Infrastructure/Persistencia/Migraciones'
    tablas = {t for archivo in carpeta.glob('*.cs') if not archivo.name.endswith(('.Designer.cs', 'Snapshot.cs'))
              for t in re.findall(r'CreateTable\(\s*name: "(\w+)"', archivo.read_text(encoding='utf-8'))}
    assert {'orden_pago', 'resultado_archivo'} <= tablas
    con_origen = {c.rsplit('.', 1)[0] for c in destinos()} | {c.rsplit('.', 1)[0] for c in NUEVAS}
    assert sorted(t for t in tablas if T + t not in con_origen) == []
