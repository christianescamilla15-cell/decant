"""Paridad sin base: la separación universo/oráculo por columna, el mapeo y sus parches, la comparación de esquema
(con su control negativo de T6), el arbitraje, el cuadre por lado y el binding de la pantalla (T4)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from legado.generador.simulacion import COLUMNAS
from paridad import arbitraje, binding, esquema, mapeo, migracion, motor, oraculo, reporte, universo
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
    assert mapeo.aplicar(('char', 'T3_texto'), 'NA         ') is None
    assert mapeo.aplicar(('T3_texto',), '987320396284801163') == '987320396284801163'
    assert mapeo.aplicar(('T3_numero',), Decimal('0.000000')) is None
    assert mapeo.aplicar(('T3_numero',), Decimal('19.859734')) == Decimal('19.859734')


def test_parche_ciega1_t3_recorta_solo_espacios_finales():
    assert mapeo.aplicar(('ciega1_T3',), 'FICT220667399219' + ' ' * 19) == 'FICT220667399219'


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


@pytest.mark.parametrize('envio, ultima, horas', [
    (datetime(2023, 6, 1, 6, 39, 53, tzinfo=timezone.utc), datetime(2023, 6, 1, 12, 30, 42, tzinfo=timezone.utc), 1),
    (datetime(2023, 12, 1, 6, 22, 41, tzinfo=timezone.utc), datetime(2023, 12, 1, 15, 8, 5, tzinfo=timezone.utc), 0),
    (datetime(2022, 3, 20, 11, 55, 9, tzinfo=timezone.utc), datetime(2022, 3, 21, 12, 50, 6, tzinfo=timezone.utc), 1),
])
def test_la_auditoria_de_t5_mide_la_hora_que_el_legado_supone_de_mas(envio, ultima, horas):
    # casos reales: 469818d6… (junio 2023), 2da9c50b… (diciembre 2023), 274cab37… (marzo 2022)
    assert motor._horas_de_desfase(envio, ultima) == horas


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
    salida = {'archivo': 'p.jsonl', 'procedimiento': 'dbo.sp_reporte_ordenes', 'parametros': [], 'conjunto': 0,
              'llave_orden': ['fecha_valor']}
    piso = reporte.piso(cursor, salida, tmp_path)
    assert [m['pct_empatados_invertidos'] for m in piso['muestras']] == [0.0, 100.0, 0.0]
    assert piso['pct_empatados_invertidos'] == 100.0 and piso['inversiones_contrato'] == 0
    assert any('DBCC FREEPROCCACHE' in s for s in cursor.preparaciones)
