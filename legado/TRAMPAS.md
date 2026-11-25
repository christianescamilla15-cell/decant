# Catálogo de trampas del legado `BFN_DIVISAS`

Este archivo es la verdad del autor del legado: qué defectos se sembraron, dónde y cuánto pesan en los datos.
**La radiografía no lo lee.** Sus detectores buscan patrones genéricos. Sólo `radiografia/medicion.py`, al
final y como medición, cruza lo que se detectó contra la tabla de abajo. Si los detectores leyeran este archivo,
la detección sería circular.

Las cifras salen de la generación por omisión (semilla `20231229`, 400 operaciones por día, del 1-ene-2021 al
respaldo del 29-dic-2023 a las 06:00, hora de la Ciudad de México) y las comprueban las pruebas de
`tests/test_generador.py`.

## Tabla de medición

Una trampa cuenta como detectada si TODAS sus señales aparecen en el informe de la radiografía
(`categoría → objeto`). Una trampa sin señales no tiene un patrón genérico que la delate en S1.

| Id | Trampa | Señales esperadas |
|---|---|---|
| T1 | TOP sin ORDER BY con empates reales | `top_sin_order_by → dbo.sp_lista_operaciones` |
| T2 | INNER JOIN que pierde hijos | `inner_join_hija → dbo.vw_reporte_ordenes` |
| T3 | Centinelas («NA», 0) en vez de NULL | `centinela → dbo.operacion.cuenta_clabe` · `centinela → dbo.orden_pago.bic_intermediario` · `centinela → dbo.operacion.tipo_cambio_referencia` |
| T4 | Lados invertidos en el detalle | |
| T5 | Horario de verano (hora local, corresponsal en Nueva York) | `desfase_horario_fijo → dbo.sp_conciliar` |
| T6 | Columna que ningún reporte ni procedimiento imprime | `columna_sin_lectura → dbo.orden_pago.codigo_proposito` |
| T7 | Acentos latin-1 en columnas Unicode | `mojibake → dbo.operacion.cliente` |
| T8 | GETDATE() dentro de una regla | `reloj_en_regla → dbo.sp_conciliar` |
| T9 | Re-registro: el mismo documento con otra llave cada día | `re_registro → dbo.orden_pago.uetr` |
| D1 | La comisión se trunca en vez de redondearse | |
| D2 | Los montos ignoran los decimales de ISO 4217 | |
| D3 | Liquidaciones descartadas en silencio | `if_exists_sin_else → dbo.sp_registrar_liquidacion` |

## Trampas

### T1 · TOP sin ORDER BY con empates reales
- **Dónde:** `dbo.sp_lista_operaciones` (la lista de la pantalla): `SELECT TOP (@maximo) … WHERE fecha_operacion`
  del día, sin `ORDER BY`.
- **En los datos:** `fecha_operacion` es `smalldatetime` (al minuto). El 44.7 % de las operaciones (184,387)
  comparten su minuto con otra, y hasta 24 caen en el mismo minuto. El archivo de sucursales llega a las 22:00
  con horas de la mañana: hay 18,156 saltos en los que el orden por id no es el orden por fecha.
- **Al modernizar:** la pantalla «muestra las primeras 200 del día» en el orden que el plan entregue. Al agregar
  `ORDER BY fecha_operacion` siguen los empates. La comparación con el TO-BE se hace por llave natural y el orden
  se mide por inversiones, nunca por posición.
- **Medido** (`legado/VOLUMEN.md`): esta lista sale idéntica de corrida a corrida a cualquier volumen. Su daño es
  de significado, no de inestabilidad. Lo inestable es el reporte con empates (`sp_reporte_ordenes`).

### T2 · INNER JOIN que pierde hijos
- **Dónde:** `dbo.vw_reporte_ordenes` hace `orden_pago INNER JOIN partida_solicitada`, y `dbo.sp_reporte_ordenes`
  la usa.
- **En los datos:** de 150,724 órdenes vigentes, 6,545 no tienen partidas del corresponsal: 6,397 vencidas y
  148 aún enviadas al respaldo. El reporte «de órdenes» no las muestra.
- **Al modernizar:** un reporte que «cuadra» con el legado puede estar perdiendo exactamente lo mismo que él.

### T3 · Centinelas en vez de NULL
- **Dónde:** `operacion.cuenta_clabe = 'NA'` (operación en efectivo), `orden_pago.bic_intermediario = 'NA'` (sin
  intermediario) y `operacion.tipo_cambio_referencia = 0` (el cajero no la capturó). Las tres columnas son
  `NOT NULL`.
- **En los datos:** 107,265 CLABE «NA» (26 %), 230,306 BIC intermediario «NA» (85 %) y 53,702 tipos de cambio de
  referencia en 0 (13 %).
- **Al modernizar:** cargarlos tal cual inventa una CLABE y un tipo de cambio de cero. Convertirlos a NULL cambia
  los conteos de cualquier reporte que cuente «con CLABE». Contar CONTENIDO, no filas.

### T4 · Lados invertidos en el detalle
- **Dónde:** `dbo.partida_solicitada` guarda lo que LIQUIDÓ el corresponsal (`ABONO`, `COMISION_CORRESPONSAL`,
  hora de Nueva York) y `dbo.partida_liquidada` guarda lo que SOLICITÓ el cliente (`PRINCIPAL`, `COMISION`,
  `IVA`, `GASTOS_OUR`). `sp_detalle_operacion` devuelve primero `partida_solicitada` (conjunto 1) y después
  `partida_liquidada` (conjunto 2). La pantalla (`legado/pantalla/app.py`, `REJILLAS`) pinta el conjunto 1 en
  «Liquidado por el corresponsal» y el 2 en «Solicitado por el cliente». La pantalla es la que tiene razón; los
  nombres de las tablas están cruzados.
- **En los datos:** 244,862 partidas del corresponsal en `partida_solicitada` y 893,190 del cliente en
  `partida_liquidada`.
- **Al modernizar:** quien mapea por nombre de tabla publica los lados al revés. Una radiografía de la base no lo
  ve: no hay patrón de código que lo delate. Se atrapa en S2 con la prueba que lee el BINDING de la pantalla
  (qué conjunto pinta qué rejilla) y lo compara con el contenido de cada tabla.

### T5 · Horario de verano
- **Dónde:** el legado guarda la hora LOCAL de la Ciudad de México (`fecha_operacion`, `fecha_envio`,
  `fecha_registro`) y guarda tal cual la hora local de Nueva York que manda el corresponsal
  (`partida_solicitada.fecha_hora`). `sp_conciliar` calcula
  `horas_liquidacion = DATEDIFF(minute, fecha_envio, DATEADD(hour, -1, ultima)) / 60.0`: supone que Nueva York
  va siempre una hora adelante.
- **En los datos:** México tuvo horario de verano hasta el 30-oct-2022 y Nueva York lo sigue teniendo. Entre el
  2.º domingo de marzo y el 1.er domingo de abril, entre el último domingo de octubre y el 1.er domingo de
  noviembre, y de marzo a noviembre desde 2023, la diferencia es de 2 horas. De 144,179 órdenes conciliadas,
  41,414 (29 %) tienen `horas_liquidacion` con una hora de más, y en 356 eso cambia si «se liquidó en menos de
  24 h». Además, hay operaciones en la 1:00–1:59 que se repite el 31-oct-2021 y el 30-oct-2022 (dos y dos en la
  segunda vuelta): guardadas en hora local, no se puede saber cuál ocurrió primero.
- **Al modernizar:** el TO-BE guarda UTC y calcula bien. Cada diferencia contra el legado en esas ventanas es una
  discrepancia del legado, no un defecto nuestro, y necesita su ADR y su pregunta cerrada a negocio.

### T6 · Columna que ningún reporte ni procedimiento imprime
- **Dónde:** `orden_pago.codigo_proposito` (ISO 20022 `Purp/Cd`). Sólo aparece en la lista de columnas del
  `INSERT` de `sp_registrar_orden`; ningún procedimiento, vista, trigger o job la lee.
- **En los datos:** 251,828 de 270,621 órdenes la traen (93 %).
- **Al modernizar:** ningún reporte ni pantalla la extrañaría si el TO-BE la pierde. Sólo la caza la comparación
  de esquema columna por columna (nivel BD de la paridad).

### T7 · Acentos latin-1 en columnas Unicode (y el daño de `bcp -c`)
- **Dónde:** `operacion.cliente` es `nvarchar`. Entre mar-2021 y jun-2022 la interfaz del archivo de sucursales
  leyó como latin-1 archivos que venían en UTF-8.
- **En los datos:** 21,189 clientes con mojibake (`ARTESANÃ\x8dAS DEL LAGO`). Conviven con nombres sanos con
  acentos y con 22,571 beneficiarios con letras que no caben en latin-1 ni en cp1252 (`Dvořák`, `Łęczyca`,
  `Ελληνική`, `İzmir`).
- **`bcp -c`, medido** (`python -m legado bcp`). En Windows, `bcp -c` escribe con la página ANSI (1252). En Linux,
  mssql-tools18 escribe UTF-8, así que para reproducirlo se fuerza `-C 1252`:
  - `operacion.cliente`: 21,189 renglones con `?` (los caracteres de control del mojibake no existen en cp1252), y
    390,744 de 412,556 que ya no se leen como UTF-8;
  - `orden_pago.beneficiario`: 22,587 renglones distintos del original, 16,884 con `?` y el resto con sustitución
    «parecida» SILENCIOSA (`Ł`→`L`, `ę`→`e`, `İ`→`I`).
  La referencia sin pérdida es `bcp -w` (UTF-16).
- **Al modernizar:** extraer con `-c` destruye datos sin error. Reparar el mojibake es una decisión de negocio
  (¿se corrige el nombre del cliente o se conserva como lo tiene el legado?).

### T8 · GETDATE() dentro de una regla
- **Dónde:** `sp_conciliar` (el job nocturno):
  `UPDATE orden_pago SET estatus = 'VENCIDA' WHERE estatus = 'ENVIADA' AND fecha_envio < DATEADD(day, -3, GETDATE())`.
- **En los datos:** 6,397 órdenes vencidas, cada una vencida por el reloj de SU noche. Al respaldo quedan 148
  enviadas. Si hoy alguien corre el job sobre el respaldo, `GETDATE()` es de 2026 y las vence todas, también las
  enviadas el mismo día del respaldo. La prueba de integración lo demuestra en el motor real, dentro de una
  transacción que se revierte.
- **Al modernizar:** reprocesar otro día da otra respuesta. El TO-BE recibe el reloj inyectado (`IClock`), y el
  replay alimentado del universo debe usar la hora de cada noche.
- Por eso el contenedor del legado corre con el Agent apagado: el job existe en msdb y se inventaría, pero con el
  reloj real vencería todo.

### T9 · Re-registro
- **Dónde:** cada mañana hábil a las 07:00, la interfaz vuelve a dar de alta con `sp_registrar_orden` cada orden
  que el corresponsal no ha liquidado: otra fila, otro `id`, la misma `uetr`, el mismo folio, la misma
  referencia MT103 y un `fecha_registro` nuevo. La anterior queda `REEMPLAZADA`.
- **En los datos:** 104,773 de 150,901 documentos tienen al menos un re-registro: 119,897 filas `REEMPLAZADA`, con
  hasta 5 registros por documento. En el delta del día del respaldo hay 146 re-registros fechados ese mismo día.
- **Al modernizar:** se cruza por llave natural (`uetr`) y se queda el más reciente. Un delta con tope «ayer»
  pierde los re-registros de hoy, y comparar por `id` empareja documentos distintos.

## Defectos del legado: decisión de negocio en S2 (¿replicar o corregir?)

Mientras negocio no decida, el TO-BE replica el defecto y la diferencia queda visible en la paridad.

### D1 · La comisión se trunca en vez de redondearse
- **Dónde:** `sp_registrar_orden`: `ROUND(@monto_mxn * 0.0025, 2, 1)`. El tercer argumento `1` TRUNCA. Hay un
  mínimo de 150.
- **En los datos:** en 27,546 de 55,369 órdenes vigentes con comisión sobre el mínimo, truncar da un centavo menos
  que redondear.
- **Pregunta cerrada:** ¿el TO-BE trunca (como el legado) o redondea (y la comisión de la mitad de las órdenes
  sube un centavo)?

### D2 · Los montos ignoran los decimales de ISO 4217
- **Dónde:** todos los montos son `decimal(18,2)`, aunque el catálogo `moneda.decimales` dice 0 para JPY y 3
  para KWD. El corresponsal abona yenes enteros.
- **En los datos:** 4,511 de 4,561 órdenes vigentes en JPY traen centavos. 4,318 salen en `DIFERENCIA` sólo por
  eso, el 72 % de todas las diferencias.
- **Pregunta cerrada:** ¿el TO-BE redondea al número de decimales de la moneda (y concilia esas órdenes) o
  conserva los centavos que el corresponsal nunca abonará?

### D3 · Liquidaciones descartadas en silencio
- **Dónde:** `sp_registrar_liquidacion` sólo registra la confirmación si la orden sigue `ENVIADA`
  (`IF EXISTS … BEGIN … END`, sin `ELSE`). Si el job ya la venció, la confirmación del corresponsal se pierde sin
  error.
- **En los datos:** 5,776 liquidaciones llegaron después del vencimiento. Las órdenes quedaron `VENCIDA` aunque el
  corresponsal sí pagó.
- **Pregunta cerrada:** ¿el TO-BE registra esas liquidaciones (y reabre la orden) o las rechaza con un error
  visible?

## Sólo documentado (no sembrado)

- **Checksum entre motores:** `HASHBYTES('MD5', columna_nvarchar)` en SQL Server hashea UTF-16LE y `md5(texto)` en
  PostgreSQL hashea UTF-8. El mismo nombre da huellas distintas. Para comparar por huella se convierte antes a la
  misma codificación, por ejemplo con `CAST(… AS varchar(…) COLLATE Latin1_General_100_CI_AS_SC_UTF8)` en
  SQL Server 2019+.
