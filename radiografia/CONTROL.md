# Control: la radiografía sobre bases públicas de Microsoft

Una radiografía que sólo se prueba sobre el legado que uno mismo sembró puede «detectar» lo que su autor ya sabía.
El control la corre, sin cambiar nada, sobre bases que no escribimos y que se tienen por limpias.

## Estado de los controles con `detectores-v4`

- **Ninguno de los dos controles públicos es un control de generalización.**
  - WideWorldImporters es de ENTRENAMIENTO desde la v1. Para la v4 se usó, además, una forma de su código ya
    publicada en el informe de la v3: `FROM t FOR SYSTEM_TIME AS OF @f AS alias` (tablas temporales), que el lector
    de fuentes del FROM ahora salta.
  - AdventureWorks fue el control APARTADO de la v2. Su resultado ya es conocido, y la v4 se escribió sabiendo qué
    hacían sus tres `ufnGetProduct*` (límite «el ON» documentado con la v3). Re-correrlo sólo mide los falsos
    positivos NUEVOS que meten los detectores v4, y si esas tres funciones salen ahora por la razón correcta.
- **El control real de la v4 es una NUEVA siembra a ciegas** (ronda 3, procedimiento en el README). La ronda 1
  (`CONTROL_CIEGO.md`) dio 0 de 3 con la v2 y la ronda 2 (`CONTROL_CIEGO_2.md`) 0 de 3 con la v3. Detectar ahora sus
  6 trampas no cuenta como control: los catálogos son conocidos y los arreglos de la v3 y la v4 salieron de ellos.

## Detectores congelados vigentes: `detectores-v4`

Los detectores son tres archivos. Se congelaron en el tag `detectores-v4` con estos sha256, y la prueba
`test_los_detectores_estan_congelados` falla si cualquiera cambia:

```
5cf30e52b92687831c998b0f869dfbb980578e91af9a290b44f09fe4f79c2192  radiografia/tsql.py
d1babf3b81166df433b8ac1186930b8cd94c4d0ddc1a847d250f2b6404cffdf7  radiografia/patrones.py
43aa47868fb8f6c919b4d8df3cd63d084511dd3426529fc8d03e54277fd9256d  radiografia/datos.py
```

`datos.py` no cambió desde la v3. Qué cambió de la v3 a la v4: los tres arreglos genéricos que propuso quien sembró
la ronda 2. Ninguno depende de los nombres de sus trampas:

1. **ORDER BY que no ordena:** `TOP 100 PERCENT` o `TOP (100) PERCENT` con ORDER BY en una vista, una tabla
   derivada (`FROM/JOIN/APPLY ( … )`), una CTE o el `RETURN` de una función en línea. El optimizador descarta ese
   TOP y su ORDER BY. Es forma léxica y se reporta en el objeto que lo define, con la clave `top_sin_order_by` y
   `forma: orden_que_no_ordena`. No se marca el SELECT final de un procedimiento (ése sí ordena), un `TOP n` con
   ORDER BY (elige filas) ni un `TOP 100 PERCENT` dentro de EXISTS o IN.
2. **La unicidad es la del CONJUNTO:** en `SELECT @v = … FROM … [JOIN …]`, cada tabla debe quedar fija por una
   llave ÚNICA suya (PK o índice único sin filtro del esquema restaurado), igualada con AND, en el WHERE o en su
   ON, a constantes, variables o columnas de tablas ya fijas. Una tabla que entra por el lado N de una llave
   foránea no queda fija aunque el WHERE cubra la PK del FROM. Sólo se reporta si alguna variable toma una
   columna de una tabla sin fijar: si toma sólo de tablas fijas, todas las filas le dan el mismo valor. Vistas,
   tablas derivadas, funciones, variables de tabla y temporales no tienen metadatos: no se juzgan. Control
   dentro del legado: la asignación por PK de `sp_registrar_orden` sigue sin marcarse.
3. **División entera:** categoría nueva `division_entera`. Se reporta `/` cuando los DOS lados son enteros, con
   una inferencia mínima de tipos: literales sin punto decimal, columnas int/bigint/smallint/tinyint (resueltas
   por las fuentes del FROM de su consulta), `COUNT(*)`, `DATEDIFF` y `AVG(<entero>)` (lo que propuso la ronda 2),
   y además variables y parámetros declarados enteros, `SUM`/`MIN`/`MAX` de enteros, `CAST`/`CONVERT` a entero,
   `ISNULL`/`NULLIF`/`COALESCE`, un `CASE` con todos sus resultados enteros y la aritmética entre enteros. Lo que no
   se puede tipar no se reporta. Control dentro del legado: las divisiones entre `60.0` de `sp_conciliar` no se
   marcan, y una prueba lo exige.

Historial de congelamientos:

| Tag | Archivo | sha256 |
|---|---|---|
| `detectores-v3` | `radiografia/tsql.py` | `f79f123a08aa370e2a9dd10053f03f36c8b089b06e4616843ddd4e908465f2bd` |
| `detectores-v3` | `radiografia/patrones.py` | `071d6b38652fa72e5508601cc0ea45efffd8f3a7fe1830635d5409d75ee16bbe` |
| `detectores-v3` | `radiografia/datos.py` | `43aa47868fb8f6c919b4d8df3cd63d084511dd3426529fc8d03e54277fd9256d` |
| `detectores-v2` | `radiografia/tsql.py` | `8e29395ee20f056a02e1858abb3812dd0a05747a6d0c531ada5881e34e86ff6b` |
| `detectores-v2` | `radiografia/patrones.py` | `70f4415556b3386b31264bbe8a28eededb35c548b351b9f0157fddf0d8788b3e` |
| `detectores-v2` | `radiografia/datos.py` | `ab60df538a88a6423e1cb734abc7c5e33d620425e580f33d18573b01fc29a5a9` |

## Corrida de `detectores-v4` sobre los controles públicos

Corridas una vez el 24-nov-2026, desde un clon limpio en el tag `detectores-v4`, sobre los mismos respaldos
oficiales (sha256 verificados). Los informes completos, sin editar, están en
[`control/v4/wideworldimporters/`](control/v4/wideworldimporters/radiografia.md) y
[`control/v4/adventureworks/`](control/v4/adventureworks/radiografia.md). Los de la v2 y la v3 se conservan donde
estaban.

**Falsos positivos nuevos: 0 en los dos controles.** Ningún hallazgo aparece ni desaparece respecto a la v3. Lo
único que cambia es el detalle de las tres asignaciones de AdventureWorks. Lo que sigue se verificó leyendo el
código y los datos en una restauración aparte, de sólo lectura, sin volver a correr los detectores.

| Control | Hallazgos v3 → v4 | Nuevos | Falso positivo | Lectura |
|---|---:|---:|---:|---|
| WideWorldImporters | 273 → 273 | 0 | 0 | Los 273 son idénticos a la v3: categoría, objeto, línea y detalle. Sus 47 módulos traen 5 divisiones y las 5 son entre `100.0` (impuestos y descuentos en `GetOrderUpdates`, `CalculateCustomerPrice` e `InvoiceCustomerOrders`): bien NO marcadas como división entera. No hay `TOP 100 PERCENT` ni asignaciones con JOIN. |
| AdventureWorks | 173 → 173 | 0 | 0 | Las 3 asignaciones de `ufnGetProductListPrice`, `ufnGetProductDealerPrice` y `ufnGetProductStandardCost` siguen marcadas, **ahora por la razón correcta**: «el historial entra por un INNER JOIN que iguala `productid`, sin cubrir ninguna llave única suya (`productid, startdate`)». La v3 decía «sin WHERE» y miraba sólo `Product`. Siguen latentes: 0 periodos traslapados en `ProductListPriceHistory` y en `ProductCostHistory`. Los 51 módulos no tienen ninguna división ni `TOP 100 PERCENT`, y ésas son las únicas 3 asignaciones con JOIN. |

**Lectura:**

1. **Unicidad del conjunto:** el límite «el ON» de la v3 queda cubierto en el único caso público que lo mostraba.
   Las 3 funciones de AdventureWorks salen por la llave del historial, no por un WHERE ausente. Es un caso conocido
   desde la v3: confirma el arreglo, no lo valida.
2. **ORDER BY que no ordena y división entera:** 0 hallazgos en los dos controles. Sin casos positivos fuera del
   legado, sólo hay especificidad medida: 5 divisiones entre decimales bien ignoradas, ningún `TOP 100 PERCENT`.
   La sensibilidad queda por medir en la ronda 3.
3. Nada de esto valida la v4. Su control real es la siembra a ciegas ronda 3.

### Límites que quedan con la v4

- **Lo que se ve, no lo que se infiere.** Sigue siendo un analizador léxico con niveles de paréntesis, no un parser
  de T-SQL: SQL dinámico (`EXEC (@sql)`, `sp_executesql`) no se analiza.
- **ORDER BY que no ordena:** se reporta la vista o la tabla derivada, no el procedimiento que la lee confiando en
  su orden. Tampoco cubre otras formas del mismo engaño, como llenar una temporal con `INSERT … SELECT … ORDER BY`
  y leerla sin ORDER BY.
- **Unicidad del conjunto:** sólo juzga `SELECT @v = …`. Un `UPDATE … FROM` con un JOIN 1:N (que también escribe
  un valor arbitrario) no se juzga. Las fuentes sin metadatos (vistas, tablas derivadas, funciones, variables de
  tabla y temporales) cuentan como fijas: es un falso negativo posible a cambio de no inventar. Sólo fijan las
  igualdades `columna = expresión` unidas con AND; un `IN (@x)` o una función sobre la llave no fijan nada.
- **División entera:** no tipa columnas de vistas, tablas derivadas, temporales ni variables de tabla, ni el
  resultado de funciones del usuario o tipos de alias. `AVG(<entero>)` sin una división (que en PostgreSQL da
  `numeric` y en SQL Server trunca) no se reporta: el arreglo pedido era la `/`.
- Siguen los límites anteriores: las columnas calculadas cuentan como dato en `espacios_finales` (v3), e IF EXISTS
  no distingue una variable de tabla de una tabla (v2).

## Historial: corrida de `detectores-v3` sobre los controles públicos

Corridas una vez el 24-nov-2026, con el árbol limpio en el tag `detectores-v3`, sobre los mismos respaldos
oficiales (sha256 verificados). Los informes completos, sin editar, están en
[`control/v3/wideworldimporters/`](control/v3/wideworldimporters/radiografia.md) y
[`control/v3/adventureworks/`](control/v3/adventureworks/radiografia.md). Los de la v2 se conservan donde estaban.

**Lo que cambió respecto a la v2:** ningún hallazgo de la v2 desapareció. Los nuevos son exactamente estos 14. Se
clasificaron leyendo el código y los datos en una restauración aparte, de sólo lectura, sin volver a correr los
detectores.

| Control | Hallazgos v2 → v3 | Nuevos | Patrón real | Falso positivo | Lectura |
|---|---:|---:|---:|---:|---|
| WideWorldImporters | 262 → 273 | 11 `espacios_finales` | 11 | 0 | Los 11 valores terminan de verdad en espacio, por ejemplo `'Isabell '` y `'David Novacek '`. En datos capturados: `People.PreferredName` (8), `People.FullName`, `Customers.CustomerName`, `PackageTypes.PackageTypeName` y sus copias `_Archive`. Tres son columnas CALCULADAS: `People.SearchName` y `StockItems.SearchDetails` son `concat(…, N' ', …)` y rellenan por diseño cuando el segundo término es NULL (199 de 227 artículos); `Invoices.ConfirmedReceivedBy` sale de un JSON con el nombre ya relleno (87 facturas). **Límite:** el detector no omite columnas calculadas, que no se migran como dato. |
| AdventureWorks | 170 → 173 | 3 `top_sin_order_by` (asignación desde varias filas) | 3 | 0 | `ufnGetProductListPrice`, `ufnGetProductDealerPrice` y `ufnGetProductStandardCost` asignan el precio o el costo desde un historial filtrado por `@OrderDate BETWEEN StartDate AND EndDate`: ninguna llave única garantiza una sola fila. Hoy es latente (0 periodos traslapados en los dos historiales). **Pero el detector lo marca por la razón EQUIVOCADA:** dice «sin WHERE» porque el filtro va en el `JOIN … ON` y sólo lee el WHERE. Si leyera el ON, juzgaría sólo la tabla del FROM (`Product`, única por `ProductID`) y NO lo marcaría: un falso negativo escondido detrás de un acierto. |

**Lectura:**

1. Los 3 arreglos no metieron ningún falso positivo en sentido estricto: la forma existe en los 14 hallazgos nuevos.
2. Sí aparecieron dos límites nuevos, que no se corrigen bajo este congelamiento:
   - las columnas calculadas cuentan como dato;
   - la asignación desde varias filas no lee el `ON`, y con un JOIN sólo juzga la tabla del FROM.
3. Reloj por variable: 0 hallazgos en los dos controles. Sin casos positivos fuera del legado, no hay sensibilidad
   medida, sólo especificidad.
4. Nada de esto valida la v3. Su control real es la siembra a ciegas ronda 2.

---

# Historial: control apartado de la v2 sobre AdventureWorks (una sola corrida, tal cual)

- **Fuente:** `AdventureWorks2022.bak` del release `adventureworks` del repositorio `microsoft/sql-server-samples`
  en GitHub. sha256 `d17567adb1521f972e1dc183a7216cea869c4580b5d75632425bcadbaf82ce5e`, 209,838,080 bytes.
- **Corrida única:** 24-nov-2026, con el árbol limpio en el commit del tag `detectores-v2`:

  ```
  python -m radiografia --bak AdventureWorks2022.bak --base AdventureWorks2022 \
      --salida radiografia/control/adventureworks
  ```

- **Informe completo, sin editar:** [`control/adventureworks/radiografia.md`](control/adventureworks/radiografia.md).
- **Qué se analizó:** 71 tablas con 760,837 filas y 51 módulos (10 procedimientos, 20 vistas, 11 funciones y 10
  triggers). Tiempo: 26 s.
- **Cómo se clasificó:** leyendo el código y los datos en una restauración aparte, de sólo lectura, sin volver a
  correr los detectores. Las consultas están en la tabla.

Definición, la misma para los dos controles: un hallazgo es **patrón real** si la forma existe de verdad (por
ejemplo, un 0 que significa «no aplica» en vez de NULL), sea o no un defecto. Es **falso positivo** si la forma no
existe (un 0 que es una cantidad legítima).

| Patrón | Hallazgos | Patrón real | Falso positivo | Lectura (y consulta de verificación) |
|---|---:|---:|---:|---|
| TOP sin ORDER BY | 0 | 0 | 0 | — |
| INNER JOIN a una tabla hija | 10 | 10 | 0 | La forma existe en las 10, pero ninguna pierde datos HOY y todas son la intención: precio o costo a una fecha, contacto, descripción, cliente individual. Las vistas de empleados no pierden a nadie (0 empleados sin historial de departamento) y `vSalesPersonSalesByFiscalYears` tampoco (0 vendedores sin pedidos). **0 defectos.** |
| Reloj del servidor en una regla | 0 | 0 | 0 | Los 10 triggers sellan `ModifiedDate` con `GETDATE()` dentro de un SET: bien clasificados como asignación. |
| IF EXISTS sin ELSE que escribe | 4 | 0 | 4 | `ufnGetContactInformation`: los 4 escriben sólo en la variable de tabla que regresa la función (`@retContactInformation`), no en datos. **Límite del detector:** no distingue una variable de tabla de una tabla. No se corrige: los detectores están congelados. |
| Desfase horario fijo | 0 | 0 | 0 | — |
| **ROUND que trunca (validación de D1)** | **0** | 0 | **0** | Ningún falso positivo. AdventureWorks no tiene un solo `ROUND` que trunque, así que el control mide su ESPECIFICIDAD (no dispara sobre ROUND normales) pero no su sensibilidad fuera del legado. |
| Centinelas | 14 | 8 | 6 | Reales: `Shelf = 'N/A'` (290) con `Bin = 0` (328); `ReferenceOrderLineID = 0` y `ActualCost = 0` en las 31,002 transacciones de orden de trabajo, en las dos tablas de historial; `ListPrice = 0` y `StandardCost = 0` en 200 de los 209 componentes que no se venden. Falsos: `EmailPromotion` 0 (es un código), `BOMLevel` 0, `DaysToManufacture` 0, `ScrappedQty` 0, `RejectedQty` 0 y `UnitPriceDiscount` 0. Precisión 8/14. |
| Mojibake | 0 | 0 | 0 | — |
| Re-registro | 0 | 0 | 0 | — |
| Llave candidata con duplicados (informativo) | 3 | — | — | Direcciones y descripciones que se repiten de verdad; bien NO llamadas re-registro. |
| Columnas / tablas que ningún módulo lee | 72 / 38 | — | — | Inventario: la aplicación de AdventureWorks lee las tablas directo. |
| Literales mágicos (inventario) | 29 en 20 módulos | — | — | — |

**Lo que dice el control apartado:**

1. Los detectores de alta señal (TOP sin ORDER BY, reloj en regla, desfase fijo, ROUND que trunca, mojibake y
   re-registro) dan **0 falsos positivos** sobre una base que no vieron.
2. **IF EXISTS que escribe tiene un límite nuevo**, que WideWorldImporters no mostró: 4 falsos positivos por escribir
   en una variable de tabla. Es justo lo que un control apartado debe encontrar. Queda documentado y no se corrige
   bajo este congelamiento.
3. **INNER JOIN a una hija y centinelas siguen siendo de revisión:** la forma es real casi siempre (10/10 y 8/14),
   pero no distingue defecto de intención.
4. La validación de `round_trunca` es parcial: especificidad sí (0 falsos positivos), sensibilidad sin casos.

El control apartado NO está en el CI: se corre una vez por congelamiento. El CI repite sólo el de entrenamiento.

---

# Control de entrenamiento: WideWorldImporters

- **Fuente:** `WideWorldImporters-Full.bak` del release `wide-world-importers-v1.0` del repositorio
  `microsoft/sql-server-samples` en GitHub. sha256
  `e842bad6ce02f74f166947e559dab1b476edd7eaae3da2ab9e3f522f1dd87124`, 127,111,168 bytes.
- **Orden:**

  ```
  python -m radiografia --bak WideWorldImporters-Full.bak --base WideWorldImporters \
      --salida radiografia/control/wideworldimporters
  ```

- **Informe completo:** [`control/wideworldimporters/radiografia.md`](control/wideworldimporters/radiografia.md)
  (y su `.json`).
- **Qué se analizó:** 48 tablas con 4,713,833 filas y 47 módulos (42 procedimientos, 3 vistas y 2 funciones).
  No tiene triggers. No se restauró su msdb, así que no hay jobs que inventariar.
- **Tiempo:** 48–65 s (arranque del contenedor 6 s, restauración 8 s, patrones sobre datos 30 s).

## Resultado (detectores congelados `detectores-v2`)

La última corrida, ya con el detector `round_trunca`, da lo mismo que la anterior: 0 ROUND que truncan en
WideWorldImporters.

Un falso positivo, aquí, es un hallazgo que al leer el código o los datos NO resulta ser un defecto.

| Patrón | Hallazgos | Defectos reales | Falsos positivos | Lectura |
|---|---:|---:|---:|---|
| TOP sin ORDER BY | 0 | 0 | 0 | — |
| INNER JOIN a una tabla hija | 7 | 0 | 7 | Extractos encabezado→renglones (`Integration.Get*Updates`) y existencias de un artículo: ahí el INNER JOIN es la intención. |
| Reloj del servidor dentro de una regla | 0 | 0 | 0 | WideWorldImporters usa `SYSDATETIME()` sólo como sello (VALUES/SELECT) y recibe el corte por parámetro. |
| IF EXISTS sin ELSE que escribe datos | 0 | 0 | 0 | — |
| IF EXISTS sin ELSE de guarda o DDL (informativo) | 65 | 0 | — | 64 `IF NOT EXISTS … CREATE/EXEC` de configuración idempotente y 1 `IF EXISTS … THROW`. |
| Desfase horario fijo | 0 | 0 | 0 | — |
| ROUND que trunca (nuevo en v2) | 0 | 0 | 0 | No cuenta como validación: WideWorldImporters es de entrenamiento. |
| Centinelas | 7 | 0 | 3 | Con la definición de «patrón real» del control apartado: 4 son reales por diseño (importe sin impuesto e impuesto en 0 en los pagos: un 0 en vez de NULL) y 3 son ceros legítimos (saldo pendiente 0 = pagado, dos tablas; 0 artículos refrigerados). Antes se contaron los 7 como falsos positivos. |
| **Mojibake** | **5** | **5** | **0** | **Daño REAL en la muestra: «Chávez» guardado como «ChÃ¡vez» en `Application.People` (FullName, SearchName), `Sales.Customers` (dos direcciones) y 213 facturas (`Sales.Invoices.DeliveryInstructions`). No hay ni una «Chávez» bien escrita.** |
| Re-registro | 0 | 0 | 0 | — |
| Llave candidata con duplicados (informativo) | 9 | 0 | — | Nombres de ciudad, direcciones y correos que se repiten de verdad. El detector NO los llama re-registro. |
| Columnas que ningún módulo lee | 75 | — | — | En WideWorldImporters la aplicación lee las tablas directo, sin procedimientos. «Ningún módulo la lee» no es «nadie la lee». |
| Tablas que ningún módulo lee | 7 | — | — | Igual; 5 son tablas `_Archive` (historial temporal). |
| Literales mágicos (inventario) | 87 en 29 módulos | — | — | Inventario para leer, no defectos. |

**Lo que dice el control:**

1. **Precisión por patrón sobre código limpio.** TOP sin ORDER BY, reloj en regla, IF EXISTS que escribe, desfase
   fijo y re-registro: 0 hallazgos y 0 falsos positivos. Sobre el legado esos mismos detectores encuentran lo
   sembrado. Su señal es alta.
2. **INNER JOIN a una hija y centinelas numéricos son patrones de REVISIÓN.** Encuentran la forma, no la
   intención: 7 y 7 falsos positivos aquí, 1 y 3 aciertos en el legado. El informe los presenta así y nadie los
   arregla sin leerlos.
3. **Columnas y tablas sin lectura sólo valen si todo el acceso pasa por la base.** En el legado la pantalla sólo
   llama procedimientos y el detector encuentra la columna sembrada. En WideWorldImporters el resultado es
   inventario, no hallazgo.
4. **El detector de mojibake encontró un defecto real que nadie sembró** en una base pública de Microsoft.

## Versión 1: lo que el control cambió en los detectores

La primera corrida (mismos datos, detectores antes del control) dio 270 hallazgos. Cada diferencia contra la
versión final se debe a un arreglo GENÉRICO que se hizo por un falso positivo concreto; ninguno se hizo leyendo el
catálogo de trampas del legado. Tras cada arreglo, la radiografía del legado se volvió a medir: sigue en 8 de 9.

| Patrón | v1 | Final | Falso positivo de la v1 → arreglo genérico | Prueba de regresión |
|---|---:|---:|---|---|
| TOP sin ORDER BY | 1 | 0 | `Website.SearchForPeople` SÍ tiene `ORDER BY`: el analizador cortaba la consulta en el `END` de un `CASE`. Era un **defecto de la radiografía**, no del patrón. Ahora el `ELSE`/`END` de un `CASE` no abre ni cierra sentencias. | `test_top_con_order_by_tras_un_case_no_se_detecta` |
| INNER JOIN a una tabla hija | 9 | 7 | Dos con llave foránea a sí misma (`Sales.Customers` → cliente que paga): no se sabe qué lado es el hijo → se omiten. | `test_llave_foranea_a_si_misma_no_se_detecta` |
| IF EXISTS sin ELSE | 65 | 0 (+65 informativos) | Guardas de configuración idempotente y un `THROW`: el camino no tomado no pierde datos. Sólo es hallazgo si el cuerpo escribe datos (INSERT/UPDATE/DELETE/MERGE). | `test_if_not_exists_de_configuracion_es_guarda_no_defecto`, `test_if_exists_que_lanza_un_error_es_guarda` |
| Centinelas | 8 | 7 | Un id de empaque `9` fuera del rango 6–7. 9 y 99 son códigos legítimos demasiado comunes: dejan de contar como centinela (siguen 0, −1, 999…). | `test_nueve_no_se_toma_por_centinela` |
| Re-registro | 4 | 0 | (a) Tablas de historial temporal (`*_Archive`), que guardan versiones por diseño → se omiten. (b) Personas con el mismo nombre que «comparten» 69 % de columnas por banderas y NULL; dos filas cualesquiera comparten 63 %. Ahora el re-registro exige parecerse 30 puntos MÁS que la base de la tabla. En el legado: 82 % contra 20 %. | `test_re_registro_exige_parecerse_mas_que_dos_filas_cualesquiera` |

Lo que el control no cambió: los 7 INNER JOIN y los 7 centinelas restantes. Bajarlos exigiría saber la
intención del código o el significado de la columna, y eso ya no es un patrón genérico. Se quedan como
revisión humana.

## Cómo repetirlo

En CI corre el job `control-publico`: descarga el respaldo, verifica su sha256, lo radiografía y sube el informe
como artefacto. En local:

```
mkdir -p muestras && curl -fsSL -o muestras/WideWorldImporters-Full.bak \
  https://github.com/Microsoft/sql-server-samples/releases/download/wide-world-importers-v1.0/WideWorldImporters-Full.bak
sha256sum muestras/WideWorldImporters-Full.bak     # e842bad6…1dd87124
python -m radiografia --bak muestras/WideWorldImporters-Full.bak --base WideWorldImporters \
    --salida radiografia/control/wideworldimporters
```
