# Radiografía de `BFN_DIVISAS`

Generada 2026-11-25T01:23:25+00:00 (UTC) por `python -m radiografia`. Todo lo que sigue se midió sobre el respaldo restaurado en un contenedor limpio.

## Restauración

| Base restaurada | Archivo | sha256 contra el manifiesto | Verificación | Segundos |
|---|---|---|---|---:|
| `BFN_DIVISAS` | `bfn_divisas_2023-12-29.bak` | coincide | íntegro (VERIFYONLY con CHECKSUM) | 2.3 |
| `legado_msdb` | `msdb_2023-12-29.bak` | coincide | íntegro (VERIFYONLY con CHECKSUM) | 0.7 |

## Criterio de salida

`COUNT(*)` de `dbo.operacion` en el respaldo = **412,130** · la pantalla del legado publicaba **412,130** al tomarlo → CUMPLE.

## Corte medido en la fuente

Tabla principal `dbo.operacion`: MAX(id) = **412130** (IDENT_CURRENT 412130).
- `fecha_operacion`: 2021-01-01 00:09:00 → **2023-12-29 03:34:00**

| Tabla | MAX(id) | IDENT_CURRENT | Fecha más reciente |
|---|---:|---:|---|
| `dbo.bitacora` | 685273 | 685273 | fecha 2023-12-29 03:44:36 |
| `dbo.folio` | — | — | actualizado 2023-12-29 03:44:36 |
| `dbo.moneda` | — | — |  |
| `dbo.operacion` | 412130 | 412130 | fecha_operacion 2023-12-29 03:34:00 |
| `dbo.orden_pago` | 270621 | 270621 | fecha_registro 2023-12-29 03:44:36, fecha_envio 2023-12-29 03:45:38, fecha_valor 2023-12-29 |
| `dbo.partida_liquidada` | 893190 | 893190 | fecha_hora 2023-12-29 03:44:36 |
| `dbo.partida_solicitada` | 244862 | 244862 | fecha_hora 2023-12-28 17:51:08 |

## Inventario

7 tablas · 2,506,089 filas · 10 módulos · 1 triggers · 1 pasos de job.

| Tabla | Filas |
|---|---:|
| `dbo.partida_liquidada` | 893,190 |
| `dbo.bitacora` | 685,273 |
| `dbo.operacion` | 412,130 |
| `dbo.orden_pago` | 270,621 |
| `dbo.partida_solicitada` | 244,862 |
| `dbo.moneda` | 11 |
| `dbo.folio` | 2 |

Módulos: 1 job, 7 procedimiento, 1 trigger, 1 vista.

Triggers: `dbo.tr_orden_pago_bitacora` sobre `dbo.orden_pago`.

| Job | Paso | Base | Comando | Horario | Habilitado |
|---|---|---|---|---|---|
| BFN - conciliacion nocturna | conciliar | BFN_DIVISAS | `EXEC dbo.sp_conciliar;` | todas las noches 23:30 23:30 | sí |

## Hallazgos por patrón

| Patrón | Hallazgos |
|---|---:|
| TOP sin ORDER BY | 5 |
| INNER JOIN a una tabla hija | 1 |
| Reloj del servidor (GETDATE y similares) dentro de una regla | 1 |
| IF EXISTS sin ELSE que escribe datos (camino silencioso) | 1 |
| IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo) | 0 |
| Conversión de zona con desfase fijo | 1 |
| Centinelas en vez de NULL (por distribución de valores) | 3 |
| Texto con mojibake (UTF-8 leído como latin-1) | 1 |
| Re-registro: el mismo documento con otra llave interna | 3 |
| Llave candidata con duplicados (no parece re-registro) | 1 |
| Columnas que ningún módulo lee | 4 |
| Tablas que ningún módulo lee | 1 |
| Literales mágicos (números y códigos en duro) | 30 |

### TOP sin ORDER BY (5)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_conciliar` | 7 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero | `SELECT TOP (5000) id INTO #lote FROM dbo.orden_pago WHERE estatus = 'LIQUIDADA';` |
| `dbo.sp_detalle_operacion` | 8 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero; asigna a variables (si el filtro no es único, el valor es arbitrario) | `SELECT TOP 1 @orden = id FROM dbo.orden_pago WHERE operacion_id = @operacion_id AND estatus <> 'REEMPLAZADA';` |
| `dbo.sp_lista_operaciones` | 13 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero | `SELECT TOP (@maximo) o.id, o.folio, o.fecha_operacion, o.sucursal, o.canal, o.cliente, o.tipo, o.moneda,` |
| `dbo.sp_registrar_liquidacion` | 15 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero; asigna a variables (si el filtro no es único, el valor es arbitrario) | `SELECT TOP 1 @id = id, @moneda = moneda FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA';` |
| `dbo.sp_registrar_orden` | 23 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero; asigna a variables (si el filtro no es único, el valor es arbitrario) | `SELECT TOP 1 @anterior = id, @folio = folio FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA';` |

### INNER JOIN a una tabla hija (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.vw_reporte_ordenes` | 8 | INNER JOIN de dbo.orden_pago a su tabla hija dbo.partida_solicitada: descarta los registros de dbo.orden_pago sin dbo.partida_solicitada | `INNER JOIN dbo.partida_solicitada p ON p.orden_id = o.id` |

### Reloj del servidor (GETDATE y similares) dentro de una regla (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_conciliar` | 21 | GETDATE() decide un resultado: reprocesar otro día da otra respuesta | `WHERE estatus = 'ENVIADA' AND fecha_envio < DATEADD(day, -3, GETDATE());` |

### IF EXISTS sin ELSE que escribe datos (camino silencioso) (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_registrar_liquidacion` | 13 | IF EXISTS sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se entera (camino silencioso) | `IF EXISTS (SELECT 1 FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA')` |

### Conversión de zona con desfase fijo (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_conciliar` | 10 | DATEADD(hour, -1, …): convierte zonas con un desfase fijo; con horario de verano el desfase cambia según la fecha | `SET horas_liquidacion = DATEDIFF(minute, o.fecha_envio, DATEADD(hour, -1, l.ultima)) / 60.0,` |

### Centinelas en vez de NULL (por distribución de valores) (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.operacion.cuenta_clabe` |  | 107,265 filas (26.0%) con 'NA': valor de relleno típico ('NA'); la columna no usa NULL |  |
| `dbo.operacion.tipo_cambio_referencia` |  | 53,702 filas (13.0%) con Decimal('0.000000'): 0.000000 queda fuera del rango del resto de la columna (0.113984 … 71.214699); la columna no usa NULL |  |
| `dbo.orden_pago.bic_intermediario` |  | 230,306 filas (85.1%) con 'NA': valor de relleno típico ('NA'); la columna no usa NULL |  |

### Texto con mojibake (UTF-8 leído como latin-1) (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.operacion.cliente` |  | 21,189 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 400 de 400 valores distintos se reparan al revertir la decodificación |  |

### Re-registro: el mismo documento con otra llave interna (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.orden_pago.folio` |  | 119,897 filas repiten un valor (150,724 distintos en 270,621); las filas repetidas comparten el 81% de sus columnas (dos filas cualesquiera, el 20%): el MISMO documento dado de alta con otra llave interna; en 40 de 40 grupos la fila de id mayor es la de fecha_registro más reciente |  |
| `dbo.orden_pago.uetr` |  | 119,897 filas repiten un valor (150,724 distintos en 270,621); las filas repetidas comparten el 82% de sus columnas (dos filas cualesquiera, el 20%): el MISMO documento dado de alta con otra llave interna; en 40 de 40 grupos la fila de id mayor es la de fecha_registro más reciente |  |
| `dbo.orden_pago.referencia_mt103` |  | 119,897 filas repiten un valor (150,724 distintos en 270,621); las filas repetidas comparten el 81% de sus columnas (dos filas cualesquiera, el 20%): el MISMO documento dado de alta con otra llave interna; en 40 de 40 grupos la fila de id mayor es la de fecha_registro más reciente |  |

### Llave candidata con duplicados (no parece re-registro) (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.partida_solicitada.referencia` |  | 100,683 filas repiten un valor (144,179 distintos en 244,862); las filas repetidas comparten el 50% de sus columnas (dos filas cualesquiera, el 24%); en 40 de 40 grupos la fila de id mayor es la de fecha_hora más reciente |  |

### Columnas que ningún módulo lee (4)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.folio.actualizado` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `dbo.moneda.numerico` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `dbo.moneda.activa` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |
| `dbo.orden_pago.codigo_proposito` |  | ningún procedimiento, vista, trigger ni job la lee: sólo una comparación de esquema columna por columna nota si se pierde |  |

### Tablas que ningún módulo lee (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.bitacora` |  | ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o la lee otra aplicación) |  |

### Literales mágicos (números y códigos en duro) (30)

| Objeto | Literales distintos | Ejemplos |
|---|---:|---|
| `dbo.sp_registrar_orden` | 12 | `'ENVIADA'`, `'OP'`, `9`, `'REEMPLAZADA'`, `0.0025`, `2`, `150`, `3`, `0.16`, `'OUR'`, `4`, `25.00` |
| `dbo.sp_conciliar` | 7 | `5000`, `'LIQUIDADA'`, `60.0`, `'PRINCIPAL'`, `'VENCIDA'`, `'ENVIADA'`, `-3` |
| `dbo.sp_registrar_operacion` | 6 | `'FX'`, `'V'`, `1.0035`, `0.9965`, `9`, `2` |
| `dbo.sp_registrar_liquidacion` | 3 | `'ENVIADA'`, `2`, `'LIQUIDADA'` |
| `dbo.sp_detalle_operacion` | 1 | `'REEMPLAZADA'` |
| `dbo.vw_reporte_ordenes` | 1 | `'REEMPLAZADA'` |

## Tiempos

arranque_contenedor: 4.2 s · restauracion: 4.2 s · inventario: 1.0 s · patrones_codigo: 0.0 s · patrones_datos: 14.1 s · total: 23.9 s

