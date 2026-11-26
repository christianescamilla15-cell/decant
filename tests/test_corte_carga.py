"""Carga histórica por mes (S3 paso 3, ADR 0013; criterios 4, 5, 6 y 12), sin base. El plan se arma con las filas
REALES del generador: el GROUP BY por mes que en el CI hace SQL Server se reproduce aquí como oráculo independiente
(mes de la hora local del sello de cada fila), y el plan, la huella y las guardas son el código de `corte/carga.py`.
Lo que necesita las dos bases (aplicar, reversa, controles) corre en el CI (`corte/carga_ci.py`)."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from corte import carga, runbook
from legado.generador.simulacion import COLUMNAS

RAIZ = Path(__file__).resolve().parent.parent
LEGADO_SQL = (RAIZ / 'legado' / 'sql' / '02_tablas.sql').read_text(encoding='utf-8')
DESTINO_SQL = (RAIZ / 'corte' / 'destino.sql').read_text(encoding='utf-8')


def columnas_de(ddl: str, tabla: str) -> list[tuple[str, str, bool]]:
    """(columna, tipo, admite NULL) de un CREATE TABLE, en orden."""
    cuerpo = re.search(rf'CREATE TABLE {re.escape(tabla)} \((.*?)\n\);', ddl, re.S).group(1)
    resultado = []
    for renglon in cuerpo.splitlines():
        renglon = renglon.split('--')[0].strip().rstrip(',')
        m = re.match(r'(\w+)\s+(\w+(?:\s*\([\d,\s]+\))?)(.*)$', renglon)
        if m and m.group(1).upper() not in ('CONSTRAINT', 'PRIMARY'):
            resultado.append((m.group(1), re.sub(r'\s+', '', m.group(2)).lower(), 'NOT NULL' not in m.group(3)))
    return resultado


# ── la especificación y el destino ──────────────────────────────────────────────────────────────────────────────

def test_la_especificacion_de_las_7_tablas_es_la_del_legado():
    """Columnas, tipos y nulos de `carga.TABLAS` = `legado/sql/02_tablas.sql`, y el orden = el del generador."""
    assert set(carga.TABLAS) == set(COLUMNAS)
    for t in carga.TABLAS.values():
        legado = [(c, tipo, nula) for c, tipo, nula in columnas_de(LEGADO_SQL, t.origen)]
        assert [(c.nombre, c.tipo, c.nula) for c in t.columnas] == legado, t.nombre
        assert t.nombres == COLUMNAS[t.nombre]
        assert t.identidad == (t.nombres[0] == 'id')


TIPO_EXACTO = {'int': 'integer', 'bigint': 'bigint', 'smallint': 'smallint', 'tinyint': 'smallint', 'bit': 'boolean',
               'date': 'date', 'datetime': 'timestamp', 'smalldatetime': 'timestamp', 'sysname': 'varchar(128)'}


def tipo_en_postgres(tipo: str) -> str:
    if tipo in TIPO_EXACTO:
        return TIPO_EXACTO[tipo]
    nombre, _, args = tipo.partition('(')
    return {'char': 'char', 'varchar': 'varchar', 'nvarchar': 'varchar', 'decimal': 'numeric'}[nombre] + '(' + args


def test_el_destino_guarda_los_valores_crudos_con_tipos_que_los_conservan():
    """char(n) sigue siendo char(n) (con su relleno), los centinelas caben donde estaban (NOT NULL como en el legado) y
    cada decimal conserva su escala. La única diferencia declarada: folio.actualizado se copia en el cierre."""
    for t in carga.TABLAS.values():
        destino = columnas_de(DESTINO_SQL, t.destino)
        assert [c for c, *_ in destino] == list(t.nombres), t.nombre
        for c, (nombre, tipo, nula) in zip(t.columnas, destino):
            assert tipo == tipo_en_postgres(c.tipo), (t.nombre, nombre, tipo)
            esperado = True if (t.nombre, nombre) == ('folio', 'actualizado') else c.nula
            assert nula == esperado, (t.nombre, nombre)


def test_los_indices_unicos_del_destino_son_las_llaves_primarias_del_legado():
    def llaves(ddl: str, esquema: str) -> dict[str, str]:
        return {t: re.search(rf'CREATE TABLE {esquema}\.{t} \(\s*(\w+)[^\n]*\n?[^\n]*PRIMARY KEY', ddl).group(1)
                for t in carga.TABLAS}
    assert llaves(LEGADO_SQL, 'dbo') == llaves(DESTINO_SQL, 'legado')
    assert 'UNIQUE' not in LEGADO_SQL.upper() and 'UNIQUE' not in DESTINO_SQL.upper()
    filas = [('operacion', 'pk_operacion', 'id', 1), ('moneda', 'pk_moneda', 'codigo', 1)]
    assert carga.indices_unicos(filas) == {'moneda': [['codigo']], 'operacion': [['id']]}
    assert carga.indices_unicos(filas) != carga.indices_unicos([*filas, ('orden_pago', 'ux', 'uetr', 1)])


def test_las_consultas_leen_las_columnas_de_la_especificacion_en_orden():
    for t in carga.CON_IDENTIDAD:
        for consultas in (carga.POR_RANGO, carga.POR_SELLO):
            lista = re.search(r'SELECT (.*?)\nFROM', consultas[t.nombre], re.S).group(1)
            nombres = tuple(c.strip().removeprefix('s.') for c in lista.replace('\n', ' ').split(','))
            assert nombres == t.nombres, (t.nombre, nombres)
        for consulta in (carga.PLAN[t.nombre], carga.TOTALES[t.nombre], carga.POR_SELLO[t.nombre]):
            assert '%(corte)s' in consulta                     # nunca más allá del corte medido
        assert f"N'dbo.{t.nombre}'" in carga.IDENT_CURRENT[t.nombre]


def test_los_interruptores_son_las_banderas_del_to_be():
    opciones = (RAIZ / 'src' / 'Decant.Application' / 'Opciones.cs').read_text(encoding='utf-8')
    banderas = re.findall(r'bool (\w+)', re.search(r'record Banderas\((.*?)\)', opciones).group(1))
    semilla = re.search(r'INSERT INTO corte\.interruptor .*?;', DESTINO_SQL, re.S).group(0)
    sembrados = re.findall(r"\('(\w+)'\)", semilla)
    assert sembrados == banderas == ['VencerAutomatico', 'ConciliarAutomatico', 'NotificarCorresponsal']


def test_los_roles_separan_insertar_de_borrar():
    """aplicar sólo inserta en las tablas del legado; reversa sólo borra; ninguno toca el punto de no retorno."""
    insert = re.search(r'GRANT INSERT ON (.*?) TO decant_corte_aplica;', DESTINO_SQL, re.S).group(1)
    delete = re.search(r'GRANT DELETE ON (.*?) TO decant_corte_revierte;', DESTINO_SQL, re.S).group(1)
    assert insert == delete
    assert {x.strip() for x in insert.split(',')} == {t.destino for t in carga.CON_IDENTIDAD}
    assert not re.search(r'GRANT[^;]*(UPDATE|DELETE)[^;]*ON[^;]*legado\.(operacion|orden_pago|partida|bitacora)'
                         r'[^;]*TO[^;]*aplica', DESTINO_SQL)
    assert not re.search(r'GRANT[^;]*no_retorno', DESTINO_SQL)


# ── el plan, con las filas reales del generador ─────────────────────────────────────────────────────────────────

def _sellos(t: dict) -> dict[str, list[tuple[int, datetime, Decimal | None]]]:
    """El oráculo del GROUP BY del CI: (id, sello local, monto) de cada fila, con el sello que declara cada tabla."""
    liquidacion = {b[2]: b[7] for b in t['bitacora'] if b[3] == 'U' and b[5] == 'LIQUIDADA'}
    return {'operacion': [(f[0], f[2], f[12]) for f in t['operacion']],
            'orden_pago': [(f[0], f[5], f[13]) for f in t['orden_pago']],
            'partida_solicitada': [(f[0], liquidacion[f[1]], f[5]) for f in t['partida_solicitada']],
            'partida_liquidada': [(f[0], f[6], f[5]) for f in t['partida_liquidada']],
            'bitacora': [(f[0], f[7], None) for f in t['bitacora']]}


def agregados(t: dict, grieta: str | None = None) -> tuple[dict, dict, dict]:
    ventana = carga.ventana_grieta(grieta)
    resultado, totales, cortes = {}, {}, {}
    for tabla, filas in _sellos(t).items():
        por_mes: dict[str, list] = defaultdict(list)
        for id_, sello, monto in filas:
            en_ventana = ventana['grieta_desde'] <= sello < ventana['grieta_hasta']
            por_mes[ventana['grieta_mes'] if en_ventana else f'{sello.year:04d}-{sello.month:02d}'].append((id_, monto))
        resultado[tabla] = [(m, min(i for i, _ in v), max(i for i, _ in v), len(v),
                             None if v[0][1] is None else sum(x for _, x in v)) for m, v in por_mes.items()]
        ids = [f[0] for f in filas]
        montos = [x for _, _, x in filas if x is not None]
        totales[tabla] = (len(ids), max(ids), sum(montos) if montos else None)
        cortes[tabla] = max(ids)
    return resultado, totales, cortes


@pytest.fixture(scope='module')
def tres_anios(datos):
    a, totales, cortes = agregados(datos.tablas)
    g, _, _ = agregados(datos.tablas, grieta=carga.GRIETA)
    return {'plan': carga.plan(a, totales, cortes), 'grieta': carga.plan(g, totales, cortes, grieta=carga.GRIETA),
            'totales': totales}


def test_los_36_meses_son_rangos_contiguos_que_cubren_hasta_el_corte(tres_anios):
    p = tres_anios['plan']
    assert p['faltas'] == []
    assert p['meses'] == list(carga.MESES) and len(p['meses']) == 36
    for t, d in p['tablas'].items():
        meses = [d['meses'][m] for m in carga.MESES]
        assert meses[0]['desde'] == 0 and meses[-1]['hasta'] == d['corte'] == tres_anios['totales'][t][1]
        assert all(meses[i]['desde'] == meses[i - 1]['hasta'] for i in range(1, 36))
        assert all(m['filas'] > 0 and m['hasta'] - m['desde'] >= m['filas'] for m in meses)
    assert carga.rangos(p, '2021-01')['operacion'] == {'desde': 0, 'hasta': 9696, 'filas': 9696,
                                                       'monto': p['tablas']['operacion']['meses']['2021-01']['monto']}


def test_si_un_mes_se_encima_con_otro_no_hay_plan(datos_chicos):
    """Control negativo: una fila de marzo con un id entre los de abril (lo que haría una alta fechada hacia atrás)."""
    a, totales, cortes = agregados(datos_chicos.tablas)
    meses = ('2021-03', '2021-04')
    assert carga.plan(a, totales, cortes, meses=meses)['faltas'] == []
    marzo = next(x for x in a['operacion'] if x[0] == '2021-03')
    abril = next(x for x in a['operacion'] if x[0] == '2021-04')
    a['operacion'] = [(m, lo, abril[2] - 1 if m == '2021-03' else hi, n, s) for m, lo, hi, n, s in a['operacion']]
    faltas = carga.plan(a, totales, cortes, meses=meses)['faltas']
    assert faltas and 'operacion: 2021-04' in faltas[0] and 'se enciman' in faltas[0]
    assert marzo[2] < abril[1]


def test_si_una_fila_no_tiene_sello_los_meses_no_suman_el_origen(datos_chicos):
    a, totales, cortes = agregados(datos_chicos.tablas)
    totales['partida_solicitada'] = (totales['partida_solicitada'][0] + 1, *totales['partida_solicitada'][1:])
    faltas = carga.plan(a, totales, cortes, meses=('2021-03', '2021-04'))['faltas']
    assert any('partida_solicitada: los meses suman' in f for f in faltas)


def test_la_grieta_utc_mueve_la_ultima_noche_y_los_totales_globales_no_la_ven(tres_anios):
    """Criterio 6, del lado del plan: el fin de octubre de 2022 en UTC manda a noviembre lo de las 18:00 en adelante
    del 31; cada mes cambia y la suma de los 36 meses, no. En `operacion` además el plan se encima: su sello es la
    fecha de NEGOCIO y las altas por archivo de las 22:00 (ids mayores) traen horas del día, que se quedan en octubre,
    mientras las de ventanilla de las 18:00 en adelante (ids menores) se van a noviembre."""
    bueno, grieta = tres_anios['plan'], tres_anios['grieta']
    assert grieta['sha'] != bueno['sha']
    assert len(grieta['faltas']) == 1 and grieta['faltas'][0].startswith('operacion: 2022-11 empieza en el id')
    assert carga.totales_del_plan(bueno) == carga.totales_del_plan(grieta)
    octubre = {t: (bueno['tablas'][t]['meses'][carga.GRIETA], grieta['tablas'][t]['meses'][carga.GRIETA])
               for t in bueno['tablas']}
    movidas = {t: b['filas'] - g['filas'] for t, (b, g) in octubre.items()}
    assert movidas == {'operacion': 39, 'orden_pago': 61, 'partida_liquidada': 201, 'partida_solicitada': 0,
                       'bitacora': 381}
    siguiente = carga.siguiente(carga.GRIETA)
    for t, n in movidas.items():
        assert grieta['tablas'][t]['meses'][siguiente]['filas'] - bueno['tablas'][t]['meses'][siguiente]['filas'] == n
        assert grieta['tablas'][t]['meses'][carga.GRIETA]['desde'] == bueno['tablas'][t]['meses'][carga.GRIETA]['desde']


def test_la_ventana_de_la_grieta_es_la_hora_local_en_que_en_utc_ya_es_otro_mes():
    assert carga.ventana_grieta(None)['grieta_desde'] == carga.ventana_grieta(None)['grieta_hasta']
    assert carga.ventana_grieta('2022-10') == {'grieta_desde': datetime(2022, 10, 31, 18, 0),
                                               'grieta_hasta': datetime(2022, 11, 1), 'grieta_mes': '2022-11'}
    assert carga.ventana_grieta('2021-06')['grieta_desde'] == datetime(2021, 6, 30, 19, 0)    # horario de verano
    assert carga.ventana_grieta('2023-12')['grieta_mes'] == '2024-01'
    assert carga.frontera('2023-12') == (datetime(2023, 12, 1), datetime(2024, 1, 1))


# ── huellas ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_la_huella_del_mes_no_normaliza_nada(datos_chicos):
    """Los valores CRUDOS: el relleno de un char(n), el centinela «NA» y la escala de un decimal cuentan. El orden de
    llegada no."""
    t = carga.TABLAS['orden_pago']
    filas = list(datos_chicos.tablas['orden_pago'][:200])
    base = carga.huella_de_filas(t, filas)
    assert carga.huella_de_filas(t, list(reversed(filas))) == base
    assert base['filas'] == 200 and base['primero'] == 1 and base['ultimo'] == 200
    i = next(k for k, f in enumerate(filas) if f[9] == 'NA')
    columna = t.nombres.index('bic_intermediario')
    for cambio in ('NA         ', None, 'N/A'):          # el relleno del char(11), el NULL del TO-BE, otro centinela
        otra = [*filas[:i], (*filas[i][:columna], cambio, *filas[i][columna + 1:]), *filas[i + 1:]]
        assert carga.huella_de_filas(t, otra)['huella'] != base['huella'], cambio
    monto = t.nombres.index('monto')
    escala = [(*filas[0][:monto], filas[0][monto].quantize(Decimal('0.001')), *filas[0][monto + 1:]), *filas[1:]]
    assert carga.huella_de_filas(t, escala)['huella'] != base['huella']


def test_comparar_mes_y_la_huella_previa_nombran_lo_distinto():
    a = {'operacion': {'filas': 2, 'huella': 'a' * 64}, 'orden_pago': {'filas': 1, 'huella': 'b' * 64}}
    b = {**a, 'orden_pago': {'filas': 0, 'huella': 'c' * 64}}
    assert carga.comparar_mes(a, a) == []
    assert [f.split(':')[0] for f in carga.comparar_mes(a, b)] == ['orden_pago']
    previa = {'tablas': {'operacion': {'filas': 0}}, 'secuencias': {'operacion': {'last_value': 1, 'is_called': False}}}
    sin_setval = {**previa, 'secuencias': {'operacion': {'last_value': 9696, 'is_called': True}}}
    assert carga.diferencias_de_huella(previa, previa) == []
    assert carga.diferencias_de_huella(previa, sin_setval) == [
        "secuencia operacion: {'last_value': 1, 'is_called': False} → {'last_value': 9696, 'is_called': True}"]


# ── guardas, consumibles y reversa ──────────────────────────────────────────────────────────────────────────────

def test_el_corte_del_destino_se_mide_por_dos_caminos():
    vacio = {t.nombre: None for t in carga.CON_IDENTIDAD}
    assert carga.corte_del_destino(vacio, {}) == ({t.nombre: 0 for t in carga.CON_IDENTIDAD}, [])
    corte, faltas = carga.corte_del_destino({**vacio, 'operacion': 9696}, {})
    assert corte['operacion'] == 9696 and faltas == ['operacion: MAX(id) del destino 9696 ≠ el del registro de meses 0']


def test_solo_ids_mayores_al_corte():
    rango = {'operacion': {'desde': 9696, 'hasta': 18000, 'filas': 8304},
             'bitacora': {'desde': 5, 'hasta': 5, 'filas': 0}}
    assert carga.guarda_de_rangos(rango, {'operacion': 9696, 'bitacora': 99}) == []
    assert carga.guarda_de_rangos(rango, {'operacion': 18000, 'bitacora': 0})[0].startswith('operacion: el mes empieza')
    assert carga.ids_fuera([9697, 18000], 9696, 18000, 9696) == []
    assert carga.ids_fuera([9696, 9697, 18001], 9696, 18000, 9000) == [9696, 18001]
    assert carga.ids_fuera([9697], 0, 18000, 9697) == [9697]          # el corte del destino manda sobre el plan


def test_los_folios_del_lote_son_el_mayor_usado_mas_uno(datos_chicos):
    lote = {'operacion': datos_chicos.tablas['operacion'][:50], 'orden_pago': datos_chicos.tablas['orden_pago'][:30]}
    folios = carga.folios_del_lote(lote)
    assert folios['FX'] == 51
    assert folios['OP'] == max(int(f[2][3:]) for f in lote['orden_pago']) + 1
    assert carga.numero_de_folio('FX-000000123', 'FX') == 123 and carga.numero_de_folio('OP-1', 'FX') is None


def test_la_reversa_se_genera_antes_con_rangos_secuencias_folios_y_huella_previa(tres_anios):
    p = tres_anios['plan']
    previa = {'tablas': {'operacion': {'filas': 0, 'max_id': None, 'huella': 'x'}},
              'secuencias': {t.nombre: {'last_value': 1, 'is_called': False} for t in carga.CON_IDENTIDAD},
              'folios': {'FX': {'siguiente': 1, 'actualizado': None}, 'OP': {'siguiente': 1, 'actualizado': None}}}
    rev = carga.reversa('2023-12', p, previa)
    assert rev['plan_sha'] == p['sha'] and rev['mes'] == '2023-12'
    assert rev['borrar'] == {t: {'desde': d['meses']['2023-12']['desde'], 'hasta': d['meses']['2023-12']['hasta']}
                             for t, d in p['tablas'].items()}
    assert rev['secuencias'] == previa['secuencias'] and rev['folios'] == {'FX': 1, 'OP': 1}
    assert rev['huella_previa'] == {'tablas': previa['tablas'], 'secuencias': previa['secuencias']}
    json.dumps(rev)                                        # se guarda tal cual (archivo y jsonb)


def test_el_corte_de_la_carga_es_el_medido_en_el_paso_2(tmp_path):
    medido = runbook.CORTE_MEDIDO
    cortes = runbook.cortes(None)
    assert cortes == {'bitacora': 685276, 'operacion': 412125, 'orden_pago': 270616, 'partida_liquidada': 893174,
                      'partida_solicitada': 244869}
    manifiesto = tmp_path / 'respaldo.json'
    manifiesto.write_text(json.dumps({'tablas': {f'dbo.{t}': {'filas': n, 'max_id': n} for t, n in cortes.items()}}))
    assert runbook.cortes(manifiesto, medido) == cortes
    manifiesto.write_text(json.dumps({'tablas': {f'dbo.{t}': {'max_id': n + (t == 'operacion')}
                                                 for t, n in cortes.items()}}))
    with pytest.raises(runbook.Negado, match='no es el medido por dos caminos'):
        runbook.cortes(manifiesto, medido)
