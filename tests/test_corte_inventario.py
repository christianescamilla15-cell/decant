"""Inventario de salidas DESDE EL CÓDIGO (S3, ADR 0014), sin base: el parser sobre el SQL real del legado y sobre
casos mínimos que aíslan cada regla. Cada prueba trae su control negativo."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from corte import codigo, escribir, fuentes, sql
from legado.conexion import lotes as lotes_del_cargador
from radiografia.tsql import fichas

RAIZ = codigo.RAIZ


@pytest.fixture(scope='module')
def inv() -> dict:
    return codigo.inventario()


def _objeto(inv: dict, id_: str) -> dict:
    return next(o for o in inv['objetos'] if o['id'] == id_)


def _analizar(texto: str) -> sql.Analisis:
    conocidos = {'dbo.moneda': 'tabla', 'dbo.operacion': 'tabla', 'dbo.orden_pago': 'tabla', 'dbo.bitacora': 'tabla',
                 'dbo.sp_hija': 'procedimiento', 'dbo.fn_tasa': 'funcion'}
    return sql.analizar(fichas(texto), conocidos, 'BFN_DIVISAS', 'BFN_DIVISAS')


def test_el_inventario_del_codigo_cuenta_lo_que_dice_el_plan(inv, tmp_path):
    """Criterio 1 del plan: 15 procedimientos, 2 vistas, 1 trigger, 1 job, 2 interfaces y la pantalla."""
    assert inv['por_tipo'] == {'procedimiento': 15, 'vista': 2, 'trigger': 1, 'funcion': 0, 'job': 1,
                               'interfaz': 2, 'pantalla': 1}
    # control: el conteo sale del código, no está escrito; sin el último procedimiento, hay uno menos y no aparece
    copia = tmp_path / 'sql'
    shutil.copytree(codigo.SQL, copia)
    procs = copia / '05_procedimientos.sql'
    texto = procs.read_text(encoding='utf-8')
    procs.write_text(texto[:texto.index('-- Contingencia de la mesa')], encoding='utf-8')
    otro = codigo.inventario(sql=copia)
    assert otro['por_tipo']['procedimiento'] == 14
    assert 'dbo.sp_alta_manual_orden' not in {o['id'] for o in otro['objetos']}


def test_los_lotes_son_los_mismos_que_ejecuta_el_cargador_del_legado():
    for ruta in sorted(codigo.SQL.glob('*.sql')):
        texto = ruta.read_text(encoding='utf-8')
        assert [x.texto.strip() for x in sql.lotes(texto, ruta.name)] == lotes_del_cargador(texto), ruta.name
    # control: una línea que EMPIEZA con GO pero no es GO no separa
    assert len(sql.lotes('SELECT 1\nGOTO fin\nGO\nSELECT 2\n', 'x.sql')) == 2


def test_update_from_escribe_la_tabla_del_alias_no_la_primera_del_from(inv):
    """r3-T1: `UPDATE o … FROM dbo.orden_pago p JOIN dbo.operacion o` escribe operacion, no orden_pago."""
    reflejar = _objeto(inv, 'dbo.sp_reflejar_estatus_operacion')
    assert reflejar['escribe'] == {'dbo.operacion': ['UPDATE']}
    assert set(reflejar['lee']) == {'dbo.orden_pago', 'dbo.operacion'}
    # control: el mismo patrón con el alias en la PRIMERA tabla (sp_conciliar) escribe esa tabla
    assert _objeto(inv, 'dbo.sp_conciliar')['escribe'] == {'dbo.orden_pago': ['UPDATE']}
    assert _analizar('UPDATE x SET a = 1 FROM dbo.operacion x JOIN dbo.orden_pago y ON y.id = x.id').escribe == {
        'dbo.operacion': {'UPDATE'}}


def test_el_reloj_dentro_de_sql_dinamico_se_ve_y_queda_marcado(inv):
    """r3-T2: el GETDATE() vive dentro de la cadena que corre sp_executesql; también lo que esa cadena lee."""
    antiguedad = _objeto(inv, 'dbo.sp_antiguedad_ordenes')
    assert antiguedad['sql_dinamico'] == ['sp_executesql']
    assert antiguedad['reloj'] == ['GETDATE (en SQL dinámico)']
    assert antiguedad['desde_sql_dinamico'] == ['dbo.orden_pago']
    # control: un GETDATE() en una cadena que NO se ejecuta, o en un comentario, no es reloj
    a = _analizar("-- GETDATE() aquí no cuenta\nSELECT 'GETDATE()' AS texto FROM dbo.moneda")
    assert not a.reloj and not a.sql_dinamico and a.lee == {'dbo.moneda'}


def test_identidad_de_sesion_y_el_trigger_que_inserta_en_otra_tabla_con_identidad(inv):
    """r3-T3: sp_alta_manual_orden usa @@IDENTITY tras insertar en orden_pago, cuyo trigger inserta en bitacora."""
    alta = _objeto(inv, 'dbo.sp_alta_manual_orden')
    assert alta['identidad'] == ['@@IDENTITY']
    assert alta['efectivo']['dispara'] == ['dbo.tr_orden_pago_bitacora']
    assert 'dbo.bitacora' in alta['efectivo']['escribe'] and inv['tablas']['dbo.bitacora']['identidad']
    # control: los demás que insertan órdenes usan SCOPE_IDENTITY (no se marcan como @@IDENTITY)
    assert _objeto(inv, 'dbo.sp_registrar_orden')['identidad'] == ['SCOPE_IDENTITY']


def test_una_columna_con_nombre_de_tabla_no_es_una_lectura_de_esa_tabla():
    """`moneda` es columna de operacion y también tabla: sólo cuenta como tabla en posición de tabla."""
    assert _analizar('SELECT moneda, COUNT(*) FROM dbo.operacion GROUP BY moneda').lee == {'dbo.operacion'}
    # control: en el FROM sí es la tabla
    assert _analizar('SELECT m.nombre FROM dbo.moneda m').lee == {'dbo.moneda'}


def test_variables_de_tabla_y_temporales_no_son_escrituras_de_tablas_del_legado(inv):
    posicion = _objeto(inv, 'dbo.sp_reporte_posicion')          # INSERT/UPDATE sólo a @posicion
    assert posicion['acceso'] == 'lee' and posicion['escribe'] == {}
    conciliar = _objeto(inv, 'dbo.sp_conciliar')                # SELECT … INTO #lote
    assert conciliar['temporales'] == ['#lote'] and '#lote' not in conciliar['escribe']
    # control: un INSERT a una tabla real sí escribe
    assert _analizar('INSERT INTO dbo.moneda (codigo) VALUES (1)').escribe == {'dbo.moneda': {'INSERT'}}


def test_efectos_fuera_de_la_base_se_declaran_por_objeto(inv):
    a = _analizar("""
        EXEC msdb.dbo.sp_send_dbmail @recipients = 'x';
        EXEC msdb.dbo.sp_start_job @job_name = 'otro';
        SELECT * FROM SRV1.Base.dbo.tabla;
        SELECT * FROM OPENQUERY(SRV2, 'select 1');
        BULK INSERT dbo.moneda FROM '/datos/monedas.csv';
        EXEC xp_cmdshell 'dir';
        SELECT * FROM OtraBase.dbo.cosa;""")
    assert a.efectos == {'correo (sp_send_dbmail)', 'arranca un job (sp_start_job)', 'servidor enlazado: SRV1',
                         'servidor enlazado (OPENQUERY)', 'archivos (BULK INSERT)', 'sistema operativo (xp_cmdshell)',
                         'otra base: OtraBase'}
    # control: el legado de hoy no tiene ninguno; sólo las interfaces (archivos) salen de la base
    con_efectos = {o['id'] for o in inv['objetos'] if o['efectivo']['efectos_externos']}
    assert con_efectos == {'interfaz:buzon_corresponsal', 'interfaz:archivo_sucursales'}


def test_los_escritores_incluyen_triggers_y_pasos_de_job(inv):
    """Plan, criterio 9: N de N escritores sacados del inventario, no una cifra fija."""
    assert inv['escritores'] == [
        'dbo.sp_alta_manual_orden', 'dbo.sp_conciliar', 'dbo.sp_reflejar_estatus_operacion',
        'dbo.sp_registrar_liquidacion', 'dbo.sp_registrar_operacion', 'dbo.sp_registrar_orden',
        'dbo.tr_orden_pago_bitacora', 'job:BFN - conciliacion nocturna/paso:conciliar']
    paso = _objeto(inv, 'job:BFN - conciliacion nocturna')['pasos'][0]
    assert paso['llama'] == ['dbo.sp_conciliar']
    assert paso['efectivo']['escribe'] == {'dbo.bitacora': ['INSERT'], 'dbo.orden_pago': ['UPDATE']}
    # control: los que sólo leen no son escritores
    lectores = {o['id'] for o in inv['objetos'] if o['acceso'] == 'lee'}
    assert lectores and not lectores & set(inv['escritores'])


def test_el_job_se_lee_con_su_paso_y_su_horario_y_otro_subsistema_es_un_efecto():
    codigo_ = sql.leer_scripts([codigo.SQL / '06_job.sql'], RAIZ)
    job = codigo_.jobs[0]
    assert (job.nombre, job.horarios[0]['hora'], job.pasos[0]['comando']) == (
        'BFN - conciliacion nocturna', '23:30', 'EXEC dbo.sp_conciliar;')
    # control: un paso CmdExec es un efecto fuera de la base (no T-SQL que se pueda analizar)
    assert sql.SUBSISTEMAS_EXTERNOS['CMDEXEC'] == 'sistema operativo'


def test_la_pantalla_y_las_interfaces_salen_del_codigo(inv, tmp_path):
    pantalla = _objeto(inv, 'pantalla:legado/pantalla')
    assert pantalla['llama'] == ['dbo.sp_detalle_operacion', 'dbo.sp_lista_operaciones'] and pantalla['lee'] == []
    assert {o['id']: o['nombre'] for o in inv['objetos'] if o['tipo'] == 'interfaz'} == {
        'interfaz:archivo_sucursales': 'Archivo de sucursales', 'interfaz:buzon_corresponsal': 'Buzón del corresponsal'}
    # control: una consulta nueva en la pantalla y un archivo nuevo en las interfaces entran solos
    copia = tmp_path / 'pantalla'
    shutil.copytree(codigo.PANTALLA, copia)
    (copia / 'nueva.py').write_text("CONSULTA = 'SELECT folio FROM dbo.orden_pago'\n", encoding='utf-8')
    consultas = fuentes.consultas_de(sorted(copia.glob('*.py')), tmp_path, {'dbo.orden_pago': 'tabla'}, 'BFN_DIVISAS')
    assert any(c.analisis.lee == {'dbo.orden_pago'} for c in consultas)
    interfaces = tmp_path / 'interfaces.py'
    interfaces.write_text(codigo.INTERFACES.read_text(encoding='utf-8')
                          + "\n\ndef tesoreria(d):\n    return {f'tesoreria/{d:%Y%m%d}.txt': ''}\n", encoding='utf-8')
    assert [i.carpeta for i in fuentes.interfaces_de(interfaces, tmp_path)] == [
        'corresponsal', 'sucursales', 'tesoreria']


def test_objetos_json_versionado_es_el_que_sale_del_codigo(tmp_path):
    generado = escribir.generar()[escribir.OBJETOS]
    assert escribir.OBJETOS.read_text(encoding='utf-8') == generado, 'corre python -m corte.escribir'
    # control: un cambio en el SQL cambia el inventario (la comparación puede fallar)
    copia = tmp_path / 'sql'
    shutil.copytree(codigo.SQL, copia)
    with (copia / '05_procedimientos.sql').open('a', encoding='utf-8') as f:
        f.write('CREATE OR ALTER PROCEDURE dbo.sp_x AS SELECT 1;\nGO\n')
    assert json.dumps(codigo.inventario(sql=copia), ensure_ascii=False, indent=1) + '\n' != generado


def test_el_inventario_es_determinista():
    assert json.dumps(codigo.inventario()) == json.dumps(codigo.inventario())
    # control: las rutas son relativas al repo (no dependen de dónde se clonó)
    assert not any(Path(o['fuente'].split(':')[0]).is_absolute() for o in codigo.inventario()['objetos'])
