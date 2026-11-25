# Control: la radiografía sobre una base pública de Microsoft

Una radiografía que sólo se prueba sobre el legado que uno mismo sembró puede «detectar» lo que su autor ya sabía.
El control la corre, sin cambiar nada, sobre una base que no escribimos y que se tiene por limpia:
**WideWorldImporters**, el respaldo oficial de los ejemplos de SQL Server.

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
- **Tiempo:** 48 s (arranque del contenedor 6 s, restauración 8 s, patrones sobre datos 30 s).

## Resultado (versión final de los detectores)

Un falso positivo, aquí, es un hallazgo que al leer el código o los datos NO resulta ser un defecto.

| Patrón | Hallazgos | Defectos reales | Falsos positivos | Lectura |
|---|---:|---:|---:|---|
| TOP sin ORDER BY | 0 | 0 | 0 | — |
| INNER JOIN a una tabla hija | 7 | 0 | 7 | Extractos encabezado→renglones (`Integration.Get*Updates`) y existencias de un artículo: ahí el INNER JOIN es la intención. |
| Reloj del servidor dentro de una regla | 0 | 0 | 0 | WideWorldImporters usa `SYSDATETIME()` sólo como sello (VALUES/SELECT) y recibe el corte por parámetro. |
| IF EXISTS sin ELSE que escribe datos | 0 | 0 | 0 | — |
| IF EXISTS sin ELSE de guarda o DDL (informativo) | 65 | 0 | — | 64 `IF NOT EXISTS … CREATE/EXEC` de configuración idempotente y 1 `IF EXISTS … THROW`. |
| Desfase horario fijo | 0 | 0 | 0 | — |
| Centinelas | 7 | 0 | 7 | Ceros legítimos: saldo pendiente 0 (pagado), 0 artículos refrigerados; y «0 de impuesto» en los pagos, un 0 en vez de NULL decidido por el diseño. |
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
