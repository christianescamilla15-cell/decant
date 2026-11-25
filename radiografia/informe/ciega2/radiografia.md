# Radiografía de `BFN_DIVISAS`

Generada 2026-11-25T03:47:00+00:00 (UTC) por `python -m radiografia`. Todo lo que sigue se midió sobre el respaldo restaurado en un contenedor limpio.

## Restauración

| Base restaurada | Archivo | sha256 contra el manifiesto | Verificación | Segundos |
|---|---|---|---|---:|
| `BFN_DIVISAS` | `bfn_divisas_2023-12-29.bak` | coincide | íntegro (VERIFYONLY con CHECKSUM) | 0.8 |
| `legado_msdb` | `msdb_2023-12-29.bak` | coincide | íntegro (VERIFYONLY con CHECKSUM) | 0.3 |

## Criterio de salida

**CUMPLE.** El restaurado se compara contra lo que el legado decía de sí mismo al tomar el respaldo (el manifiesto), no contra sí mismo.

### Cifras de la pantalla: qué cuenta cada una

| Cifra | Valor | Tabla | COUNT(*) | Interpretaciones que dan la cifra | Lectura |
|---|---:|---|---:|---|---|
| Operaciones registradas | 412,125 | `dbo.operacion` | 412,125 | `COUNT(*)`, `COUNT(DISTINCT id)`, `COUNT(DISTINCT folio)` | la pantalla cuenta filas |
| Órdenes de pago | 150,719 | `dbo.orden_pago` | 270,616 | `COUNT(DISTINCT operacion_id)`, `COUNT(DISTINCT folio)`, `COUNT(DISTINCT uetr)`, `COUNT(DISTINCT referencia_mt103)` | la pantalla NO cuenta filas (270,616): cuenta valores distintos; 119,897 filas repiten la llave |

### Cuadre de cada tabla y contador contra el manifiesto

| Objeto | Manifiesto | Restaurado | Cuadra |
|---|---|---|---|
| `dbo.bitacora` | {'filas': 685276, 'max_id': 685276} | {'filas': 685276, 'max_id': 685276} | sí |
| `dbo.folio` | {'filas': 2, 'max_id': None} | {'filas': 2, 'max_id': None} | sí |
| `dbo.moneda` | {'filas': 11, 'max_id': None} | {'filas': 11, 'max_id': None} | sí |
| `dbo.operacion` | {'filas': 412125, 'max_id': 412125} | {'filas': 412125, 'max_id': 412125} | sí |
| `dbo.orden_pago` | {'filas': 270616, 'max_id': 270616} | {'filas': 270616, 'max_id': 270616} | sí |
| `dbo.partida_liquidada` | {'filas': 893174, 'max_id': 893174} | {'filas': 893174, 'max_id': 893174} | sí |
| `dbo.partida_solicitada` | {'filas': 244869, 'max_id': 244869} | {'filas': 244869, 'max_id': 244869} | sí |
| `dbo.folio.siguiente` | {'FX': 412126, 'OP': 150720} | {'FX': 412126, 'OP': 150720} | sí |

### Salidas publicadas: re-corrida sobre el restaurado contra la captura del respaldo

El orden se mide por inversiones con llave natural. Los pares con distinta llave de orden son contrato (0 inversiones). Los pares empatados son libres, y su desorden es el piso de la paridad.

| Salida | Renglones (comunes) | Mismo contenido | Pares contrato | Inversiones contrato | Pares empatados | Empatados invertidos | % posiciones distintas |
|---|---:|---|---:|---:|---:|---:|---:|
| reporte_del_mes (`dbo.sp_reporte_ordenes`) | 7,492 (7,492) | sí | 26,515,033 | 0 | 1,546,253 | 225,715 (14.6 %) | 40.2 |
| lista_del_dia_anterior (`dbo.sp_lista_operaciones`) | 200 (183) | no: sin ORDER BY, otra instancia devuelve otras filas | 0 | 0 | 16,653 | 372 (2.23 %) | 69.0 |

## Corte medido en la fuente

Tabla principal `dbo.operacion`: MAX(id) = **412125** (IDENT_CURRENT 412125).
- `fecha_operacion`: 2021-01-01 00:09:00 → **2023-12-29 03:34:00**

| Tabla | MAX(id) | IDENT_CURRENT | Fecha más reciente |
|---|---:|---:|---|
| `dbo.bitacora` | 685276 | 685276 | fecha 2023-12-29 03:44:36 |
| `dbo.folio` | — | — | actualizado 2023-12-29 03:44:36 |
| `dbo.moneda` | — | — |  |
| `dbo.operacion` | 412125 | 412125 | fecha_operacion 2023-12-29 03:34:00 |
| `dbo.orden_pago` | 270616 | 270616 | fecha_registro 2023-12-29 03:44:36, fecha_envio 2023-12-29 03:45:38, fecha_valor 2023-12-29 |
| `dbo.partida_liquidada` | 893174 | 893174 | fecha_hora 2023-12-29 03:44:36 |
| `dbo.partida_solicitada` | 244869 | 244869 | fecha_hora 2023-12-28 17:58:52 |

## Inventario

7 tablas · 2,506,073 filas · 16 módulos · 1 triggers · 1 pasos de job.

| Tabla | Filas |
|---|---:|
| `dbo.partida_liquidada` | 893,174 |
| `dbo.bitacora` | 685,276 |
| `dbo.operacion` | 412,125 |
| `dbo.orden_pago` | 270,616 |
| `dbo.partida_solicitada` | 244,869 |
| `dbo.moneda` | 11 |
| `dbo.folio` | 2 |

Módulos: 1 job, 12 procedimiento, 1 trigger, 2 vista.

Triggers: `dbo.tr_orden_pago_bitacora` sobre `dbo.orden_pago`.

| Job | Paso | Base | Comando | Horario | Habilitado |
|---|---|---|---|---|---|
| BFN - conciliacion nocturna | conciliar | BFN_DIVISAS | `EXEC dbo.sp_conciliar;` | todas las noches 23:30 23:30 | sí |

## Hallazgos por patrón

| Patrón | Hallazgos |
|---|---:|
| Selección no determinista: TOP sin ORDER BY o asignación desde varias filas | 6 |
| INNER JOIN a una tabla hija | 1 |
| Reloj del servidor (GETDATE y similares) en una regla, directo o por una variable | 3 |
| IF EXISTS sin ELSE que escribe datos (camino silencioso) | 1 |
| IF EXISTS sin ELSE con cuerpo de guarda o DDL (informativo) | 0 |
| Conversión de zona con desfase fijo | 1 |
| ROUND con tercer argumento: trunca en vez de redondear | 1 |
| Centinelas en vez de NULL (por distribución de valores) | 3 |
| Texto con mojibake (UTF-8 leído como latin-1) | 1 |
| Espacios finales que SQL Server ignora al comparar y PostgreSQL no | 1 |
| Re-registro: el mismo documento con otra llave interna | 3 |
| Llave candidata con duplicados (no parece re-registro) | 1 |
| Columnas que ningún módulo lee | 4 |
| Tablas que ningún módulo lee | 1 |
| Literales mágicos (números y códigos en duro) | 39 |

### Selección no determinista: TOP sin ORDER BY o asignación desde varias filas (6)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_conciliar` | 7 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero | `SELECT TOP (5000) id INTO #lote FROM dbo.orden_pago WHERE estatus = 'LIQUIDADA';` |
| `dbo.sp_detalle_operacion` | 8 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero; asigna a variables (si el filtro no es único, el valor es arbitrario) | `SELECT TOP 1 @orden = id FROM dbo.orden_pago WHERE operacion_id = @operacion_id AND estatus <> 'REEMPLAZADA';` |
| `dbo.sp_lista_operaciones` | 15 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero | `SELECT TOP (@maximo) o.id, o.folio, o.fecha_operacion, o.sucursal, o.canal, o.cliente, o.tipo, o.moneda,` |
| `dbo.sp_registrar_liquidacion` | 15 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero; asigna a variables (si el filtro no es único, el valor es arbitrario) | `SELECT TOP 1 @id = id, @moneda = moneda FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA';` |
| `dbo.sp_registrar_orden` | 23 | SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero; asigna a variables (si el filtro no es único, el valor es arbitrario) | `SELECT TOP 1 @anterior = id, @folio = folio FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA';` |
| `dbo.sp_reporte_posicion` | 24 | asigna @tc_cierre desde dbo.operacion sin TOP ni agregado y sin filtro único (el WHERE iguala moneda; llaves únicas de la tabla: id): la variable se queda con la última fila que entregue el plan | `SELECT @tc_cierre = tipo_cambio` |

### INNER JOIN a una tabla hija (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.vw_reporte_ordenes` | 8 | INNER JOIN de dbo.orden_pago a su tabla hija dbo.partida_solicitada: descarta los registros de dbo.orden_pago sin dbo.partida_solicitada | `INNER JOIN dbo.partida_solicitada p ON p.orden_id = o.id` |

### Reloj del servidor (GETDATE y similares) en una regla, directo o por una variable (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_conciliar` | 21 | GETDATE() decide un resultado: reprocesar otro día da otra respuesta | `WHERE estatus = 'ENVIADA' AND fecha_envio < DATEADD(day, -3, GETDATE());` |
| `dbo.sp_ordenes_por_vencer` | 11 | el reloj del servidor entra por la variable @limite (viene de @hoy) y decide un resultado: reprocesar otro día da otra respuesta | `CASE WHEN fecha_envio < DATEADD(day, -1, @limite) THEN 'VENCE HOY' ELSE 'VENCE MANANA' END AS aviso` |
| `dbo.sp_ordenes_por_vencer` | 13 | el reloj del servidor entra por la variable @limite (viene de @hoy) y decide un resultado: reprocesar otro día da otra respuesta | `WHERE estatus = 'ENVIADA' AND fecha_envio < @limite` |

### IF EXISTS sin ELSE que escribe datos (camino silencioso) (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_registrar_liquidacion` | 13 | IF EXISTS sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se entera (camino silencioso) | `IF EXISTS (SELECT 1 FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA')` |

### Conversión de zona con desfase fijo (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_conciliar` | 10 | DATEADD(hour, -1, …): convierte zonas con un desfase fijo; con horario de verano el desfase cambia según la fecha | `SET horas_liquidacion = DATEDIFF(minute, o.fecha_envio, DATEADD(hour, -1, l.ultima)) / 60.0,` |

### ROUND con tercer argumento: trunca en vez de redondear (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.sp_registrar_orden` | 43 | ROUND(…, …, 1) trunca en vez de redondear: con montos, un centavo de diferencia contra cualquier cálculo que redondee | `SET @comision = ROUND(@monto_mxn * 0.0025, 2, 1);` |

### Centinelas en vez de NULL (por distribución de valores) (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.operacion.cuenta_clabe` |  | 107,265 filas (26.0%) con 'NA': valor de relleno típico ('NA'); la columna no usa NULL |  |
| `dbo.operacion.tipo_cambio_referencia` |  | 53,702 filas (13.0%) con Decimal('0.000000'): 0.000000 queda fuera del rango del resto de la columna (0.113984 … 71.214699); la columna no usa NULL |  |
| `dbo.orden_pago.bic_intermediario` |  | 230,297 filas (85.1%) con 'NA': valor de relleno típico ('NA'); la columna no usa NULL |  |

### Texto con mojibake (UTF-8 leído como latin-1) (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.operacion.cliente` |  | 21,189 filas con secuencias de UTF-8 leído como latin-1; en la muestra, 400 de 400 valores distintos se reparan al revertir la decodificación |  |

### Espacios finales que SQL Server ignora al comparar y PostgreSQL no (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.partida_solicitada.referencia` |  | 48,013 de 244,869 valores con espacios al final (19.6%), medidos con DATALENGTH en el motor: SQL Server los ignora al comparar (=, DISTINCT, GROUP BY) y LEN no los cuenta; PostgreSQL sí los distingue; ventana en fecha_hora: 2022-07-04 08:00:15 → 2023-01-27 17:54:05 (la tabla va de 2021-01-01 08:11:34 a 2023-12-28 17:58:52); concentrados en esa ventana |  |

### Re-registro: el mismo documento con otra llave interna (3)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.orden_pago.folio` |  | 119,897 filas repiten un valor (150,719 distintos en 270,616); las filas repetidas comparten el 81% de sus columnas (dos filas cualesquiera, el 20%): el MISMO documento dado de alta con otra llave interna; en 40 de 40 grupos la fila de id mayor es la de fecha_registro más reciente |  |
| `dbo.orden_pago.uetr` |  | 119,897 filas repiten un valor (150,719 distintos en 270,616); las filas repetidas comparten el 82% de sus columnas (dos filas cualesquiera, el 20%): el MISMO documento dado de alta con otra llave interna; en 40 de 40 grupos la fila de id mayor es la de fecha_registro más reciente |  |
| `dbo.orden_pago.referencia_mt103` |  | 119,897 filas repiten un valor (150,719 distintos en 270,616); las filas repetidas comparten el 81% de sus columnas (dos filas cualesquiera, el 20%): el MISMO documento dado de alta con otra llave interna; en 40 de 40 grupos la fila de id mayor es la de fecha_registro más reciente |  |

### Llave candidata con duplicados (no parece re-registro) (1)

| Objeto | Línea | Detalle | Fragmento |
|---|---:|---|---|
| `dbo.partida_solicitada.referencia` |  | 100,686 filas repiten un valor (144,183 distintos en 244,869); las filas repetidas comparten el 50% de sus columnas (dos filas cualesquiera, el 24%); en 40 de 40 grupos la fila de id mayor es la de fecha_hora más reciente |  |

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

### Literales mágicos (números y códigos en duro) (39)

| Objeto | Literales distintos | Ejemplos |
|---|---:|---|
| `dbo.sp_registrar_orden` | 12 | `'ENVIADA'`, `'OP'`, `9`, `'REEMPLAZADA'`, `0.0025`, `2`, `150`, `3`, `0.16`, `'OUR'`, `4`, `25.00` |
| `dbo.sp_conciliar` | 7 | `5000`, `'LIQUIDADA'`, `60.0`, `'PRINCIPAL'`, `'VENCIDA'`, `'ENVIADA'`, `-3` |
| `dbo.sp_registrar_operacion` | 6 | `'FX'`, `'V'`, `1.0035`, `0.9965`, `9`, `2` |
| `dbo.sp_registrar_liquidacion` | 3 | `'ENVIADA'`, `2`, `'LIQUIDADA'` |
| `dbo.sp_reporte_posicion` | 3 | `'C'`, `'V'`, `2` |
| `dbo.sp_tablero_corresponsales` | 3 | `'CONCILIADA'`, `60`, `'REEMPLAZADA'` |
| `dbo.sp_ordenes_por_vencer` | 2 | `-2`, `'ENVIADA'` |
| `dbo.sp_detalle_operacion` | 1 | `'REEMPLAZADA'` |
| `dbo.vw_liquidaciones_recientes` | 1 | `'ABONO'` |
| `dbo.vw_reporte_ordenes` | 1 | `'REEMPLAZADA'` |

## Tiempos

arranque_contenedor: 4.2 s · restauracion: 2.1 s · inventario: 0.7 s · patrones_codigo: 0.1 s · patrones_datos: 12.7 s · criterio_salida: 1.2 s · total: 21.3 s

