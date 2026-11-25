"""Veredicto MEDIDO de cada hallazgo que no corresponde a una trampa del catálogo.

Es la revisión humana que sigue a la radiografía, específica de este legado: cada veredicto se apoya en consultas
sobre el respaldo restaurado en un contenedor limpio. Ningún detector usa este módulo. Tampoco lee el catálogo de
trampas: sólo mide.

    python -m radiografia.veredictos --manifiesto respaldos/respaldo_2023-12-29.json --salida radiografia/informe
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from radiografia import sqlserver
from radiografia.__main__ import _sha256

LIMITE_LOTE = 5000            # el TOP (5000) de sp_conciliar


def _uno(cursor, sql: str, parametros: tuple = ()):
    cursor.execute(sql, parametros)
    return cursor.fetchone()[0]


def _indice_unico_con(cursor, tabla: str, columna: str) -> int:
    return _uno(cursor, """SELECT COUNT(*) FROM sys.indexes i JOIN sys.index_columns ic
                              ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                           JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
                           WHERE i.object_id = OBJECT_ID(%s) AND i.is_unique = 1 AND c.name = %s""",
                (tabla, columna))


def veredictos(cursor) -> list[dict]:
    r = []
    # ── TOP 1 sobre «uetr + ENVIADA» (sp_registrar_orden y sp_registrar_liquidacion)
    duplicadas = _uno(cursor, "SELECT COUNT(*) FROM (SELECT uetr FROM dbo.orden_pago WHERE estatus = 'ENVIADA' "
                              "GROUP BY uetr HAVING COUNT(*) > 1) x")
    unico = _indice_unico_con(cursor, 'dbo.orden_pago', 'uetr')
    ventanas = _uno(cursor, "SELECT COUNT(*) FROM dbo.bitacora b JOIN dbo.bitacora a ON a.id = b.id + 1 "
                            "WHERE b.accion = 'I' AND a.accion = 'U' AND a.estatus_nuevo = 'REEMPLAZADA' "
                            "AND a.fecha = b.fecha")
    medicion = {'uetr_con_mas_de_una_ENVIADA': duplicadas, 'indices_unicos_sobre_uetr': unico,
                'altas_seguidas_de_REEMPLAZADA_segun_la_bitacora': ventanas}
    for objeto in ('dbo.sp_registrar_orden', 'dbo.sp_registrar_liquidacion'):
        r.append({'categoria': 'top_sin_order_by', 'objeto': objeto, 'clase': 'latente', 'medicion': medicion,
                  'veredicto': (f'Latente: hoy ningún uetr tiene dos filas ENVIADA ({duplicadas}), pero ningún índice '
                                f'único lo garantiza ({unico}). La invariante la sostiene el re-registro: '
                                f'sp_registrar_orden da de alta la fila nueva y DESPUÉS marca REEMPLAZADA la '
                                f'anterior. La bitácora muestra {ventanas:,} veces esa ventana con dos ENVIADA; una '
                                f'liquidación concurrente tomaría cualquiera de las dos.')})
    # ── TOP 1 sobre «operacion_id + <> REEMPLAZADA» (sp_detalle_operacion)
    duplicadas = _uno(cursor, "SELECT COUNT(*) FROM (SELECT operacion_id FROM dbo.orden_pago "
                              "WHERE estatus <> 'REEMPLAZADA' GROUP BY operacion_id HAVING COUNT(*) > 1) x")
    unico = _indice_unico_con(cursor, 'dbo.orden_pago', 'operacion_id')
    r.append({'categoria': 'top_sin_order_by', 'objeto': 'dbo.sp_detalle_operacion', 'clase': 'latente',
              'medicion': {'operaciones_con_mas_de_una_orden_vigente': duplicadas,
                           'indices_unicos_sobre_operacion_id': unico},
              'veredicto': (f'Latente: {duplicadas} operaciones tienen más de una orden vigente y no hay índice único '
                            f'({unico}). La invariante la sostiene el re-registro, no la base.')})
    # ── TOP (5000) del lote nocturno (sp_conciliar)
    cursor.execute("""SELECT TOP 1 fecha, COUNT(*) FROM dbo.bitacora
                      WHERE usuario = 'svc_agente' AND estatus_anterior = 'LIQUIDADA'
                      GROUP BY fecha ORDER BY COUNT(*) DESC, fecha""")
    noche_pico, maximo = cursor.fetchone()
    noches = _uno(cursor, "SELECT COUNT(DISTINCT fecha) FROM dbo.bitacora WHERE usuario = 'svc_agente'")
    pendientes = _uno(cursor, "SELECT COUNT(*) FROM dbo.orden_pago WHERE estatus = 'LIQUIDADA'")
    clase = 'latente' if maximo < LIMITE_LOTE else 'defecto real'
    r.append({'categoria': 'top_sin_order_by', 'objeto': 'dbo.sp_conciliar', 'clase': clase,
              'medicion': {'noches': noches, 'maximo_liquidadas_por_noche': maximo, 'noche_pico': str(noche_pico),
                           'limite_del_lote': LIMITE_LOTE, 'liquidadas_al_respaldo': pendientes},
              'veredicto': (f'{"Latente" if clase == "latente" else "Real"}: en {noches:,} noches el máximo de '
                            f'órdenes LIQUIDADA conciliadas fue {maximo:,} ({noche_pico:%Y-%m-%d}), contra un lote de '
                            f'{LIMITE_LOTE:,} ({LIMITE_LOTE / maximo:.1f} veces de margen). Si el volumen lo pasa, el '
                            f'resto espera a la noche siguiente y el TOP sin ORDER BY decide cuáles.')})
    # ── moneda.activa: nadie la lee
    cursor.execute("""SELECT m.codigo, COUNT(*), MIN(o.fecha_operacion), MAX(o.fecha_operacion)
                      FROM dbo.operacion o JOIN dbo.moneda m ON m.codigo = o.moneda WHERE m.activa = 0
                      GROUP BY m.codigo ORDER BY m.codigo""")
    inactivas = [{'moneda': c, 'operaciones': n, 'primera': str(a), 'ultima': str(b)}
                 for c, n, a, b in cursor.fetchall()]
    fecha_baja = _uno(cursor, "SELECT COUNT(*) FROM sys.columns WHERE object_id = OBJECT_ID('dbo.moneda') "
                              "AND system_type_id IN (40, 42, 58, 61)")
    moneda = inactivas[0]['moneda'] if inactivas else 'HRK'
    cursor.execute('BEGIN TRANSACTION')
    try:
        cursor.execute("""DECLARE @id int;
                          EXEC dbo.sp_registrar_operacion @fecha_operacion = '2023-12-29T10:00:00', @sucursal = '0001',
                               @canal = 'VENTANILLA', @cliente = N'PRUEBA DE VEREDICTO', @tipo = 'V',
                               @moneda = %s, @monto_divisa = 100, @tipo_cambio = 1, @id = @id OUTPUT;
                          SELECT @id""", (moneda,))
        aceptada = cursor.fetchone()[0]
    finally:
        cursor.execute('ROLLBACK TRANSACTION')
    r.append({'categoria': 'columna_sin_lectura', 'objeto': 'dbo.moneda.activa', 'clase': 'defecto real',
              'medicion': {'operaciones_en_monedas_inactivas': inactivas, 'columnas_de_fecha_en_moneda': fecha_baja,
                           'id_asignado_a_una_operacion_nueva_en_moneda_inactiva': aceptada},
              'veredicto': (f'DEFECTO REAL no sembrado: ningún procedimiento consulta moneda.activa. Con la moneda '
                            f'{moneda} dada de baja, sp_registrar_operacion aceptó una operación nueva (id {aceptada}, '
                            f'revertida). El catálogo no guarda la fecha de baja ({fecha_baja} columnas de fecha), '
                            f'así que la base no puede distinguir las operaciones de antes y de después de la '
                            f'baja. Si no hay violaciones, es porque las sucursales dejaron de operarla, no porque el '
                            f'sistema lo impida.')})
    # ── moneda.numerico y folio.actualizado: inventario
    numericos = _uno(cursor, "SELECT COUNT(*) FROM dbo.moneda WHERE numerico LIKE '[0-9][0-9][0-9]'")
    total_monedas = _uno(cursor, 'SELECT COUNT(*) FROM dbo.moneda')
    r.append({'categoria': 'columna_sin_lectura', 'objeto': 'dbo.moneda.numerico', 'clase': 'inventario',
              'medicion': {'codigos_numericos_validos': numericos, 'monedas': total_monedas},
              'veredicto': (f'Inventario: el código numérico ISO 4217 ({numericos} de {total_monedas} válidos) no lo '
                            f'lee nadie. Se migra tal cual; no es defecto.')})
    cursor.execute('SELECT serie, siguiente, actualizado FROM dbo.folio ORDER BY serie')
    folios = [{'serie': s.strip(), 'siguiente': n, 'actualizado': str(a)} for s, n, a in cursor.fetchall()]
    r.append({'categoria': 'columna_sin_lectura', 'objeto': 'dbo.folio.actualizado', 'clase': 'inventario',
              'medicion': {'folios': folios},
              'veredicto': ('Inventario: sello GETDATE() del último consumo; nadie lo lee. No sirve como corte (el '
                            'corte se mide con MAX(id)) y el contador que importa para S3 es «siguiente».')})
    # ── partida_solicitada.referencia: candidata con duplicados
    cursor.execute("""SELECT COUNT(*), SUM(CASE WHEN ordenes > 1 THEN 1 ELSE 0 END), MAX(renglones) FROM (
                          SELECT referencia, COUNT(DISTINCT orden_id) AS ordenes, COUNT(*) AS renglones
                          FROM dbo.partida_solicitada GROUP BY referencia HAVING COUNT(*) > 1) x""")
    grupos, cruzados, maximo = cursor.fetchone()
    r.append({'categoria': 'llave_candidata_con_duplicados', 'objeto': 'dbo.partida_solicitada.referencia',
              'clase': 'explicado',
              'medicion': {'referencias_repetidas': grupos, 'repetidas_en_mas_de_una_orden': cruzados,
                           'renglones_maximos_por_referencia': maximo},
              'veredicto': (f'No es llave: es la referencia del MENSAJE del corresponsal, compartida por sus '
                            f'renglones (abono y gastos). {grupos:,} referencias repetidas, {cruzados} en más de una '
                            f'orden, y como máximo {maximo} renglones cada una. El detector acertó en no llamarlo '
                            f're-registro.')})
    # ── folio y referencia_mt103 marcados como re-registro
    cursor.execute("""SELECT COUNT(DISTINCT uetr), COUNT(DISTINCT folio), COUNT(DISTINCT referencia_mt103),
                             COUNT(DISTINCT uetr + '|' + folio + '|' + referencia_mt103) FROM dbo.orden_pago""")
    uetr, folio, referencia, tripleta = cursor.fetchone()
    misma = uetr == folio == referencia == tripleta
    for objeto in ('dbo.orden_pago.folio', 'dbo.orden_pago.referencia_mt103'):
        r.append({'categoria': 're_registro', 'objeto': objeto, 'clase': 'señal de respaldo de T9',
                  'medicion': {'distintos_uetr': uetr, 'distintos_folio': folio, 'distintos_referencia': referencia,
                               'distintas_tripletas': tripleta},
                  'veredicto': (f'Señal de respaldo de T9, no ruido: uetr, folio y referencia MT103 parten las filas '
                                f'en los MISMOS {uetr:,} documentos ({"misma" if misma else "distinta"} partición). '
                                f'Cualquiera de las tres sirve de llave natural; uetr es la del estándar.')})
    # ── bitácora sin lectura
    cursor.execute('SELECT usuario, COUNT(*) FROM dbo.bitacora GROUP BY usuario ORDER BY usuario')
    por_usuario = {u: n for u, n in cursor.fetchall()}
    r.append({'categoria': 'tabla_sin_lectura', 'objeto': 'dbo.bitacora', 'clase': 'retención y universo',
              'medicion': {'filas_por_usuario': por_usuario, 'noches_del_job': noches},
              'veredicto': (f'Retención: no se migra como tabla viva. Además es FUENTE del replay: sus sellos '
                            f'svc_agente dan las {noches:,} noches del job (el reloj que se inyecta en lugar de '
                            f'GETDATE(), T8) y el orden entre cada llegada y el vencimiento (D3).')})
    return r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m radiografia.veredictos', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifiesto', type=Path, required=True)
    parser.add_argument('--salida', type=Path, default=Path('radiografia/informe'))
    args = parser.parse_args(argv)
    manifiesto = json.loads(args.manifiesto.read_text(encoding='utf-8'))
    principal = next(a for a in manifiesto['archivos'] if a['base'] == manifiesto['base'])
    ruta = args.manifiesto.parent / principal['nombre']
    if _sha256(ruta) != principal['sha256']:
        raise SystemExit(f'{ruta.name}: el sha256 no coincide con el manifiesto')
    servidor = sqlserver.arrancar_limpio()
    try:
        servidor.restaurar(servidor.copiar(str(ruta)), manifiesto['base'])
        with servidor.conectar(manifiesto['base']) as conexion:
            resultado = veredictos(conexion.cursor())
    finally:
        servidor.cerrar()
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / 'veredictos.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + '\n',
                                                 encoding='utf-8')
    for v in resultado:
        print(f"{v['categoria']:32s} {v['objeto']:36s} {v['clase']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
