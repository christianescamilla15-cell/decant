"""Las trampas latentes con el plan variado (S3 paso 6; ADR 0011 y 0014; criterio 2), sin base. Lo que necesita el
respaldo y la base cerrada (la copia, las variantes, el plan de la caché y el TO-BE) corre en el CI
(`corte/latentes_ci.py`, job `latentes` de `carga.yml`)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from corte import codigo, estado, latentes, latentes_ci, oraculo, trampas
from corte.carga import TABLAS
from corte.estado import NoSeCopia
from corte.latentes import R1_T1, R2_T2
from corte.sql import leer_scripts

RAIZ = Path(__file__).resolve().parent.parent
CARGA = RAIZ / '.github' / 'workflows' / 'carga.yml'


@pytest.fixture(scope='module')
def modulos():
    return {m.id: m for m in leer_scripts(sorted(codigo.SQL.glob('*.sql')), codigo.RAIZ, codigo.PRINCIPAL).modulos}


@pytest.fixture(scope='module')
def conocidos():
    return {f'dbo.{t}' for t in TABLAS} | {o.id for o in latentes.OBJETOS}


# ── el alcance: los dos latentes del catálogo, confirmados después ──────────────────────────────────────────────

def test_los_objetos_medidos_son_los_latentes_del_catalogo_sellado():
    """El catálogo sólo se usa DESPUÉS de medir (para nombrar y confirmar el alcance): aquí se confirma que los dos
    objetos que se varían son los de r1-T1 y r2-T2, y que los dos son de lectura en el inventario del código."""
    cat = trampas.catalogo()
    assert latentes_ci.alcance(cat)['coincide']
    assert {o.id for o in latentes.OBJETOS} == {o for t in trampas.LATENTES for o in cat[t]['objetos']}
    lectores = {o['id'] for o in codigo.inventario()['objetos'] if o['acceso'] == 'lee'}
    assert {o.id for o in latentes.OBJETOS} <= lectores
    assert {k: v[0] for k, v in latentes_ci.DEL_CATALOGO.items()} == {'r1-T1': R1_T1.id, 'r2-T2': R2_T2.id}


def test_cada_sentencia_con_la_asignacion_esta_una_vez_en_el_codigo(modulos):
    for o in latentes.OBJETOS:
        texto = modulos[o.id].texto
        assert texto.count(o.sentencia) == 1, o.id
        assert o.fin is None or texto.count(o.fin) == 1
        assert o.clave in o.sentencia or o.clave in texto
        # la asignación sin TOP ni ORDER BY: lo que la vuelve latente
        assert 'TOP' not in o.sentencia and 'ORDER BY' not in o.sentencia
    assert R2_T2.clave in modulos[R2_T2.id].texto


def test_el_universo_se_lee_de_la_copia_y_nunca_del_original():
    for o in latentes.OBJETOS:
        assert f'{estado.ESQUEMA}.' in o.universo and 'dbo.' not in o.universo
        assert f'{estado.ESQUEMA}.' in latentes.CANDIDATOS_MS[o.id] and 'dbo.' not in latentes.CANDIDATOS_MS[o.id]


# ── las variantes: sólo en la copia ─────────────────────────────────────────────────────────────────────────────

def test_las_variantes_del_piso_y_las_dos_del_encargo_estan_para_los_dos(modulos):
    for o in latentes.OBJETOS:
        ids = [v.id for v in latentes.VARIANTES[o.id]]
        assert ids[:2] == ['tal cual', 'tal cual, otra vez']
        assert {'MAXDOP 4', 'MAXDOP 1', 'lote suelto', 'estadísticas y caché'} <= set(ids)
        assert ids[-1] == 'estadísticas y caché'            # va al final: cambia lo que ven las que siguen
        assert len(set(ids)) == len(ids)
    # r1-T1: además, el lote suelto sin paralelismo (lo que el catálogo midió: «la última por id»)
    assert latentes.variante(R1_T1, 'lote suelto, MAXDOP 1').lote
    assert all(v.forzada for o in latentes.OBJETOS for v in latentes.VARIANTES[o.id]
               if v.id in ('OPTIMIZE FOR UNKNOWN', 'HASH JOIN', 'MERGE JOIN', 'recorrido paralelo'))


def test_cada_variante_cambia_solo_su_sentencia_y_se_copia_en_estado(modulos, conocidos):
    for o in latentes.OBJETOS:
        original = modulos[o.id].texto
        for v in latentes.VARIANTES[o.id]:
            for parche in (False, True):
                texto, reemplazos = latentes.texto_de_variante(original, o, v, parche)
                assert len(reemplazos) == int(parche) + int(v.pista is not None)
                if v.pista:
                    assert f'OPTION ({v.pista});' in texto
                if parche:
                    assert o.parche in texto or o.parche[:-1] in texto
                copia = estado.copiar(texto, conocidos)
                assert 'dbo.' not in re.sub(r'--[^\n]*', '', copia.texto), (o.id, v.id)
                nombre = latentes.nombre_de_copia(o, v, parche)
                assert nombre.startswith(f'{estado.ESQUEMA}.') and re.fullmatch(r'estado\.\w+', nombre)
                assert latentes.renombrar(copia.texto, nombre).count(f'CREATE PROCEDURE {nombre}') == 1
    with pytest.raises(NoSeCopia, match='exactamente una vez'):
        latentes.texto_de_variante('SELECT 1', R1_T1, latentes.MAXDOP1, False)


def test_ninguna_sentencia_toca_la_configuracion_ni_la_cache_del_servidor():
    """Las variantes van EN LA COPIA: nada de sp_configure, ALTER DATABASE ni vaciar toda la caché. Las estadísticas
    son de las tablas de `estado` y los planes se sacan de la caché uno por uno, sólo los de la copia."""
    for ruta in (RAIZ / 'corte' / 'latentes.py', RAIZ / 'corte' / 'latentes_ci.py'):
        texto = ruta.read_text(encoding='utf-8')
        assert not re.search(r"sp_configure|ALTER\s+DATABASE|DBCC\s+FREEPROCCACHE\s*(?:WITH|;|$)", texto, re.I | re.M)
    assert all(q.startswith(f'UPDATE STATISTICS {estado.ESQUEMA}.') for q in latentes_ci.ESTADISTICAS_MS.values())
    assert 'DBCC FREEPROCCACHE (@h)' in latentes.SACAR_PLAN
    assert "N'estado'" in latentes.PLANES_DE_LA_COPIA and "N':latentes:" in latentes.PLANES_DE_LA_COPIA
    # la consulta que busca los planes de la copia no se encuentra a sí misma: la marca va partida
    assert latentes.MARCA not in latentes.PLANES_DE_LA_COPIA


def test_el_lote_suelto_convierte_el_parametro_en_variable_local(modulos, conocidos):
    for o in latentes.OBJETOS:
        for v in (v for v in latentes.VARIANTES[o.id] if v.lote):
            texto, _r = latentes.texto_de_variante(modulos[o.id].texto, o, v, False)
            lote = latentes.lote_suelto(estado.copiar(texto, conocidos).texto, o, v, False)
            assert lote.startswith(f'/* {latentes.MARCA}:{o.id}:{v.sufijo} */')
            assert f'DECLARE {o.parametro} {o.tipo} = @entrada;' in lote
            assert 'CREATE' not in lote.upper().split('\n', 2)[1] and 'PROCEDURE' not in lote
            assert o.clave in lote and not lote.rstrip().upper().endswith('END')
            if v.pista:
                assert f'OPTION ({v.pista});' in lote
    with pytest.raises(NoSeCopia, match='un solo parámetro'):
        latentes.lote_suelto('CREATE PROCEDURE estado.x @a int, @b int AS BEGIN SELECT 1; END', R2_T2, latentes.LOTE,
                             False)


def test_el_conductor_corre_cada_entrada_con_la_guarda_y_captura_su_salida():
    for o in latentes.OBJETOS:
        for v in latentes.VARIANTES[o.id]:
            llamada = latentes.llamada_de(o, v, False)
            q = latentes.conductor(o, llamada, lote=v.lote)
            assert 'IF @@TRANCOUNT <> @t0' in q and q.rstrip().endswith('SELECT @t0, @@TRANCOUNT, @roto, @i - 1;')
            assert f'INSERT INTO #salida ({", ".join(f"[{c}]" for c, _t in o.salida)}) {llamada};' in q
            # el texto del lote suelto entra como UN parámetro, nunca pegado al texto
            assert q.count('%') == (1 if v.lote else 0)
            assert q.startswith('DECLARE @lote nvarchar(max) = %s;') == v.lote
            if v.lote:
                assert llamada.startswith('EXEC sp_executesql @lote')
            else:
                assert llamada.startswith(f'EXEC {estado.ESQUEMA}.')
    cargar = latentes.cargar_entradas(R1_T1)
    assert 'STRING_SPLIT(%s' in cargar and 'ORDER BY ordinal' in cargar


def test_la_muestra_del_pr_es_determinista_y_de_noche_corre_todo():
    lote = latentes.variante(R1_T1, 'lote suelto')
    assert latentes.cada_cuanto(R1_T1, lote, completo=False) == R1_T1.cada > 1
    assert latentes.cada_cuanto(R1_T1, lote, completo=True) == 1
    assert latentes.cada_cuanto(R1_T1, latentes.TAL_CUAL, completo=False) == 1
    forzada = latentes.variante(R2_T2, 'recorrido paralelo')
    assert latentes.cada_cuanto(R2_T2, forzada, completo=True) == forzada.cada > 1
    assert latentes.muestra(list(range(25)), 10) == [0, 10, 20]


# ── el plan real ────────────────────────────────────────────────────────────────────────────────────────────────

SHOWPLAN = ('<ShowPlanXML><QueryPlan NonParallelPlanReason="MaxDOPSetToOne"><ParameterList><ColumnReference '
            'Column="@fecha" ParameterCompiledValue="\'2021-01-01\'" /></ParameterList>'
            '<RelOp PhysicalOp="Nested Loops" EstimateRows="{e}" Parallel="false"><NestedLoops Optimized="1" '
            'WithUnorderedPrefetch="1"><RelOp PhysicalOp="Index Seek" EstimateRows="{e}" Parallel="false">'
            '<Object Database="[BFN_DIVISAS_CORTE]" Schema="[estado]" Table="[operacion]" Index="[ix_operacion_fecha]"'
            ' /></RelOp><RelOp PhysicalOp="Clustered Index Seek" EstimateRows="1" Parallel="false"><Object Database='
            '"[BFN_DIVISAS_CORTE]" Schema="[estado]" Table="[operacion]" Index="[pk_operacion]" /></RelOp>'
            '</NestedLoops></RelOp></QueryPlan></ShowPlanXML>')


def _fila(hash_, xml, handle='0x01', sentencia='SELECT @tc_cierre = tipo_cambio FROM estado.operacion'):
    return (hash_, 10, 1, 1, handle, sentencia, xml)


def test_el_showplan_dice_el_recorrido_el_orden_por_lotes_y_las_estimaciones():
    p = latentes.plan_de([_fila('0xD2B9', SHOWPLAN.format(e='227.26'))], R1_T1)
    assert p['visto'] and p['operadores'] == ['Nested Loops', 'Index Seek', 'Clustered Index Seek']
    assert p['indices'] == ['operacion.ix_operacion_fecha', 'operacion.pk_operacion'] and not p['paralelo']
    assert p['estimaciones'] == [227.26, 227.26, 1.0] and p['compilado_con'] == ["'2021-01-01'"]
    assert 'orden por lotes' in latentes.acceso(p) and 'estimación 227.26 filas' in latentes.acceso(p)
    assert p['no_paralelo'] == 'MaxDOPSetToOne'
    # una sentencia que no es la de la asignación no cuenta
    assert not latentes.plan_de([_fila('0x1', SHOWPLAN.format(e='1'), sentencia='SELECT 1')], R1_T1)['visto']


def test_el_mismo_query_plan_hash_con_otras_estimaciones_es_otro_plan():
    """Medido en el ensayo: el Nested Loops optimizado ordena las búsquedas por lotes según la estimación; dos
    compilaciones con el mismo query_plan_hash y otra estimación entregan otra fila al final. La identidad del plan
    lleva las estimaciones; la misma entrada de la caché, no cambia."""
    base = latentes.plan_de([_fila('0xD2B9', SHOWPLAN.format(e='53.0'))], R1_T1)
    otra = latentes.plan_de([_fila('0xD2B9', SHOWPLAN.format(e='102.0'), handle='0x02')], R1_T1)
    misma = latentes.plan_de([_fila('0xD2B9', SHOWPLAN.format(e='53.0'))], R1_T1)
    forma = latentes.plan_de([_fila('0x6A19', SHOWPLAN.format(e='53.0'))], R1_T1)
    assert latentes.plan_cambio(otra, base) and latentes.que_cambio(otra, base).startswith('las estimaciones')
    assert latentes.plan_cambio(misma, base) is False and latentes.que_cambio(misma, base) is None
    assert latentes.que_cambio(forma, base) == 'la forma (query_plan_hash)'
    assert latentes.plan_cambio({'visto': False}, base) is None


# ── la salida, la comparación y sus árbitros ────────────────────────────────────────────────────────────────────

def _pos(fecha, moneda, tc, compras='100.00', ventas='40.00'):
    pos = f'{float(compras) - float(ventas):.2f}'
    from decimal import ROUND_HALF_UP, Decimal
    mxn = (Decimal(pos) * Decimal(tc)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return (fecha, moneda, 'Nombre', compras, ventas, pos, tc, str(mxn))


def test_la_salida_va_por_unidad_y_una_unidad_repetida_es_un_error():
    s = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.177961'), _pos('2023-12-28', 'USD', '17.1')])
    assert set(s) == {('2023-12-28', 'CAD'), ('2023-12-28', 'USD')}
    assert s[('2023-12-28', 'CAD')][5] == '13.177961'
    with pytest.raises(NoSeCopia, match='dos veces'):
        latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '1'), _pos('2023-12-28', 'CAD', '2')])


def test_la_comparacion_cuenta_unidades_sobre_la_muestra():
    a = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.177961')])
    b = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.270531'), _pos('2023-12-27', 'CAD', '13.2')])
    c = latentes.comparar(R1_T1, a, b)
    assert c['distintas'] == 2 and c['columnas'] == {'tc_cierre,posicion_mxn': 1, '(la unidad falta en un lado)': 1}
    assert latentes.comparar(R1_T1, a, b, sobre={'2023-12-28'})['distintas'] == 1


def test_el_arbitro_de_r1_t1_exige_otra_operacion_del_mismo_dia_y_moneda():
    """El ejemplo del catálogo: CAD el 28-dic-2023, 13.177961 por fecha contra 13.270531 por id."""
    cand = latentes.candidatos(R1_T1, [('2023-12-28', 'CAD', '13.177961'), ('2023-12-28', 'CAD', '13.270531')])
    a = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.270531')])
    b = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.177961')])
    k = [('2023-12-28', 'CAD')]
    assert latentes.arbitrar(R1_T1, a, b, k, cand) == {
        'explicadas': 1, 'sin_explicar': 0, 'muestra_sin_explicar': [], 'clase': latentes.DEFECTO_LEGADO}
    # un tipo de cambio que no es de ninguna operación de ese día y moneda: defecto nuestro
    otro = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.5')])
    assert latentes.arbitrar(R1_T1, otro, b, k, cand)['clase'] == latentes.DEFECTO_NUESTRO
    # una diferencia fuera de lo que alimenta la variable (las compras): defecto nuestro
    compras = latentes.por_unidad(R1_T1, [_pos('2023-12-28', 'CAD', '13.270531', compras='101.00')])
    assert latentes.arbitrar(R1_T1, compras, b, k, cand)['sin_explicar'] == 1
    # la derivada que no sigue a la variable (posicion_mxn de otro tipo de cambio): defecto nuestro
    fila = list(_pos('2023-12-28', 'CAD', '13.270531'))
    fila[7] = '999.99'
    assert latentes.arbitrar(R1_T1, latentes.por_unidad(R1_T1, [tuple(fila)]), b, k, cand)['sin_explicar'] == 1


def test_el_arbitro_de_r2_t2_exige_otra_orden_de_la_misma_operacion():
    op = ('F1', 'Cliente', 'USD', '10', '170')
    vigente = ('OP-2', 'U1', 'CONCILIADA', '2023-12-28 10:00:00.000')
    vieja = ('OP-1', 'U1', 'REEMPLAZADA', '2023-12-27 10:00:00.000')
    cand = latentes.candidatos(R2_T2, [(7, *vigente), (7, *vieja)])
    legado = latentes.por_unidad(R2_T2, [(7, *op, *vieja)])
    tobe = latentes.por_unidad(R2_T2, [(7, *op, *vigente)])
    assert latentes.arbitrar(R2_T2, legado, tobe, [('7',)], cand)['clase'] == latentes.DEFECTO_LEGADO
    ajena = latentes.por_unidad(R2_T2, [(7, *op, 'OP-9', 'U9', 'ENVIADA', None)])
    assert latentes.arbitrar(R2_T2, ajena, tobe, [('7',)], cand)['clase'] == latentes.DEFECTO_NUESTRO


# ── la aceptación ───────────────────────────────────────────────────────────────────────────────────────────────

def _corrida(distintas=0, tobe=0, huellas=('h1',), handles=('0x1',), cambio=None, no_compila=False, que=None):
    return {'entradas': 10, 'cada': 1, 'segundos': 1.0, 'no_compila': no_compila,
            'plan': {'visto': True, 'hashes': ['0x1'], 'huellas': list(huellas), 'handles': list(handles),
                     'operadores': [], 'indices': [], 'estimaciones': [], 'nested_loops': [], 'last_dop': 1},
            'plan_cambio': cambio, 'que_cambio': que,
            'contra_tal_cual': {'distintas': distintas, 'unidades': 10, 'columnas': {}},
            'contra_tobe': {'distintas': tobe, 'unidades': 10, 'columnas': {}}, 'arbitraje': {}}


def _parche_ok(objeto):
    return {v.id: _corrida() for v in latentes.con_parche(objeto)}


def test_detectada_si_una_variante_natural_cambia_el_plan_y_la_salida_y_el_parche_hace_coincidir_todo():
    corridas = {'tal cual': _corrida(), 'tal cual, otra vez': _corrida(cambio=False),
                'MAXDOP 4': _corrida(cambio=False), 'estadísticas y caché': _corrida(5, 0, ('h2',), cambio=True)}
    v = latentes.veredicto(R1_T1, corridas, _parche_ok(R1_T1))
    assert v['estado'] == 'detectada con el plan variado' and v['detectada'] and v['manifiestan'] == [
        'estadísticas y caché']
    assert v['controles']['mismo_plan_no_detecta']['detectado'] and v['controles']['parche']['detectado']
    assert v['controles']['mismo_plan_no_detecta']['variantes_con_el_mismo_plan'] == ['tal cual, otra vez',
                                                                                     'MAXDOP 4']
    assert latentes.faltas_de(R1_T1, v) == []
    # sin el parche que haga coincidir todo, no es detección: no concluyente
    malo = {**_parche_ok(R1_T1), 'MAXDOP 4': _corrida(distintas=1)}
    assert latentes.veredicto(R1_T1, corridas, malo)['estado'].startswith('no concluyente')


def test_una_variante_con_el_mismo_plan_no_detecta_aunque_cambie_la_salida():
    corridas = {'tal cual': _corrida(), 'tal cual, otra vez': _corrida(cambio=False),
                'MAXDOP 1': _corrida(distintas=3, cambio=False)}
    v = latentes.veredicto(R1_T1, corridas, _parche_ok(R1_T1))
    assert not v['detectada'] and v['manifiestan'] == []
    assert v['controles']['mismo_plan_no_detecta']['con_el_mismo_plan_y_otra_salida'] == ['MAXDOP 1']
    faltas = latentes.faltas_de(R1_T1, v)
    assert any('no es del plan' in f for f in faltas) and any('ninguna variante cambió el plan' in f for f in faltas)
    # la caché repetida con otra entrada de la caché tampoco vale como control
    otra = {**corridas, 'tal cual, otra vez': _corrida(cambio=False, handles=('0x2',))}
    assert not latentes.veredicto(R1_T1, otra, _parche_ok(R1_T1))['controles']['mismo_plan_no_detecta']['detectado']


def test_solo_forzada_o_sin_manifestarse_no_cuentan_como_detectada():
    base = {'tal cual': _corrida(), 'tal cual, otra vez': _corrida(cambio=False),
            'lote suelto': _corrida(huellas=('h3',), cambio=True)}
    forzada = {**base, 'recorrido paralelo': _corrida(7, 7, ('h4',), cambio=True)}
    v = latentes.veredicto(R2_T2, forzada, _parche_ok(R2_T2))
    assert v['estado'] == 'sólo forzada (pista en la copia)' and not v['detectada']
    assert v['forzadas_que_manifiestan'] == ['recorrido paralelo']
    v = latentes.veredicto(R2_T2, {**base, 'HASH JOIN': _corrida(no_compila=True)}, _parche_ok(R2_T2))
    assert v['estado'] == 'no se manifiesta' and not v['detectada'] and v['no_aplican'] == ['HASH JOIN']
    assert v['plan_cambio_en'] == ['lote suelto'] and latentes.faltas_de(R2_T2, v) == []


def test_una_diferencia_sin_explicar_deja_el_job_en_rojo():
    c = _corrida(5, 0, ('h2',), cambio=True)
    c['arbitraje'] = {'contra la copia tal cual': {'explicadas': 4, 'sin_explicar': 1, 'muestra_sin_explicar': [['x']],
                                                   'clase': latentes.DEFECTO_NUESTRO}}
    v = latentes.veredicto(R1_T1, {'tal cual': _corrida(), 'tal cual, otra vez': _corrida(cambio=False),
                                   'lote suelto': c}, _parche_ok(R1_T1))
    assert any('defecto nuestro' in f for f in latentes.faltas_de(R1_T1, v))


# ── el TO-BE y el control por dato ──────────────────────────────────────────────────────────────────────────────

def test_el_tobe_para_todas_las_entradas_es_su_consulta_del_oraculo():
    for o, parametro in ((R1_T1, '%(fecha)s'), (R2_T2, '%(op)s')):
        consulta = oraculo.TOBE[o.id][0]
        q = latentes.tobe_para_todas(o, consulta)
        assert parametro not in q and 'unnest(%(entradas)s::' in q
        # lo que el TO-BE decide sigue igual: el orden explícito y la vigente
        for regla in ('ORDER BY moneda, fecha_operacion DESC, id DESC',
                      "q.estatus <> 'REEMPLAZADA' ORDER BY q.id DESC"):
            assert (regla in q) == (regla in consulta)
    with pytest.raises(NoSeCopia):
        latentes.tobe_para_todas(R2_T2, 'SELECT 1')
    assert all(ddl.startswith('CREATE INDEX ON legado.') for ddl in latentes.INDICES_TOBE)


def test_el_control_por_dato_hace_que_la_vigente_deje_de_ser_la_ultima():
    que, cambio = latentes.CONTROL_DE_DATO[R2_T2.id]
    assert 'REEMPLAZADA' in que and 'revertida' in que
    assert f'FROM {estado.ESQUEMA}.orden_pago' in cambio and 'dbo.' not in cambio
    assert "CASE n WHEN 1 THEN 'REEMPLAZADA' ELSE vigente END WHERE n IN (1, 2)" in cambio
    assert 'SESSION_CONTEXT' not in cambio and 'sp_set_session_context' in latentes.RELOJ_DE_LA_COPIA
    assert R1_T1.id not in latentes.CONTROL_DE_DATO


# ── el job ──────────────────────────────────────────────────────────────────────────────────────────────────────

def test_el_job_de_latentes_corre_en_pr_y_de_noche_con_su_alcance_y_su_memoria():
    w = yaml.safe_load(CARGA.read_text(encoding='utf-8'))
    job = w['jobs']['latentes']
    assert 'if' not in job                                   # PR, noche y a mano
    assert "'pr' || 'completo'" in job['env']['ALCANCE']
    pasos = '\n'.join(str(p.get('run', '')) for p in job['steps'])
    assert 'python -m corte.latentes_ci' in pasos and '--completo' in pasos and '/usr/bin/time -v' in pasos
    assert '--memory 1g' in pasos and 'memory.peak' in pasos and 'docker rm -f -v decant-pg-latentes' in pasos
    assert 'DECANT_ORACULO' not in pasos                     # no captura el oráculo: no lo necesita
