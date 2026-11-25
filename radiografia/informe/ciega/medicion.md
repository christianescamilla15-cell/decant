# Medición de la radiografía de `BFN_DIVISAS` contra `legado/TRAMPAS.md`

Los detectores corrieron sin leer el catálogo; esta tabla sólo cuenta qué señales esperadas aparecieron.

**Detección: 0 de 3 trampas (0.0 %)**.

| Id | Trampa | Estado | Señales esperadas | Encontradas |
|---|---|---|---|---|
| T1 | Selección no determinista: variable asignada desde varias filas | no detectada | top_sin_order_by → dbo.sp_reporte_posicion | — |
| T2 | Reloj del servidor que entra a la regla por una variable | no detectada | reloj_en_regla → dbo.sp_ordenes_por_vencer | — |
| T3 | Espacios finales que SQL Server ignora al comparar y PostgreSQL no | no detectada | espacios_finales → dbo.partida_solicitada.referencia | — |

## Hallazgos que no corresponden a ninguna trampa (23)

Cada uno lleva su veredicto MEDIDO sobre el respaldo restaurado (`radiografia/veredictos.py`; la medición completa está en `veredictos.json`).

| Patrón | Objeto | Clase | Veredicto |
|---|---|---|---|
| centinela | `dbo.operacion.cuenta_clabe` | sin veredicto |  |
| centinela | `dbo.operacion.tipo_cambio_referencia` | sin veredicto |  |
| centinela | `dbo.orden_pago.bic_intermediario` | sin veredicto |  |
| columna_sin_lectura | `dbo.folio.actualizado` | inventario | Inventario: sello GETDATE() del último consumo; nadie lo lee. No sirve como corte (el corte se mide con MAX(id)) y el contador que importa para S3 es «siguiente». |
| columna_sin_lectura | `dbo.moneda.activa` | defecto real | DEFECTO REAL no sembrado: ningún procedimiento consulta moneda.activa. Con la moneda HRK dada de baja, sp_registrar_operacion aceptó una operación nueva (id 412126, revertida). El catálogo no guarda la fecha de baja (0 columnas de fecha), así que la base no puede distinguir las operaciones de antes y de después de la baja. Si no hay violaciones, es porque las sucursales dejaron de operarla, no porque el sistema lo impida. |
| columna_sin_lectura | `dbo.moneda.numerico` | inventario | Inventario: el código numérico ISO 4217 (11 de 11 válidos) no lo lee nadie. Se migra tal cual; no es defecto. |
| columna_sin_lectura | `dbo.orden_pago.codigo_proposito` | sin veredicto |  |
| desfase_horario_fijo | `dbo.sp_conciliar` | sin veredicto |  |
| if_exists_sin_else | `dbo.sp_registrar_liquidacion` | sin veredicto |  |
| inner_join_hija | `dbo.vw_reporte_ordenes` | sin veredicto |  |
| llave_candidata_con_duplicados | `dbo.partida_solicitada.referencia` | explicado | No es llave: es la referencia del MENSAJE del corresponsal, compartida por sus renglones (abono y gastos). 100,686 referencias repetidas, 0 en más de una orden, y como máximo 2 renglones cada una. El detector acertó en no llamarlo re-registro. |
| mojibake | `dbo.operacion.cliente` | sin veredicto |  |
| re_registro | `dbo.orden_pago.folio` | señal de respaldo de T9 | Señal de respaldo de T9, no ruido: uetr, folio y referencia MT103 parten las filas en los MISMOS 150,719 documentos (misma partición). Cualquiera de las tres sirve de llave natural; uetr es la del estándar. |
| re_registro | `dbo.orden_pago.referencia_mt103` | señal de respaldo de T9 | Señal de respaldo de T9, no ruido: uetr, folio y referencia MT103 parten las filas en los MISMOS 150,719 documentos (misma partición). Cualquiera de las tres sirve de llave natural; uetr es la del estándar. |
| re_registro | `dbo.orden_pago.uetr` | sin veredicto |  |
| reloj_en_regla | `dbo.sp_conciliar` | sin veredicto |  |
| round_trunca | `dbo.sp_registrar_orden` | sin veredicto |  |
| tabla_sin_lectura | `dbo.bitacora` | retención y universo | Retención: no se migra como tabla viva. Además es FUENTE del replay: sus sellos svc_agente dan las 1,090 noches del job (el reloj que se inyecta en lugar de GETDATE(), T8) y el orden entre cada llegada y el vencimiento (D3). |
| top_sin_order_by | `dbo.sp_conciliar` | latente | Latente: en 1,090 noches el máximo de órdenes LIQUIDADA conciliadas fue 393 (2023-12-18), contra un lote de 5,000 (12.7 veces de margen). Si el volumen lo pasa, el resto espera a la noche siguiente y el TOP sin ORDER BY decide cuáles. |
| top_sin_order_by | `dbo.sp_detalle_operacion` | latente | Latente: 0 operaciones tienen más de una orden vigente y no hay índice único (0). La invariante la sostiene el re-registro, no la base. |
| top_sin_order_by | `dbo.sp_lista_operaciones` | sin veredicto |  |
| top_sin_order_by | `dbo.sp_registrar_liquidacion` | latente | Latente: hoy ningún uetr tiene dos filas ENVIADA (0), pero ningún índice único lo garantiza (0). La invariante la sostiene el re-registro: sp_registrar_orden da de alta la fila nueva y DESPUÉS marca REEMPLAZADA la anterior. La bitácora muestra 119,897 veces esa ventana con dos ENVIADA; una liquidación concurrente tomaría cualquiera de las dos. |
| top_sin_order_by | `dbo.sp_registrar_orden` | latente | Latente: hoy ningún uetr tiene dos filas ENVIADA (0), pero ningún índice único lo garantiza (0). La invariante la sostiene el re-registro: sp_registrar_orden da de alta la fila nueva y DESPUÉS marca REEMPLAZADA la anterior. La bitácora muestra 119,897 veces esa ventana con dos ENVIADA; una liquidación concurrente tomaría cualquiera de las dos. |

**12 hallazgos sin veredicto.**
