"""Cruce con lo observado y PUERTA de cobertura de salidas (S3, ADR 0014), sin base. La observación es sintética
(con la forma exacta del artefacto del CI) salvo donde se dice. Cada prueba trae su control negativo."""
from __future__ import annotations

import json
import re
import shutil

import pytest

from corte import codigo, cruce, observar, puerta, renglones

RAIZ = codigo.RAIZ
EVIDENCIA_REAL = 'tests/integracion/test_paridad.py::test_el_motor_no_tiene_defectos_nuestros_y_r08_replica_al_legado'


@pytest.fixture(scope='module')
def inv() -> dict:
    return codigo.inventario()


def observado(ejecutados=('dbo.sp_lista_operaciones',), consumidores=(('sa', 'pymssql=2.4.6'),), bitacora=(),
              catalogo=None, terminado=True) -> dict:
    return {
        'terminado': terminado,
        'objetos_ejecutados': {i: {'tipo': 'procedimiento', 'fuentes': ['dm_exec_procedure_stats'], 'ejecuciones': 1}
                               for i in ejecutados},
        'consumidores': [{'login': login, 'aplicacion': app, 'interfaz_cliente': 'DB-Library', 'sesiones': 1}
                         for login, app in consumidores],
        'bitacora': {'usuarios': [{'login': u, 'filas': 10} for u in bitacora]},
        'catalogo': catalogo or {'modulos': [], 'jobs': []},
    }


def renglon(clave: str, destino: str = 'pendiente', clase: str = 'objeto', **extra) -> renglones.Renglon:
    return renglones.Renglon(clase, clave, destino, **extra)


def todos_pendientes(inv: dict, logins=('sa',)) -> list[renglones.Renglon]:
    return [renglon(o['id']) for o in inv['objetos']] + [renglon(x, clase='login') for x in logins]


def test_lo_no_observado_queda_sin_ejecucion_observada_y_nunca_se_recorta(inv):
    c = cruce.cruzar(inv, observado())
    assert set(c['objetos']) == {o['id'] for o in inv['objetos']}          # los 22 siguen ahí
    assert c['objetos']['dbo.sp_alta_manual_orden'] == {'ejecucion': cruce.SIN_EJECUCION}
    assert len(cruce.sin_ejecucion(c)) == len(inv['objetos']) - 1
    # control: lo que sí se ejecutó queda observado, con su fuente
    assert c['objetos']['dbo.sp_lista_operaciones']['ejecucion'] == cruce.OBSERVADA


def test_una_vista_la_ejecuta_quien_la_lee(inv):
    c = cruce.cruzar(inv, observado(ejecutados=('dbo.sp_reporte_ordenes',)))
    assert c['objetos']['dbo.vw_reporte_ordenes'] == {'ejecucion': cruce.POR_QUIEN_LA_USA,
                                                     'por': ['dbo.sp_reporte_ordenes']}
    # control: la otra vista, cuyo lector no corrió, sigue sin ejecución observada
    assert c['objetos']['dbo.vw_liquidaciones_recientes']['ejecucion'] == cruce.SIN_EJECUCION


def test_la_pantalla_no_se_da_por_observada_por_lo_que_llama(inv):
    """El servidor no distingue qué cliente hizo la llamada: la pantalla queda sin ejecución observada, con nota."""
    c = cruce.cruzar(inv, observado(ejecutados=('dbo.sp_lista_operaciones', 'dbo.sp_detalle_operacion')))
    pantalla = c['objetos']['pantalla:legado/pantalla']
    assert pantalla['ejecucion'] == cruce.SIN_EJECUCION and 'dbo.sp_detalle_operacion' in pantalla['nota']
    # control: sin sus llamadas observadas, ni siquiera la nota
    assert 'nota' not in cruce.cruzar(inv, observado(ejecutados=()))['objetos']['pantalla:legado/pantalla']


def test_lo_que_el_servidor_tiene_o_ejecuta_fuera_del_codigo_necesita_renglon(inv):
    obs = observado(ejecutados=('dbo.sp_lista_operaciones', 'dbo.sp_suelto', 'dbo.operacion'),
                    catalogo={'modulos': [{'id': 'dbo.vw_fantasma', 'tipo': 'vista'}], 'jobs': ['job:limpieza']})
    c = cruce.cruzar(inv, obs)
    assert [f['id'] for f in c['fuera_del_codigo']] == ['dbo.sp_suelto', 'dbo.vw_fantasma', 'job:limpieza']
    r = puerta.evaluar(inv, c, todos_pendientes(inv), [])
    assert r['sin_renglon']['objetos'] == ['dbo.sp_suelto', 'dbo.vw_fantasma', 'job:limpieza']
    # control: una TABLA leída no es un objeto fuera del código (sus datos los cubren la carga y los totales)
    assert 'dbo.operacion' not in {f['id'] for f in c['fuera_del_codigo']}


def test_la_puerta_nombra_un_objeto_sembrado_en_el_sql(tmp_path, capsys):
    obs = tmp_path / 'observado.json'
    obs.write_text(json.dumps(observado()), encoding='utf-8')
    copia = tmp_path / 'sql'
    shutil.copytree(codigo.SQL, copia)
    argumentos = ['--sql', str(copia), '--observado', str(obs), '--renglones', str(puerta.RENGLONES),
                  '--json', str(tmp_path / 'r.json')]
    # control: sin la siembra, ningún objeto queda sin renglón (la puerta falla por otra cosa: pendientes)
    assert puerta.main(argumentos) == 1
    assert json.loads((tmp_path / 'r.json').read_text())['sin_renglon']['objetos'] == []
    with (copia / '05_procedimientos.sql').open('a', encoding='utf-8') as f:
        f.write('-- sembrado\nCREATE OR ALTER PROCEDURE dbo.sp_sembrado AS UPDATE dbo.folio SET siguiente = 0;\nGO\n')
    capsys.readouterr()
    assert puerta.main(argumentos) == 1
    salida = capsys.readouterr().out
    assert '✘ objetos sin renglón (1):\n    - dbo.sp_sembrado' in salida
    assert json.loads((tmp_path / 'r.json').read_text())['sin_renglon']['objetos'] == ['dbo.sp_sembrado']


def test_la_puerta_nombra_un_login_nuevo_del_artefacto_de_sesiones(inv):
    lista = todos_pendientes(inv)
    obs = observado(consumidores=(('sa', 'pymssql=2.4.6'), ('lector_reportes', 'Excel')))
    r = puerta.evaluar(inv, cruce.cruzar(inv, obs), lista, [])
    assert r['sin_renglon']['logins'] == ['lector_reportes']
    # control: con su renglón deja de faltar
    r = puerta.evaluar(inv, cruce.cruzar(inv, obs), lista + [renglon('lector_reportes', clase='login')], [])
    assert r['sin_renglon']['logins'] == []


def test_los_que_escribieron_segun_la_bitacora_tambien_son_consumidores(inv):
    obs = observado(bitacora=('svc_swift',))
    r = puerta.evaluar(inv, cruce.cruzar(inv, obs), todos_pendientes(inv), [])
    assert r['sin_renglon']['logins'] == ['svc_swift']
    # control: sin bitácora no aparece
    assert puerta.evaluar(inv, cruce.cruzar(inv, observado()), todos_pendientes(inv), [])['sin_renglon'][
        'logins'] == []


def test_una_aplicacion_que_su_login_no_declara_se_nombra(inv):
    lista = [r for r in todos_pendientes(inv) if r.clase == 'objeto'] + [
        renglon('sa', clase='login', aplicaciones=['pymssql=*', 'SQLCMD'])]
    obs = observado(consumidores=(('sa', 'pymssql=9.9.9'), ('sa', 'Microsoft Office')))
    r = puerta.evaluar(inv, cruce.cruzar(inv, obs), lista, [])
    assert r['sin_renglon']['aplicaciones'] == ['sa · Microsoft Office']
    # control: una versión nueva del cliente declarado sí entra por su patrón
    assert 'sa · pymssql=9.9.9' not in r['sin_renglon']['aplicaciones']


def test_sin_ejecucion_observada_no_pasa_a_retirado_solo(inv):
    lista = [r for r in todos_pendientes(inv) if r.clave != 'dbo.sp_alta_manual_orden']
    c = cruce.cruzar(inv, observado())
    r = puerta.evaluar(inv, c, lista, [])
    assert c['objetos']['dbo.sp_alta_manual_orden']['ejecucion'] == cruce.SIN_EJECUCION
    assert r['sin_renglon']['objetos'] == ['dbo.sp_alta_manual_orden'] and r['destinos']['retirado'] == {}
    # un retiro que sólo se apoya en el silencio de las estadísticas no vale
    sin_vigia = renglon('dbo.sp_alta_manual_orden', 'retirado', dueno='mesa', fecha='2027-01-15',
                        nota='sin ejecución observada en el ciclo')
    assert any('vigía' in e for e in renglones.validar(sin_vigia, RAIZ))
    # control: con dueño, fecha y la confirmación del vigía, sí
    completo = renglon('dbo.sp_alta_manual_orden', 'retirado', dueno='mesa', fecha='2027-01-15',
                       confirmacion_vigia='vigía 2027-01-08 a 2027-01-15: 0 conexiones, 0 EXEC')
    assert renglones.validar(completo, RAIZ) == []


def test_una_cobertura_que_no_apunta_a_una_prueba_real_no_cuenta():
    inventada = renglon('dbo.sp_reporte_posicion', 'comparado',
                        evidencia=['tests/integracion/test_paridad.py::test_el_reporte_de_posicion_cuadra'])
    assert renglones.validar(inventada, RAIZ) == [
        'evidencia «tests/integracion/test_paridad.py::test_el_reporte_de_posicion_cuadra»: no existe la prueba']
    assert renglones.validar(renglon('x', 'comparado'), RAIZ) == ['«comparado» sin evidencia (archivo::prueba)']
    assert 'no existe el archivo' in renglones.validar(
        renglon('x', 'comparado', evidencia=['../fuera.py::test_x']), RAIZ)[0]
    # control: una prueba que existe
    assert renglones.validar(renglon('x', 'comparado', evidencia=[EVIDENCIA_REAL]), RAIZ) == []


def test_renglones_duplicados_huerfanos_y_con_destino_desconocido_se_nombran(inv):
    lista = todos_pendientes(inv) + [renglon('dbo.sp_lista_operaciones'), renglon('dbo.sp_que_ya_no_existe'),
                                     renglon('login_viejo', clase='login')]
    lista[0].destino = 'migrado'
    r = puerta.evaluar(inv, cruce.cruzar(inv, observado()), lista, [])
    assert r['duplicados'] == ['objeto dbo.sp_lista_operaciones']
    assert r['huerfanos'] == ['login login_viejo', 'objeto dbo.sp_que_ya_no_existe']
    assert any('no es uno de' in e for e in r['renglones_invalidos'][f'objeto {lista[0].clave}'])
    # control: sin esos tres, nada de eso
    limpio = puerta.evaluar(inv, cruce.cruzar(inv, observado()), todos_pendientes(inv), [])
    assert not (limpio['duplicados'] or limpio['huerfanos'] or limpio['renglones_invalidos'])


def test_la_puerta_puede_salir_verde_y_un_pendiente_la_pone_en_rojo(inv):
    """Control de la propia puerta: con todo cubierto sale verde; basta un pendiente para el rojo."""
    lista = [renglon(o['id'], 'comparado', evidencia=[EVIDENCIA_REAL]) for o in inv['objetos']]
    lista.append(renglon('sa', 'reemplazado_con_paridad', clase='login', evidencia=[EVIDENCIA_REAL]))
    c = cruce.cruzar(inv, observado())
    assert puerta.evaluar(inv, c, lista, [])['verde']
    lista[3].destino = 'pendiente'
    r = puerta.evaluar(inv, c, lista, [])
    assert not r['verde'] and [p['clave'] for p in r['pendientes']] == [lista[3].clave]


def test_una_observacion_que_no_termino_no_absuelve_a_los_consumidores(tmp_path, capsys):
    obs = tmp_path / 'observado.json'
    obs.write_text(json.dumps(observado(terminado=False)), encoding='utf-8')
    assert puerta.main(['--observado', str(obs)]) == 1
    assert 'no terminó' in capsys.readouterr().out
    # control: la terminada no trae ese error
    obs.write_text(json.dumps(observado()), encoding='utf-8')
    puerta.main(['--observado', str(obs)])
    assert 'no terminó' not in capsys.readouterr().out


def test_el_resumen_del_job_lleva_los_conteos_por_destino(inv, tmp_path):
    r = puerta.evaluar(inv, cruce.cruzar(inv, observado()), renglones.cargar(puerta.RENGLONES)[0], [])
    md = puerta.markdown(r)
    assert '| pendiente |' in md and '| comparado |' in md and 'ROJA' in md
    # control: el texto de la consola también nombra el resultado
    assert puerta.texto(r).endswith('Resultado: ROJO')


# ── el observador (su parte sin base) ───────────────────────────────────────────────────────────────────────────

def _registro(inv: dict) -> observar.Registro:
    conocidos = {o['id']: o['tipo'] for o in inv['objetos']} | {t: 'tabla' for t in inv['tablas']}
    return observar.Registro(conocidos)


def test_query_store_cuenta_por_sentencia_y_no_infla_las_ejecuciones_del_modulo(inv):
    """Defecto hallado en la prueba local: 3 llamadas salían como 15 (5 sentencias en Query Store)."""
    r = _registro(inv)
    r.ejecutado('dbo', 'sp_registrar_orden', 'P', 'dm_exec_procedure_stats', 3, 'cache1')
    r.ejecutado('dbo', 'sp_registrar_orden', 'P', 'query_store', 15)
    e = r.resumen()['objetos_ejecutados']['dbo.sp_registrar_orden']
    assert e['ejecuciones'] == 3 and e['por_fuente'] == {'dm_exec_procedure_stats': 3, 'query_store': 15}
    # control: si el plan se expulsó y volvió, se suman las dos generaciones del caché
    r.ejecutado('dbo', 'sp_registrar_orden', 'P', 'dm_exec_procedure_stats', 2, 'cache2')
    assert r.resumen()['objetos_ejecutados']['dbo.sp_registrar_orden']['ejecuciones'] == 5


def test_lo_ad_hoc_que_nombra_una_vista_la_da_por_observada_y_lo_del_sistema_no_se_lista(inv):
    r = _registro(inv)
    r.lote_ad_hoc('0x01', 2, True, 'SELECT COUNT(*) FROM dbo.vw_liquidaciones_recientes', 50)
    r.lote_ad_hoc('0x02', 1, True, '(@1 int,@2 varchar(8000))UPDATE [dbo].[moneda] set [activa] = @1 '
                                   'WHERE [codigo]=@2', 80)
    r.lote_ad_hoc('0x03', 5, True, 'select table_id from [BFN_DIVISAS].[sys].[filetable_updates_1] with (readpast)',
                  80)
    resumen = r.resumen()
    assert 'dbo.vw_liquidaciones_recientes' in resumen['objetos_ejecutados']
    assert [g['escribe'] for g in resumen['ad_hoc'] if g['escribe']] == [{'dbo.moneda': ['UPDATE']}]
    assert resumen['ad_hoc_sin_objetos'] == 1
    # control: la tabla escrita directo queda en el grupo ad hoc, no como objeto ejecutado
    assert 'dbo.moneda' not in resumen['objetos_ejecutados']


def test_las_sesiones_se_cuentan_una_vez_aunque_se_muestreen_muchas(inv):
    r = _registro(inv)
    for _ in range(4):
        r.sesion(52, '2026-11-26T08:00:00', 'sa', 'pymssql=2.4.6', 'DB-Library', 'BFN_DIVISAS', 'ahora')
    r.sesion(53, '2026-11-26T08:00:05', 'sa', 'pymssql=2.4.6', 'DB-Library', 'master', 'ahora')
    [c] = r.resumen()['consumidores']
    assert (c['sesiones'], c['muestras'], c['bases']) == (2, 5, ['BFN_DIVISAS', 'master'])
    # control: otra aplicación del mismo login es otro consumidor
    r.sesion(54, '2026-11-26T08:00:09', 'sa', 'SQLCMD', 'ODBC', 'master', 'ahora')
    assert len(r.resumen()['consumidores']) == 2


def test_las_consultas_del_observador_se_excluyen_a_si_mismas_y_nombran_la_base_del_inventario():
    for consulta in (observar.Q_SESIONES, observar.Q_EN_CURSO):
        assert '@@SPID' in consulta
    assert observar.MARCA.strip('/* ').strip() == observar.APLICACION
    assert observar.Q_AD_HOC.count('NOT LIKE') == 1        # lo ad hoc excluye los textos con la marca
    # las consultas son literales (Semgrep); la base escrita en ellas tiene que ser la del inventario
    for nombre, consulta in vars(observar).items():
        if nombre.startswith('Q_'):
            assert consulta.startswith(observar.MARCA), nombre
            bases = set(re.findall(r'\b(\w+)\.(?:sys|dbo)\.', consulta)) | (
                set(re.findall(r"N'(\w+)'", consulta)) - {'dbid'})
            assert bases <= {codigo.PRINCIPAL, 'msdb'}, (nombre, bases)
    # control: otra base escrita a mano se vería
    assert set(re.findall(r'\b(\w+)\.(?:sys|dbo)\.', 'SELECT 1 FROM OTRA.sys.objects')) == {'OTRA'}


def test_el_observador_solo_lee(tmp_path):
    """El observador no cambia opciones del servidor ni escribe en la base: ninguna de sus consultas lo hace."""
    consultas = [v for k, v in vars(observar).items() if k.startswith('Q_') and isinstance(v, str)]
    assert len(consultas) >= 9
    for c in consultas:
        palabras = {p.upper() for p in c.replace('(', ' ').split()}
        assert not palabras & {'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'ALTER', 'CREATE', 'DROP', 'EXEC', 'DBCC'}, c
    # control: la prueba sí detecta una consulta que escribe
    assert {'ALTER'} & {p.upper() for p in 'ALTER DATABASE x SET QUERY_STORE = ON'.split()}


def test_las_rutas_del_artefacto_y_de_lo_versionado():
    assert puerta.OBSERVADO == RAIZ / 'corte' / 'inventario' / 'observado.json'
    assert puerta.RENGLONES.is_file()
    # control: el artefacto del CI no se versiona (va en .gitignore)
    assert 'corte/observado-ci/' in (RAIZ / '.gitignore').read_text(encoding='utf-8').splitlines()
