"""Integración contra el legado REAL (SQL Server en Docker) después del ciclo del CI:

    esquema → cargar → pantalla → respaldar → legado vivo → radiografía → medición → estas pruebas

El generador simula el código de los procedimientos; aquí se comprueba contra el motor que la simulación calcula
lo mismo que ellos (tipo de cambio, comisión, horas de liquidación, re-registro). Si no, los datos «históricos»
no serían los que el legado habría producido.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import pytest

from legado.generador.simulacion import _comision, _horas
from legado.generador.zonas import NUEVA_YORK, local

pytestmark = pytest.mark.integracion

INFORME = Path(os.environ.get('DECANT_INFORME', 'radiografia/informe'))
DATOS = Path('legado/datos')


@pytest.fixture(scope='module')
def conexion():
    if not os.environ.get('DECANT_SA_PASSWORD'):
        pytest.fail('las pruebas de integración necesitan el legado arriba y DECANT_SA_PASSWORD')
    from legado.conexion import conectar
    with conectar() as c:
        yield c


def _json(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


def test_el_respaldo_restaurado_cumple_el_criterio_de_salida():
    criterio = _json(INFORME / 'radiografia.json')['criterio_salida']
    assert criterio['aplica'] and criterio['cumple'], criterio
    assert criterio['filas'] > 400_000


def test_la_radiografia_detecta_al_menos_ocho_de_las_nueve_trampas():
    medicion = _json(INFORME / 'medicion.json')
    assert medicion['detectadas'] >= 8, [f['id'] for f in medicion['filas'] if f['estado'] != 'detectada']


def test_control_negativo_el_reporte_mensual_del_legado_no_se_repite_a_si_mismo(conexion):
    cursor = conexion.cursor()
    corridas = []
    for _ in range(5):
        cursor.execute("EXEC dbo.sp_reporte_ordenes @desde = '2023-12-01', @hasta = '2023-12-31'")
        corridas.append([(f[0], f[11]) for f in cursor.fetchall()])
    # mismo contenido (multiconjunto) …
    assert all(Counter(c) == Counter(corridas[0]) for c in corridas[1:])
    # … pero no el mismo orden: comparar por posición contra el propio legado ya da diferencias
    distintas = [sum(1 for a, b in zip(corridas[0], c) if a != b) for c in corridas[1:]]
    assert max(distintas) > 0, 'el control negativo salió en 0 %: hace falta más volumen (legado/VOLUMEN.md)'


def test_tipo_de_cambio_y_pesos_del_procedimiento_son_los_del_generador(conexion, datos):
    pasos = [p for p in datos.pasos if p['accion'] == 'operacion']
    cursor = conexion.cursor()
    cursor.execute('SELECT id, tipo_cambio, monto_mxn FROM dbo.operacion WHERE id > %s ORDER BY id',
                   (len(datos.tablas['operacion']),))
    filas = cursor.fetchall()
    assert len(filas) == len(pasos)
    por_seq = {op.seq: op for op in datos.operaciones}
    for (_id, tc, pesos), paso in zip(filas, pasos):
        op = por_seq[int(paso['ref'].split(':')[1])]
        assert (tc, pesos) == (op.tc, op.monto_mxn)


def test_la_comision_que_trunca_el_procedimiento_es_la_del_generador(conexion):
    cursor = conexion.cursor()
    cursor.execute("""SELECT p.monto, o.monto_mxn FROM dbo.partida_liquidada p
                      JOIN dbo.orden_pago op ON op.id = p.orden_id JOIN dbo.operacion o ON o.id = op.operacion_id
                      WHERE p.concepto = 'COMISION' AND op.fecha_registro >= '2023-12-29T06:00:00'""")
    filas = cursor.fetchall()
    assert len(filas) > 100
    assert all(comision == _comision(pesos) for comision, pesos in filas)


def test_el_re_registro_del_procedimiento_reemplaza_y_conserva_el_folio(conexion, datos):
    uetrs = [p['args']['uetr'] for p in datos.pasos if p['accion'] == 'orden' and p['args']['reregistro']]
    cursor = conexion.cursor()
    for uetr in uetrs[:60]:
        cursor.execute('SELECT id, folio, estatus, fecha_registro FROM dbo.orden_pago WHERE uetr = %s ORDER BY id',
                       (uetr,))
        filas = cursor.fetchall()
        assert len(filas) >= 2
        assert len({f[1] for f in filas}) == 1
        assert all(f[2] == 'REEMPLAZADA' for f in filas[:-1]) and filas[-1][2] in ('ENVIADA', 'LIQUIDADA')
        assert filas[-1][3].date().isoformat() == '2023-12-29'


def test_el_job_calcula_las_horas_como_el_generador_y_su_getdate_vence_todo_lo_pendiente(conexion, datos):
    """sp_conciliar dentro de una transacción que se revierte: el legado queda como estaba."""
    liquidadas = {p['args']['uetr'] for p in datos.pasos if p['accion'] == 'liquidacion'}
    docs = {d.uetr: d for d in datos.documentos if d.uetr in liquidadas}
    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) FROM dbo.orden_pago WHERE estatus = 'ENVIADA'")
    enviadas = cursor.fetchone()[0]
    assert enviadas > 0
    cursor.execute('BEGIN TRANSACTION')
    try:
        cursor.execute('EXEC dbo.sp_conciliar')
        cursor.execute("SELECT uetr, estatus, horas_liquidacion FROM dbo.orden_pago "
                       "WHERE estatus IN ('CONCILIADA', 'DIFERENCIA') AND fecha_registro >= '2023-12-28'")
        conciliadas = {u.strip(): (e, h) for u, e, h in cursor.fetchall() if u.strip() in docs}
        cursor.execute("SELECT COUNT(*) FROM dbo.orden_pago WHERE estatus = 'ENVIADA'")
        enviadas_despues = cursor.fetchone()[0]
    finally:
        cursor.execute('ROLLBACK TRANSACTION')
    assert len(conciliadas) > 50
    for uetr, (estatus, horas) in conciliadas.items():
        d = docs[uetr]
        assert horas == _horas(local(d.t_envio), local(d.t_liquidacion, NUEVA_YORK)), uetr
        assert estatus == ('CONCILIADA' if d.abono + d.comision == d.monto else 'DIFERENCIA'), uetr
    # T8: con el reloj de hoy, el job vence TODO lo enviado, incluso lo del mismo día del respaldo
    assert enviadas_despues == 0
    cursor.execute("SELECT COUNT(*) FROM dbo.orden_pago WHERE estatus = 'ENVIADA'")
    assert cursor.fetchone()[0] == enviadas          # la transacción se revirtió


def test_bcp_c_destruye_acentos_y_letras_que_no_caben_en_1252():
    from legado.bcp import medir
    r = medir()
    assert r['operacion.cliente']['con_signos_de_interrogacion'] > 10_000
    beneficiario = r['orden_pago.beneficiario']
    assert beneficiario['distintas_en_1252'] > beneficiario['con_signos_de_interrogacion'] > 1000


def test_el_legado_vivo_siguio_escribiendo_despues_del_congelamiento():
    registro = _json(sorted(DATOS.glob('vivo_*.json'))[-1])
    assert registro['re_registros']['delta'] > 50
    for tabla in ('operacion', 'orden_pago'):
        assert registro['al_terminar'][tabla]['filas'] > registro['al_congelamiento'][tabla]['filas'] \
            > registro['al_respaldo'][tabla]['filas']
    assert registro['al_congelamiento']['moneda']['filas'] == registro['al_respaldo']['moneda']['filas'] + 1
    assert registro['al_terminar']['operacion']['max_id'] > registro['al_congelamiento']['operacion']['max_id']
