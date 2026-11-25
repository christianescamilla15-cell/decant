# Control: la radiografía sobre bases públicas de Microsoft

Una radiografía que sólo se prueba sobre el legado que uno mismo sembró puede «detectar» lo que su autor ya sabía.
El control la corre, sin cambiar nada, sobre bases que no escribimos y que se tienen por limpias.

Hay dos controles con papeles distintos:

1. **WideWorldImporters es de ENTRENAMIENTO.** Los arreglos de la v1 de los detectores se hicieron mirando sus
   falsos positivos, así que su resultado ya no prueba que los detectores generalicen.
2. **AdventureWorks es el control APARTADO.** Se corrió UNA sola vez, después de congelar los detectores, y se
   publica tal cual salió. La validación del detector de D1 (`round_trunca`, agregado después de la v1) sólo cuenta
   contra él.

## Detectores congelados: `detectores-v2`

Los detectores son tres archivos. Se congelaron en el tag `detectores-v2` con estos sha256, y la prueba
`test_los_detectores_estan_congelados_en_detectores_v2` falla si cualquiera cambia:

```
8e29395ee20f056a02e1858abb3812dd0a05747a6d0c531ada5881e34e86ff6b  radiografia/tsql.py
70f4415556b3386b31264bbe8a28eededb35c548b351b9f0157fddf0d8788b3e  radiografia/patrones.py
ab60df538a88a6423e1cb734abc7c5e33d620425e580f33d18573b01fc29a5a9  radiografia/datos.py
```

Cambiar un detector después de esto exige un tag nuevo (`detectores-v3`), su sha256 aquí y un control apartado
NUEVO: el de AdventureWorks ya no serviría para validarlo.

## Control apartado: AdventureWorks (una sola corrida, tal cual)

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
