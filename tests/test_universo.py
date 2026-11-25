"""Universo del legado: partición por columna, archivos de interfaz con sus llaves reales y noches del job."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

from legado.generador.simulacion import COLUMNAS
from radiografia.datos import es_mojibake
from universo.interfaces import leer_buzon, leer_confirmacion, leer_sucursales
from universo.noches import cuadre
from universo.particion import PARTICION, columnas_de, validar

ESQUEMA = {f'dbo.{t}': list(c) for t, c in COLUMNAS.items()}

# Mensaje con el formato real que deja el generador (estilo MT910 simplificado).
MENSAJE = ("{1:F01FICTMXMMXXX0000000000}{2:O9100801231228FICTUS33XXXX00000000002312280801N}"
           "{3:{121:c0d9bfd1-62d7-4845-98cc-790b5aa7c103}}{4:\n") + """:20:FICT675378759361
:21:BFN231227000175
:25:BFNUSDNOSTRO01
:13D:2312280801-0500
:32A:231228USD5279,22
:52A:FICTUS33XXX
:71F:USD11,20
-}"""


# ── partición por columna ───────────────────────────────────────────────────────────────────────────────────

def test_cada_columna_del_legado_tiene_exactamente_una_categoria():
    assert validar(ESQUEMA) == []


def test_la_particion_detecta_columnas_sin_categoria_y_de_mas():
    errores = validar({'dbo.folio': ['serie', 'siguiente', 'actualizado', 'nueva']})
    assert errores == ['dbo.folio.nueva: sin categoría']
    assert validar({'dbo.tabla_nueva': ['a']}) == ['dbo.tabla_nueva: la tabla no está en la partición']


def test_en_orden_pago_conviven_entradas_y_resultados():
    entradas = columnas_de('dbo.orden_pago', 'entrada')
    resultados = columnas_de('dbo.orden_pago', 'resultado')
    assert {'monto', 'fecha_envio', 'bic_corresponsal', 'uetr'} <= set(entradas)
    assert {'estatus', 'horas_liquidacion', 'folio'} <= set(resultados)
    # la comisión es un resultado: la calcula sp_registrar_orden (y trunca, D1)
    assert 'monto' in PARTICION['dbo.partida_liquidada']['resultado']


# ── buzón del corresponsal: llaves reales ───────────────────────────────────────────────────────────────────

def test_la_confirmacion_se_cruza_por_uetr_y_por_nuestra_referencia_no_por_el_20():
    c = leer_confirmacion(MENSAJE)
    assert c.uetr == 'c0d9bfd1-62d7-4845-98cc-790b5aa7c103'
    assert c.referencia == 'BFN231227000175'          # :21: = nuestro :20: del MT103
    assert c.trn_corresponsal == 'FICT675378759361'   # el primer campo «parecido»: no es llave
    assert (c.moneda, c.abono, c.comision) == ('USD', Decimal('5279.22'), Decimal('11.20'))


def test_la_hora_del_corresponsal_trae_su_desfase_y_da_el_instante_utc():
    c = leer_confirmacion(MENSAJE)
    assert c.hora_local_ny == datetime(2023, 12, 28, 8, 1)              # lo que guardó el legado
    assert c.instante_utc == datetime(2023, 12, 28, 13, 1, tzinfo=timezone.utc)


def test_yenes_enteros_en_formato_swift():
    c = leer_confirmacion(MENSAJE.replace('USD5279,22', 'JPY152340,').replace(':71F:USD11,20\n', ''))
    assert (c.moneda, c.abono, c.comision) == ('JPY', Decimal('152340'), Decimal(0))


def test_el_buzon_trae_las_liquidaciones_que_el_legado_descarto(datos):
    confirmaciones = [c for ruta, texto in datos.interfaces.items() if ruta.startswith('corresponsal/')
                      for c in leer_buzon(texto)]
    tardias = {d.uetr for d in datos.documentos if d.t_liquidacion is not None and not d.aceptada
               and d.t_liquidacion < datos.config.fin}        # las que llegan después del fin no existen todavía
    en_buzon = {c.uetr for c in confirmaciones}
    assert len(tardias) > 1000 and tardias <= en_buzon     # D3: el TO-BE sí tiene de dónde sacarlas
    referencias_legado = {f[4] for f in datos.tablas['orden_pago']}
    assert not {c.trn_corresponsal for c in confirmaciones} & referencias_legado   # cruzar por :20: no encuentra nada
    assert {c.referencia for c in confirmaciones} <= referencias_legado | {
        p['args']['referencia_mt103'] for p in datos.pasos if p['accion'] == 'orden'}


def test_el_buzon_trae_horas_de_verano_y_de_invierno_de_nueva_york(datos):
    desfases = Counter(texto.split(':13D:')[1][10:15] for ruta, texto in datos.interfaces.items()
                       if ruta.startswith('corresponsal/2023'))
    assert set(desfases) == {'-0500', '-0400'}


# ── archivo de sucursales ──────────────────────────────────────────────────────────────────────────────────

def test_el_archivo_de_sucursales_trae_el_nombre_sano_que_el_legado_danio(datos):
    renglones = leer_sucursales(datos.interfaces['sucursales/20220301.csv'])
    assert renglones and all(not es_mojibake(r['cliente']) for r in renglones)
    con_acento = [r for r in renglones if any(ord(ch) > 127 for ch in r['cliente'])]
    assert con_acento
    por_fecha = {(f[3], str(f[2])) for f in datos.tablas['operacion'] if f[4] == 'ARCHIVO' and es_mojibake(f[5])}
    assert any((r['sucursal'], r['fecha_hora'].replace('T', ' ') + ':00') in por_fecha for r in con_acento)


def test_el_reenvio_tardio_de_una_sucursal_es_un_archivo_aparte(datos):
    reenvios = [r for r in datos.interfaces if r.endswith('_reenvio.csv')]
    assert len(reenvios) == 1
    ayer = datos.config.fecha_respaldo.toordinal() - 1
    renglones = leer_sucursales(datos.interfaces[reenvios[0]])
    assert renglones and all(datetime.fromisoformat(r['fecha_hora']).toordinal() == ayer for r in renglones)
    assert len({r['referencia'] for r in renglones}) == len(renglones)


# ── noches del job ─────────────────────────────────────────────────────────────────────────────────────────

def test_cuadre_de_noches_contra_el_horario():
    noches = [datetime(2023, 12, 27, 23, 30), datetime(2023, 12, 28, 23, 30), datetime(2023, 12, 28, 10, 5)]
    r = cuadre(noches, '23:30')
    assert r['noches'] == 3 and r['a_la_hora_del_horario'] == 2 and r['fuera_de_horario'] == [noches[2]]
