"""Detectores por patrón sobre código T-SQL. Los casos positivos y negativos salen del legado, de la base pública
de control (WideWorldImporters) o de formas reales de T-SQL que confundían al analizador."""
from __future__ import annotations

import re
from pathlib import Path

from legado.conexion import lotes
from legado.generador.simulacion import COLUMNAS
from radiografia import patrones
from radiografia.patrones import Modulo
from radiografia.tsql import fichas


def _m(texto: str, nombre: str = 'dbo.p') -> Modulo:
    return Modulo(nombre, 'PROCEDIMIENTO', texto)


def _categorias(hallazgos):
    return [h['categoria'] for h in hallazgos]


# ── analizador léxico ───────────────────────────────────────────────────────────────────────────────────────

def test_comentarios_y_cadenas_no_cuentan_como_codigo():
    fs = fichas("-- SELECT TOP 1 x\n/* GETDATE() */ SELECT 'TOP 1 ORDER BY', N'Ñ' FROM [dbo].[t]")
    assert [f.texto for f in fs if f.tipo == 'ident'] == ['SELECT', 'FROM', 'dbo', 't']
    assert fs[0].linea == 2


def test_el_else_y_el_end_de_un_case_no_abren_ni_cierran_sentencias():
    fs = fichas('SELECT CASE WHEN a = 1 THEN 2 ELSE 3 END AS x FROM t ORDER BY x')
    marcados = [f.texto for f in fs if f.en_caso]
    assert marcados[0] == 'CASE' and marcados[-1] == 'END' and 'ELSE' in marcados


# ── TOP sin ORDER BY ────────────────────────────────────────────────────────────────────────────────────────

def test_top_sin_order_by_se_detecta():
    h = patrones.top_sin_order_by(_m('SELECT TOP (200) id FROM dbo.operacion WHERE fecha >= @f;'))
    assert _categorias(h) == ['top_sin_order_by']


def test_top_con_order_by_tras_un_case_no_se_detecta():
    # regresión del control público: Website.SearchForPeople tiene ORDER BY después de un CASE … END
    texto = ('SELECT TOP(@n) p.id, CASE WHEN p.a <> 0 THEN N\'x\' WHEN c.id IS NOT NULL THEN N\'y\' END AS r '
             'FROM p LEFT OUTER JOIN c ON c.p = p.id WHERE p.n LIKE N\'%\' + @s + N\'%\' ORDER BY p.n FOR JSON AUTO')
    assert patrones.top_sin_order_by(_m(texto)) == []


def test_top_dentro_de_exists_no_importa_el_orden():
    assert patrones.top_sin_order_by(_m('IF EXISTS (SELECT TOP 1 1 FROM t) RETURN')) == []


def test_top_con_sugerencia_de_tabla_y_order_by_no_se_detecta():
    assert patrones.top_sin_order_by(_m('SELECT TOP 5 a FROM t WITH (NOLOCK) ORDER BY a')) == []


def test_top_que_asigna_variables_se_marca_como_tal():
    h = patrones.top_sin_order_by(_m('SELECT TOP 1 @id = id FROM dbo.orden_pago WHERE uetr = @u'))
    assert h[0]['asigna_variable'] is True


def test_update_top_siempre_es_arbitrario():
    assert _categorias(patrones.top_sin_order_by(_m('UPDATE TOP (10) t SET a = 1'))) == ['top_sin_order_by']


# ── INNER JOIN a una tabla hija ─────────────────────────────────────────────────────────────────────────────

PADRES = {'dbo.partida': {'dbo.orden'}, 'sales.customers': {'sales.customers'}}


def test_inner_join_del_padre_a_la_hija_se_detecta():
    h = patrones.inner_join_hija(_m('SELECT * FROM dbo.orden o INNER JOIN dbo.partida p ON p.orden_id = o.id'),
                                 PADRES)
    assert h[0]['padre'] == 'dbo.orden' and h[0]['hija'] == 'dbo.partida'


def test_join_sin_calificar_tambien_es_inner():
    assert patrones.inner_join_hija(_m('SELECT * FROM orden o JOIN partida p ON p.orden_id = o.id'), PADRES)


def test_left_join_y_join_de_hija_a_padre_no_se_detectan():
    assert patrones.inner_join_hija(_m('SELECT * FROM orden o LEFT JOIN partida p ON p.o = o.id'), PADRES) == []
    assert patrones.inner_join_hija(_m('SELECT * FROM partida p INNER JOIN orden o ON p.o = o.id'), PADRES) == []


def test_llave_foranea_a_si_misma_no_se_detecta():
    # regresión del control público: Sales.Customers → Sales.Customers (cliente que paga)
    texto = 'SELECT * FROM Sales.Customers AS c INNER JOIN Sales.Customers AS bt ON bt.id = c.BillToCustomerID'
    assert patrones.inner_join_hija(_m(texto), PADRES) == []


# ── reloj del servidor en una regla ─────────────────────────────────────────────────────────────────────────

def test_getdate_en_el_where_es_regla():
    texto = "UPDATE dbo.o SET estatus = 'VENCIDA' WHERE estatus = 'ENVIADA' AND f < DATEADD(day, -3, GETDATE())"
    assert _categorias(patrones.reloj_en_regla(_m(texto))) == ['reloj_en_regla']


def test_getdate_en_case_when_e_if_es_regla():
    assert patrones.reloj_en_regla(_m('SET @x = CASE WHEN GETDATE() > @f THEN 1 ELSE 0 END'))
    assert patrones.reloj_en_regla(_m('IF DATEDIFF(day, @f, SYSDATETIME()) > 3 RETURN'))


def test_getdate_como_sello_de_auditoria_no_es_regla():
    # la bitácora y los consumibles sellan la hora: no deciden nada (formas del legado y de WideWorldImporters)
    assert patrones.reloj_en_regla(_m("INSERT INTO b (a, f) SELECT 'x', GETDATE() FROM inserted")) == []
    assert patrones.reloj_en_regla(_m("UPDATE dbo.folio SET n = n + 1, actualizado = GETDATE() WHERE s = 'FX'")) == []
    assert patrones.reloj_en_regla(_m('INSERT t (a, b) VALUES (@a, SYSDATETIME())')) == []


# ── IF EXISTS sin ELSE ──────────────────────────────────────────────────────────────────────────────────────

LIQUIDACION = """IF EXISTS (SELECT 1 FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA')
BEGIN
    INSERT INTO dbo.partida (a) VALUES (1);
    UPDATE dbo.orden_pago SET estatus = 'LIQUIDADA' WHERE id = @id;
END"""


def test_if_exists_sin_else_que_escribe_es_camino_silencioso():
    assert _categorias(patrones.if_exists_sin_else(_m(LIQUIDACION))) == ['if_exists_sin_else']


def test_if_exists_con_else_no_se_detecta():
    assert patrones.if_exists_sin_else(_m(LIQUIDACION + "\nELSE RAISERROR('no existe', 16, 1)")) == []


def test_if_exists_con_case_dentro_del_bloque_encuentra_su_else():
    texto = "IF EXISTS (SELECT 1 FROM t) BEGIN UPDATE t SET a = CASE WHEN b = 1 THEN 2 END END ELSE RETURN"
    assert patrones.if_exists_sin_else(_m(texto)) == []


def test_if_not_exists_de_configuracion_es_guarda_no_defecto():
    # forma de WideWorldImporters: crear un objeto sólo si no existe (idempotente)
    texto = "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX') BEGIN EXEC (N'CREATE INDEX IX ON t (a)') END"
    assert _categorias(patrones.if_exists_sin_else(_m(texto))) == ['if_exists_guarda']


def test_if_exists_que_lanza_un_error_es_guarda():
    texto = "IF EXISTS (SELECT 1 FROM @x) BEGIN PRINT N'no'; THROW 51000, N'no', 1; END; BEGIN TRAN;"
    assert _categorias(patrones.if_exists_sin_else(_m(texto))) == ['if_exists_guarda']


# ── literales y desfase horario ─────────────────────────────────────────────────────────────────────────────

def test_literales_magicos_sin_largos_de_tipo_ni_parametros():
    texto = """CREATE PROCEDURE dbo.p @maximo int = 200, @x varchar(9) AS
    BEGIN
        DECLARE @c decimal(18, 2) = ROUND(@m * 0.0025, 2, 1);
        IF @c < 150 SET @c = 150;
        SELECT * FROM o WHERE estatus = 'ENVIADA' AND tipo IN ('A', 'B');
    END"""
    valores = {h['valor'] for h in patrones.literales(_m(texto))}
    assert {'0.0025', '150', '2', "'ENVIADA'", "'A'", "'B'"} <= valores
    assert not {'200', '9', '18'} & valores


def test_desfase_horario_fijo_en_dateadd_de_horas():
    texto = 'SET h = DATEDIFF(minute, o.fecha_envio, DATEADD(hour, -1, l.ultima)) / 60.0'
    h = patrones.desfase_horario_fijo(_m(texto))
    assert _categorias(h) == ['desfase_horario_fijo'] and '-1' in h[0]['detalle']
    assert patrones.desfase_horario_fijo(_m('SELECT DATEADD(day, -3, GETDATE())')) == []


# ── ROUND que trunca ────────────────────────────────────────────────────────────────────────────────────────

def test_round_con_tercer_argumento_distinto_de_cero_trunca():
    h = patrones.round_trunca(_m('SET @comision = ROUND(@monto_mxn * 0.0025, 2, 1);'))
    assert [x['categoria'] for x in h] == ['round_trunca']
    assert patrones.round_trunca(_m('SET @c = ROUND(@m, 2, @modo)'))           # no se sabe: se revisa


def test_round_normal_no_se_detecta():
    assert patrones.round_trunca(_m('SELECT ROUND(a * b, 2), ROUND(c, 0, 0), ROUND(ISNULL(x, 1), 2) FROM t')) == []


# ── columnas que nadie lee ──────────────────────────────────────────────────────────────────────────────────

def test_columna_que_solo_se_escribe_no_cuenta_como_leida():
    modulos = [
        _m("CREATE PROCEDURE dbo.a @proposito char(4) AS INSERT INTO dbo.orden (id, proposito, estatus) "
           "VALUES (1, @proposito, 'X')"),
        _m("CREATE PROCEDURE dbo.b AS UPDATE dbo.orden SET estatus = 'Y', sello = GETDATE() WHERE id = 1; "
           "SELECT id, estatus FROM dbo.orden"),
    ]
    h = patrones.columnas_sin_lectura(modulos, {'dbo.orden': ['id', 'proposito', 'estatus', 'sello'],
                                                'dbo.bitacora': ['id']})
    objetos = {(x['categoria'], x['objeto']) for x in h}
    assert objetos == {('columna_sin_lectura', 'dbo.orden.proposito'), ('columna_sin_lectura', 'dbo.orden.sello'),
                       ('tabla_sin_lectura', 'dbo.bitacora')}


# ── el código del legado ────────────────────────────────────────────────────────────────────────────────────

def _modulos_del_legado() -> list[Modulo]:
    modulos = []
    for ruta in sorted(Path('legado/sql').glob('0[3-5]_*.sql')):
        for lote in lotes(ruta.read_text(encoding='utf-8')):
            creado = re.search(r'CREATE\s+OR\s+ALTER\s+(\w+)\s+([\w.]+)', lote)
            if creado:
                modulos.append(Modulo(creado.group(2).lower(), creado.group(1).upper(), lote))
    return modulos


def test_sobre_el_codigo_del_legado_aparecen_los_patrones_sembrados():
    padres = {'dbo.partida_solicitada': {'dbo.orden_pago'}, 'dbo.partida_liquidada': {'dbo.orden_pago'},
              'dbo.orden_pago': {'dbo.operacion', 'dbo.moneda'}, 'dbo.operacion': {'dbo.moneda'}}
    todos = patrones.analizar_codigo(_modulos_del_legado(), padres, UNICAS_LEGADO, COLUMNAS_LEGADO)
    hallazgos = {(h['categoria'], h['objeto']) for h in todos}
    assert ('top_sin_order_by', 'dbo.sp_lista_operaciones') in hallazgos
    assert ('inner_join_hija', 'dbo.vw_reporte_ordenes') in hallazgos
    assert ('reloj_en_regla', 'dbo.sp_conciliar') in hallazgos
    assert ('desfase_horario_fijo', 'dbo.sp_conciliar') in hallazgos
    assert ('if_exists_sin_else', 'dbo.sp_registrar_liquidacion') in hallazgos
    assert ('round_trunca', 'dbo.sp_registrar_orden') in hallazgos
    # el trigger sella la bitácora con GETDATE(): no es una regla
    assert ('reloj_en_regla', 'dbo.tr_orden_pago_bitacora') not in hallazgos
    # detectores-v3 sobre las formas de la siembra a ciegas (catálogo ya conocido: no es control)
    assert ('top_sin_order_by', 'dbo.sp_reporte_posicion') in hallazgos
    assert ('reloj_en_regla', 'dbo.sp_ordenes_por_vencer') in hallazgos
    # control de falsos positivos en el propio legado: la asignación por PK de sp_registrar_orden NO se marca
    asignaciones = [h for h in todos if h.get('forma') == 'asignacion_multifila']
    assert [h['objeto'] for h in asignaciones] == ['dbo.sp_reporte_posicion']


# Llaves únicas del legado como las ve la radiografía: las PK de legado/sql/02_tablas.sql (ningún otro índice único).
UNICAS_LEGADO = {f'dbo.{t}': [{'codigo'} if t == 'moneda' else {'serie'} if t == 'folio' else {'id'}]
                 for t in ('moneda', 'folio', 'operacion', 'orden_pago', 'partida_solicitada', 'partida_liquidada',
                           'bitacora')}
COLUMNAS_LEGADO = {f'dbo.{t}': set(c) for t, c in COLUMNAS.items()}


# ── detectores-v3: asignación desde varias filas ────────────────────────────────────────────────────────────

# Llaves únicas como las lee la radiografía del esquema restaurado (PK de legado/sql/02_tablas.sql).
UNICAS = {'dbo.operacion': [{'id'}], 'dbo.orden_pago': [{'id'}], 'dbo.moneda': [{'codigo'}],
          'dbo.t': [{'a'}, {'b', 'c'}], 'dbo.sin_llave': []}
COLUMNAS_DE = {'dbo.operacion': {'id', 'moneda', 'tipo_cambio', 'fecha_operacion', 'monto_mxn'},
               'dbo.orden_pago': {'id', 'uetr', 'estatus'}, 'dbo.moneda': {'codigo', 'nombre'},
               'dbo.t': {'a', 'b', 'c', 'x'}, 'dbo.sin_llave': {'x', 'y'}}


def _multifila(texto: str):
    return patrones.asignacion_multifila(_m(texto), UNICAS, COLUMNAS_DE)


def test_asignacion_desde_varias_filas_sin_top_se_detecta():
    # forma de la siembra a ciegas: el tipo de cambio «de la última operación del día», sin TOP ni ORDER BY
    h = _multifila('SELECT @tc_cierre = tipo_cambio FROM dbo.operacion WHERE moneda = @moneda '
                   'AND fecha_operacion >= @fecha AND fecha_operacion < DATEADD(day, 1, @fecha);')
    assert [x['categoria'] for x in h] == ['top_sin_order_by'] and h[0]['forma'] == 'asignacion_multifila'


def test_asignacion_por_llave_primaria_no_se_detecta():
    # control dentro del legado: sp_registrar_orden lee una sola fila por la PK de operacion
    assert _multifila('SELECT @monto_mxn = monto_mxn FROM dbo.operacion WHERE id = @operacion_id;') == []


def test_asignacion_por_indice_unico_compuesto_o_con_mas_columnas_no_se_detecta():
    assert _multifila('SELECT @v = x FROM dbo.t WHERE c = @c AND b = @b') == []
    assert _multifila('SELECT @v = x FROM dbo.t WHERE a = @a AND x > 3') == []


def test_asignacion_con_agregado_o_sin_from_no_se_detecta():
    assert _multifila('SELECT @fecha = CAST(MAX(fecha_operacion) AS date) FROM dbo.operacion') == []
    assert _multifila('SELECT @n = COUNT(*) FROM dbo.sin_llave WHERE x = 1') == []
    assert _multifila('SELECT @hoy = GETDATE()') == []


def test_asignacion_con_or_sin_where_o_con_group_by_si_se_detecta():
    assert _multifila('SELECT @v = x FROM dbo.t WHERE a = @a OR b = @b')
    assert _multifila('SELECT @v = nombre FROM dbo.moneda')
    assert _multifila('SELECT @v = MAX(x) FROM dbo.sin_llave GROUP BY y')


def test_asignacion_desde_vista_variable_o_temporal_no_se_decide():
    assert _multifila('SELECT @v = x FROM dbo.vw_algo WHERE y = 1') == []
    assert _multifila('SELECT @v = x FROM @tabla WHERE y = 1') == []
    assert _multifila('SELECT @v = x FROM #temporal WHERE y = 1') == []


def test_asignacion_con_top_queda_para_el_otro_detector():
    assert _multifila('SELECT TOP 1 @v = x FROM dbo.sin_llave WHERE y = 1') == []


# ── detectores-v3: reloj por variable ───────────────────────────────────────────────────────────────────────

POR_VENCER = """CREATE OR ALTER PROCEDURE dbo.sp_ordenes_por_vencer AS
BEGIN
    DECLARE @hoy datetime, @limite datetime;
    SET @hoy = GETDATE();
    SET @limite = DATEADD(day, -2, @hoy);
    SELECT folio, CASE WHEN fecha_envio < DATEADD(day, -1, @limite) THEN 'VENCE HOY' ELSE 'MANANA' END AS aviso
    FROM dbo.orden_pago
    WHERE estatus = 'ENVIADA' AND fecha_envio < @limite
END"""


def test_el_reloj_que_entra_por_una_variable_se_propaga_hasta_la_regla():
    assert patrones.variables_de_reloj(_m(POR_VENCER)) == {'@HOY': 'GETDATE()', '@LIMITE': '@hoy'}
    h = patrones.reloj_por_variable(_m(POR_VENCER))
    assert [x['linea'] for x in h] == [6, 8] and all(x['categoria'] == 'reloj_en_regla' for x in h)
    # el reloj directo dentro de un SET de variable sigue sin ser regla
    assert patrones.reloj_en_regla(_m(POR_VENCER)) == []


def test_reloj_por_declare_y_select_y_en_un_join_o_un_update():
    texto = """DECLARE @ahora datetime2 = SYSDATETIME();
    SELECT @corte = CAST(@ahora AS date);
    SELECT a.x FROM a JOIN b ON b.f < @corte;
    UPDATE t SET vence = DATEADD(day, 3, @corte) WHERE id = 1;"""
    h = patrones.reloj_por_variable(_m(texto))
    assert [x['linea'] for x in h] == [3, 4]
    assert 'UPDATE' in h[1]['detalle']


def test_variable_de_reloj_que_solo_sella_un_insert_no_es_regla():
    texto = "DECLARE @ahora datetime = GETDATE(); INSERT INTO b (a, f) VALUES (1, @ahora); SELECT @ahora AS sello"
    assert patrones.reloj_por_variable(_m(texto)) == []


def test_variable_sin_reloj_no_se_marca():
    texto = 'DECLARE @limite datetime = DATEADD(day, -2, @fecha); SELECT x FROM t WHERE f < @limite'
    assert patrones.reloj_por_variable(_m(texto)) == []


def test_la_variable_del_set_de_un_update_no_hereda_el_reloj_de_otra_columna():
    # regresión de detectores-v3 sobre el propio legado (sp_registrar_orden): @n toma el folio, no GETDATE()
    texto = ("UPDATE dbo.folio SET @n = siguiente, siguiente = siguiente + 1, actualizado = GETDATE() "
             "WHERE serie = 'OP';\nIF @folio IS NULL SET @folio = 'OP-' + CAST(@n AS varchar(9));")
    assert patrones.variables_de_reloj(_m(texto)) == {}
    assert patrones.reloj_por_variable(_m(texto)) == []
