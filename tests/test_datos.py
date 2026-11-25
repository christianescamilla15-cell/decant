"""Reglas puras de los detectores sobre datos (sin base): centinelas por distribución y mojibake."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from radiografia.datos import clasificar_centinela, es_mojibake, es_re_registro


def test_na_en_una_columna_de_clabe_es_centinela():
    assert clasificar_centinela('varchar', 'NA', 0.26, {'largo_dominante': 18, 'pct_largo_dominante': 1.0})


def test_valor_corto_que_no_tiene_la_forma_de_la_columna_es_centinela():
    razon = clasificar_centinela('char', 'XYZ', 0.1, {'largo_dominante': 11, 'pct_largo_dominante': 0.99})
    assert razon and 'forma ajena' in razon


def test_un_nombre_frecuente_no_es_centinela():
    assert clasificar_centinela('nvarchar', 'MARIA LOPEZ', 0.01, {'largo_dominante': 20, 'pct_largo_dominante': 0.1}) \
        is None


def test_cero_fuera_del_rango_del_resto_es_centinela():
    # tipo de cambio de referencia: 0 cuando el cajero no la capturó; el resto va de 0.11 a 71
    razon = clasificar_centinela('decimal', Decimal('0.000000'), 0.13,
                                 {'minimo': Decimal('0.113984'), 'maximo': Decimal('71.21')})
    assert razon and 'fuera del rango' in razon


def test_cero_dentro_del_rango_no_es_centinela():
    assert clasificar_centinela('decimal', Decimal('0'), 0.2, {'minimo': Decimal('-50'), 'maximo': Decimal('80')}) \
        is None


def test_nueve_no_se_toma_por_centinela():
    # regresión del control público: un id de empaque 9 en un archivo de WideWorldImporters
    assert clasificar_centinela('int', 9, 0.036, {'minimo': 6, 'maximo': 7}) is None


def test_fechas_de_relleno_y_fechas_lejanas_son_centinela():
    assert clasificar_centinela('datetime', datetime(1900, 1, 1), 0.05, {})
    assert clasificar_centinela('date', date(2099, 12, 31), 0.05, {})
    rango = {'minimo': date(2021, 1, 1), 'maximo': date(2023, 1, 1)}
    assert clasificar_centinela('date', date(1950, 1, 1), 0.05, rango)
    assert clasificar_centinela('date', date(2020, 6, 1), 0.05, rango) is None


def test_mojibake_del_legado_y_del_control_publico():
    assert es_mojibake('JOSÃ\x89 PÃ\x89REZ')            # interfaz de sucursales del legado
    assert es_mojibake('Vicente ChÃ¡vez')               # está así en WideWorldImporters
    assert es_mojibake('â€œcomillasâ€\x9d')             # cp1252


def test_texto_sano_no_es_mojibake():
    for texto in ('José Pérez', 'São Paulo', 'ÃO MAIÚSCULO', 'Dvořák Nástroje', 'Ελληνική', 'İzmir'):
        assert not es_mojibake(texto), texto


def test_re_registro_exige_parecerse_mas_que_dos_filas_cualesquiera():
    # legado: las órdenes re-registradas comparten 82 % de columnas; dos órdenes cualesquiera, 20 %
    assert es_re_registro(0.82, 0.20)
    # control público: personas homónimas comparten 69 %, pero dos personas cualesquiera ya comparten 63 %
    assert not es_re_registro(0.69, 0.63)
    assert not es_re_registro(0.50, 0.05)
