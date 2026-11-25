# Paridad del TO-BE contra el legado

Generado 2026-11-24T22:58:03-06:00 con `python -m paridad`. Corte medido de la fuente: **2023-12-29T03:44:36** (Ciudad de México) = 2023-12-29T09:44:36+00:00; mayor sello de la bitácora o fecha_operacion (hora de la Ciudad de México), convertido a UTC; por identidad, MAX(id) de cada tabla.

| Ejercicio | Cumple |
|---|---|
| migracion byte a byte | sí |
| esquema tras cada carga | sí |
| cuadre por lado | sí |
| motor sin defectos nuestros | sí |
| solo marca | sí |
| paridad de reporte | sí |
| gemelos | sí |

## 1. Verificar la migración

### Byte a byte (después de los parches documentados)

| Legado → TO-BE | Llave | Filas | Celdas | Bytes | Faltan | Sobran | Distintas | Parches aplicados |
|---|---|---:|---:|---:|---:|---:|---:|---|
| dbo.moneda → decant.moneda | codigo | 11 | 55 | 236 | 0 | 0 | 0 | — |
| dbo.folio → decant.consecutivo | serie | 2 | 2 | 12 | 0 | 0 | 0 | — |
| dbo.operacion → decant.operacion | folio | 412,125 | 5,357,625 | 52,776,765 | 0 | 0 | 0 | T5_cdmx 412,125, T3_texto 107,265, T3_numero 53,702 |
| dbo.orden_pago (fila vigente) → decant.orden_pago | uetr | 150,719 | 2,411,504 | 27,070,789 | 0 | 0 | 0 | T5_cdmx_llegada 301,438, char 128,220, T3_texto 128,220 |
| dbo.orden_pago (cada fila = un registro, T9) → decant.registro_orden | id_legado | 270,616 | 541,232 | 16,507,576 | 0 | 0 | 0 | T5_cdmx_llegada 270,616 |
| dbo.orden_pago (filas REEMPLAZADA = copias del documento) | uetr | 119,897 | 1,678,558 | — | 0 | 0 | 0 | — |
| dbo.partida_solicitada → decant.partida_corresponsal (T4) | (uetr, renglon) | 244,869 | 1,224,345 | 15,116,948 | 0 | 0 | 0 | T5_ny 244,869, ciega1_T3 48,013 |
| dbo.partida_liquidada (fila vigente) → decant.partida_cliente (T4) | (uetr, renglon) | 497,556 | 2,487,780 | 26,307,918 | 0 | 0 | 0 | T5_cdmx_llegada 497,556 |
| dbo.partida_liquidada (filas REEMPLAZADA) → reconstruibles de partida_cliente + registro_orden | (uetr, renglon, registro) | 395,618 | — | — | 0 | 0 | 0 | — |

### Esquema columna por columna, después de cada carga

| Carga | Columnas legado | Columnas TO-BE | Errores | Avisos |
|---|---:|---:|---:|---|
| decant_migracion | 64 | 81 | 0 | dbo.orden_pago.id → decant.registro_orden.id_legado: el TO-BE admite NULL y el legado no |
| decant_motor | 64 | 81 | 0 | dbo.orden_pago.id → decant.registro_orden.id_legado: el TO-BE admite NULL y el legado no |
| decant_marca_vencimiento | 64 | 81 | 0 | dbo.orden_pago.id → decant.registro_orden.id_legado: el TO-BE admite NULL y el legado no |
| decant_marca_conciliacion | 64 | 81 | 0 | dbo.orden_pago.id → decant.registro_orden.id_legado: el TO-BE admite NULL y el legado no |
| decant_sombra | 64 | 81 | 0 | dbo.orden_pago.id → decant.registro_orden.id_legado: el TO-BE admite NULL y el legado no |

**Control negativo (T6):** la misma comparación contra un TO-BE sin `codigo_proposito` FALLA y la nombra: «dbo.orden_pago.codigo_proposito → decant.orden_pago.codigo_proposito: FALTA en el TO-BE».

### Cuadre interno por lado (Σ partes = total del encabezado)

| Base | Documentos | Con violación | Violaciones |
|---|---:|---:|---|
| legado (lados según la pantalla) | 150,719 | 0 | — |
| CONTROL: legado con los lados según el NOMBRE de la tabla | 150,719 | 446,151 | cliente: principal ≠ total del encabezado: 150,719; cliente: desglose incompleto (< 3 partidas): 150,719; corresponsal: CONCILIADA y Σ ≠ total: 138,177; corresponsal: VENCIDA con partidas: 6,397; corresponsal: ENVIADA con partidas: 139 |
| TO-BE decant_migracion | 150,719 | 0 | — |
| TO-BE decant_motor | 150,719 | 0 | — |
| TO-BE decant_sombra | 150,719 | 0 | — |

Lados según el BINDING de la pantalla (T4): «Liquidado por el corresponsal» = conjunto 1 = `dbo.partida_solicitada` → `liquidadoPorElCorresponsal`; «Solicitado por el cliente» = conjunto 2 = `dbo.partida_liquidada` → `solicitadoPorElCliente`.

## 2. Medir el motor (replay sólo del universo, hasta el corte)

| Regla | Qué | Origen | Casos | Coinciden | % | defecto nuestro | regla real del legado | discrepancia del legado | avance de producción |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| R01 | folio FX: consumible en orden de llegada | `sp_registrar_operacion` | 412,125 | 412,125 | 100.0 | 0 | 0 | 0 | 0 |
| R02 | tipo de cambio calculado (referencia × margen) | `sp_registrar_operacion` | 358,423 | 358,423 | 100.0 | 0 | 0 | 0 | 0 |
| R03 | monto en pesos ROUND(monto × tc, 2) | `sp_registrar_operacion` | 412,125 | 412,125 | 100.0 | 0 | 0 | 0 | 0 |
| R04 | folio OP: consumible por documento; el re-registro lo conserva | `sp_registrar_orden` | 150,719 | 150,719 | 100.0 | 0 | 0 | 0 | 0 |
| R05 | partidas del cliente (principal, comisión que trunca, IVA, gastos OUR) | `sp_registrar_orden` | 497,556 | 497,556 | 100.0 | 0 | 0 | 0 | 0 |
| R06 | partidas del corresponsal desde el buzón (llave UETR / :21:) | `sp_registrar_liquidacion` | 244,869 | 244,869 | 100.0 | 0 | 0 | 0 | 0 |
| R07 | estatus del documento (liquidación, D3, vencimiento con reloj inyectado, conciliación D2) | `sp_registrar_liquidacion + sp_conciliar` | 150,719 | 150,719 | 100.0 | 0 | 0 | 0 | 0 |
| R08 | horas de liquidación con los instantes (T5) | `sp_conciliar` | 144,183 | 102,769 | 71.28 | 0 | 0 | 41,414 | 0 |
| R09 | re-registro: registros por documento y fecha del más reciente | `sp_registrar_orden` | 150,719 | 150,719 | 100.0 | 0 | 0 | 0 | 0 |
| R11 | consecutivos al final (siguiente folio FX y OP) | `dbo.folio` | 2 | 2 | 100.0 | 0 | 0 | 0 | 0 |
| R12 | liquidaciones descartadas por llegar vencidas (D3, visibles en el TO-BE) | `sp_registrar_liquidacion` | 5,776 | 5,776 | 100.0 | 0 | 0 | 0 | 0 |

Árbitros que absolvieron (con su auditoría):

- **R08 · T5-desfase-fijo** (discrepancia del legado, ADR 0008): 41,414 casos, 0 con la auditoría fallida. el legado resta una hora fija a la hora de Nueva York; el TO-BE usa los instantes. Pregunta cerrada: ¿Las horas de liquidación se calculan con el desfase real de Nueva York (TO-BE) o se conserva la hora fija del legado (una hora de más entre marzo y noviembre desde 2023)? Ejemplo: legado − TO-BE = 1.00 h; (NY − CDMX) − 1 h en esos instantes = 1 h.

### Hipótesis y controles

| Regla | Hipótesis | Elegida | Casos | Coinciden | % |
|---|---|---|---:|---:|---:|
| R05 comisión (D1) | trunca (ROUND(x, 2, 1)) | sí | 150,719 | 150,719 | 100.0 |
| R05 comisión (D1) | redondea a la mitad | no | 150,719 | 123,175 | 81.72 |
| R07 estatus | CONTROL: al azar con la distribución del legado | no | 150,719 | 127,259 | 84.43 |
| | por clase: {'CONCILIADA': 91.7, 'DIFERENCIA': 4.0, 'VENCIDA': 4.3, 'ENVIADA': 0.0} | | | | |

### Sólo marca (bandera apagada: el motor marca ✔/✘ y no actúa)

| Regla | Marcas | ✔ | ✘ | Coinciden con la bitácora del legado | % | Actuados por el legado sin marca |
|---|---:|---:|---:|---:|---:|---:|
| R10-vencimiento | 110,424 | 6,397 | 104,027 | 110,424 | 100.0 | 0 |
| R07-conciliacion | 144,183 | 138,177 | 6,006 | 144,183 | 100.0 | 0 |

## 3. Paridad de reporte (TO-BE en sombra contra lo que el legado publicó)

Publicado: `salida_reporte_del_mes_2023-12-29.jsonl` (7,492 renglones, sha256 `dc03a5d23611ad8e…`). TO-BE: 7,673 renglones. Comunes 7,492; sólo en el TO-BE 181; sólo en el legado 0; comunes con alguna celda distinta 7,492.

| Orden (inversiones, por llave natural) | Pares de contrato | Inversiones de contrato | Pares empatados | % empatados invertidos |
|---|---:|---:|---:|---:|
| piso: el legado re-corrido contra lo que publicó (esta corrida) | 26,515,033 | 0 | 1,546,253 | 7.08 |
| TO-BE contra lo publicado | 26,515,033 | 0 | 1,546,253 | 47.24 |

**Veredicto del orden:** contrato en 0; los empates no son contrato: el propio legado invierte 7.08 % de sus pares empatados en esta corrida y el TO-BE 47.24 %.

| Categoría | Diferencias |
|---|---:|
| defecto nuestro | 0 |
| regla real del legado | 14,984 |
| discrepancia del legado | 0 |
| avance de producción | 181 |

- **avance** (avance de producción, corte medido (paridad/corte.py)): 181 casos, 0 con la auditoría fallida. el TO-BE ya vio una confirmación del corresponsal posterior al corte. Ejemplo: evento 2023-12-29T13:16:00+00:00 > corte; legado vivo: [(244895, Decimal('1737.48'))] (id > 244869 = posterior al corte por identidad).
- **hora-local-sin-zona** (regla real del legado, ADR 0008): 14,984 casos, 0 con la auditoría fallida. el legado publica la hora LOCAL sin zona (la nuestra de la Ciudad de México, la del corresponsal de Nueva York); el TO-BE publica la misma hora con su desfase y no replica el formato. Ejemplo: hora local 2023-11-30 14:00:20; desfase de la zona: True.

## 4. Gemelos (pantalla de detalle del legado contra el JSON de la API)

| Caso | Operación | Campos comparados | Distintos | Rejillas (binding → campo del TO-BE) |
|---|---:|---:|---:|---|
| conciliada con re-registros y gastos OUR | 682 | 60 | 0 | rejilla-liquidado → liquidadoPorElCorresponsal (1 renglones, iguales); rejilla-solicitado → solicitadoPorElCliente (4 renglones, iguales) |
| diferencia en yenes (D2) | 148 | 60 | 0 | rejilla-liquidado → liquidadoPorElCorresponsal (2 renglones, iguales); rejilla-solicitado → solicitadoPorElCliente (3 renglones, iguales) |
| vencida sin partidas del corresponsal, en efectivo (T3) | 559 | 48 | 0 | rejilla-liquidado → liquidadoPorElCorresponsal (0 renglones, iguales); rejilla-solicitado → solicitadoPorElCliente (3 renglones, iguales) |

No expuestos: `orden_id`: llave interna del legado (cambia con cada re-registro); el TO-BE expone la UETR.

## Trampas de las rondas a ciegas: ¿la paridad vio su efecto?

Medido tal cual, sin ajustar nada: la paridad sólo puede ver el efecto de una trampa en una salida que compara (`tablas`: verificar la migración: las 7 tablas, byte a byte; `dbo.sp_reporte_ordenes`: paridad de reporte (el reporte publicado al respaldar); `dbo.sp_detalle_operacion`: gemelos (la pantalla de detalle)).

| Ronda | Trampa | Objeto | ¿Lo vio? | Evidencia |
|---|---|---|---|---|
| ronda 1 | T1 · variable asignada desde varias filas | `dbo.sp_reporte_posicion` | no aplica (latente) | latente: con el plan de hoy coincide 9,341 de 9,341 (catálogo); además la paridad de S2 no compara esa salida |
| ronda 1 | T2 · reloj del servidor por una variable | `dbo.sp_ordenes_por_vencer` | no | la paridad de S2 no compara `dbo.sp_ordenes_por_vencer`: compara las tablas, el reporte de órdenes y la pantalla de detalle. Un efecto en una salida que no se compara no se puede ver |
| ronda 1 | T3 · espacios finales en la referencia del corresponsal | `dbo.partida_solicitada.referencia` | sí | byte a byte, dbo.partida_solicitada → decant.partida_corresponsal (T4): 48,013 celdas de `referencia` difieren del TO-BE (que guarda la referencia del buzón, sin relleno). El parche ciega1_T3 que las explica (48,013) se escribió con el catálogo YA revelado; sin él, la verificación falla con esas celdas. La paridad de reporte no la ve: el reporte no imprime la referencia |
| ronda 2 | T1 · ORDER BY dentro de una vista (TOP 100 PERCENT) | `dbo.vw_liquidaciones_recientes` | no | la paridad de S2 no compara `dbo.vw_liquidaciones_recientes`: compara las tablas, el reporte de órdenes y la pantalla de detalle. Un efecto en una salida que no se compara no se puede ver |
| ronda 2 | T2 · asignación por PK que el JOIN multiplica | `dbo.sp_constancia_operacion` | no aplica (latente) | latente: las 104,773 constancias muestran hoy la orden vigente (catálogo); además la paridad de S2 no compara esa salida |
| ronda 2 | T3 · división entera y AVG de enteros | `dbo.sp_tablero_corresponsales` | no | la paridad de S2 no compara `dbo.sp_tablero_corresponsales`: compara las tablas, el reporte de órdenes y la pantalla de detalle. Un efecto en una salida que no se compara no se puede ver |

## Tiempos

| Paso | Segundos |
|---|---:|
| restaurar el respaldo en un contenedor limpio | 17.8 |
| extraer universo y oráculo | 41.7 |
| cargar decant_migracion y comparar su esquema | 38.3 |
| cargar decant_motor y comparar su esquema | 40.3 |
| cargar decant_marca_vencimiento y comparar su esquema | 50.2 |
| cargar decant_marca_conciliacion y comparar su esquema | 50.2 |
| cargar decant_sombra y comparar su esquema | 41.4 |
| verificar la migración (byte a byte y cuadres) | 81.2 |
| medir el motor | 34.2 |
| paridad de reporte | 9.7 |
| gemelos | 2.4 |
