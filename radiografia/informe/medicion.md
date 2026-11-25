# Medición de la radiografía de `BFN_DIVISAS` contra `legado/TRAMPAS.md`

Los detectores corrieron sin leer el catálogo; esta tabla sólo cuenta qué señales esperadas aparecieron.

**Detección: 8 de 9 trampas (88.9 %)**.

| Id | Trampa | Estado | Señales esperadas | Encontradas |
|---|---|---|---|---|
| T1 | TOP sin ORDER BY con empates reales | detectada | top_sin_order_by → dbo.sp_lista_operaciones | top_sin_order_by → dbo.sp_lista_operaciones |
| T2 | INNER JOIN que pierde hijos | detectada | inner_join_hija → dbo.vw_reporte_ordenes | inner_join_hija → dbo.vw_reporte_ordenes |
| T3 | Centinelas («NA», 0) en vez de NULL | detectada | centinela → dbo.operacion.cuenta_clabe<br>centinela → dbo.orden_pago.bic_intermediario<br>centinela → dbo.operacion.tipo_cambio_referencia | centinela → dbo.operacion.cuenta_clabe<br>centinela → dbo.orden_pago.bic_intermediario<br>centinela → dbo.operacion.tipo_cambio_referencia |
| T4 | Lados invertidos en el detalle | sin patrón en S1 | — | — |
| T5 | Horario de verano (hora local, corresponsal en Nueva York) | detectada | desfase_horario_fijo → dbo.sp_conciliar | desfase_horario_fijo → dbo.sp_conciliar |
| T6 | Columna que ningún reporte ni procedimiento imprime | detectada | columna_sin_lectura → dbo.orden_pago.codigo_proposito | columna_sin_lectura → dbo.orden_pago.codigo_proposito |
| T7 | Acentos latin-1 en columnas Unicode | detectada | mojibake → dbo.operacion.cliente | mojibake → dbo.operacion.cliente |
| T8 | GETDATE() dentro de una regla | detectada | reloj_en_regla → dbo.sp_conciliar | reloj_en_regla → dbo.sp_conciliar |
| T9 | Re-registro: el mismo documento con otra llave cada día | detectada | re_registro → dbo.orden_pago.uetr | re_registro → dbo.orden_pago.uetr |
| D1 | La comisión se trunca en vez de redondearse | sin patrón en S1 | — | — |
| D2 | Los montos ignoran los decimales de ISO 4217 | sin patrón en S1 | — | — |
| D3 | Liquidaciones descartadas en silencio | detectada | if_exists_sin_else → dbo.sp_registrar_liquidacion | if_exists_sin_else → dbo.sp_registrar_liquidacion |

## Hallazgos que no corresponden a ninguna trampa (11)

Patrones que sí están en el código o en los datos pero que el catálogo no siembra como defecto: hay que revisarlos uno por uno (algunos son ruido del patrón, otros son hallazgos reales).

| Patrón | Objeto |
|---|---|
| columna_sin_lectura | `dbo.folio.actualizado` |
| columna_sin_lectura | `dbo.moneda.activa` |
| columna_sin_lectura | `dbo.moneda.numerico` |
| llave_candidata_con_duplicados | `dbo.partida_solicitada.referencia` |
| re_registro | `dbo.orden_pago.folio` |
| re_registro | `dbo.orden_pago.referencia_mt103` |
| tabla_sin_lectura | `dbo.bitacora` |
| top_sin_order_by | `dbo.sp_conciliar` |
| top_sin_order_by | `dbo.sp_detalle_operacion` |
| top_sin_order_by | `dbo.sp_registrar_liquidacion` |
| top_sin_order_by | `dbo.sp_registrar_orden` |
