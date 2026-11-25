# Volumen del legado y piso de la paridad: medidos, no adivinados

**Pregunta:** ¿cuántos datos necesita el legado para que el CONTROL NEGATIVO no salga en 0 %, y cuál es el piso
con el que S2 comparará el orden?

El control negativo compara el legado consigo mismo: la misma salida, sobre los mismos datos, tomada dos veces. Si
siempre sale idéntica, la paridad de S2 no tiene listón. Con pocos datos, SQL Server entrega un orden estable
aunque la consulta tenga empates.

## Métrica: inversiones por llave natural (la que usará S2)

El orden NO se compara por posición. Se cruza cada renglón por su llave natural (`folio`, `concepto`) y se cuentan
los PARES cuyo orden relativo se invirtió entre dos tomas (`radiografia/orden.py`), en dos clases:

- **contrato:** pares con distinta `fecha_valor`. El `ORDER BY fecha_valor` los promete, así que deben dar
  **0 inversiones siempre**. Una sola es un defecto.
- **empatados:** pares con la misma `fecha_valor`. Su orden lo decide el plan; el piso se mide SÓLO aquí, como
  % de pares empatados invertidos.

El % de posiciones distintas se deja sólo como contraste: con un renglón que se mueva al principio, por posición
«cambia todo».

## Volumen necesario (`python -m legado.medir_volumen --volumenes 25,50,100,250,400 --corridas 5`)

Para cada volumen se recreó la base, se cargó y se corrieron 5 veces el reporte del legado (`sp_reporte_ordenes`:
mes, trimestre y año) y la lista de la pantalla (`sp_lista_operaciones`, `TOP` sin `ORDER BY`). Se probó con
`MAXDOP 4` (los núcleos del runner de GitHub) y sin límite (12 núcleos de la laptop). «Otro momento» es la misma
salida después de actualizar estadísticas y vaciar el caché de planes.

### Resultado (24-nov-2026)

| ops/día | operaciones | salida | MAXDOP | renglones | inversiones de contrato (máx) | % de pares empatados invertidos (máx / prom) | corridas distintas | % empatados invertidos en otro momento | % posiciones distintas (máx, sólo contraste) |
|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 25 | 25,647 | sp_reporte_ordenes (mes) | 4 | 437 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 25 | 25,647 | sp_reporte_ordenes (trimestre) | 4 | 1,447 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 25 | 25,647 | sp_reporte_ordenes (año) | 4 | 5,562 | 0 | 5.46 / 5.37 | 4 | 5.46 | 19.1 |
| 25 | 25,647 | sp_lista_operaciones (2023-06-02) | 4 | 46 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 25 | 25,647 | sp_reporte_ordenes (mes) | todos | 437 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 25 | 25,647 | sp_reporte_ordenes (trimestre) | todos | 1,447 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 25 | 25,647 | sp_reporte_ordenes (año) | todos | 5,562 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 25 | 25,647 | sp_lista_operaciones (2023-06-02) | todos | 46 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 50 | 51,314 | sp_reporte_ordenes (mes) | 4 | 913 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 50 | 51,314 | sp_reporte_ordenes (trimestre) | 4 | 2,903 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 50 | 51,314 | sp_reporte_ordenes (año) | 4 | 10,779 | 0 | 17.02 / 16.36 | 4 | 17.27 | 47.9 |
| 50 | 51,314 | sp_lista_operaciones (2023-11-24) | 4 | 87 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 50 | 51,314 | sp_reporte_ordenes (mes) | todos | 913 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 50 | 51,314 | sp_reporte_ordenes (trimestre) | todos | 2,903 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 50 | 51,314 | sp_reporte_ordenes (año) | todos | 10,779 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 50 | 51,314 | sp_lista_operaciones (2023-11-24) | todos | 87 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 100 | 102,789 | sp_reporte_ordenes (mes) | 4 | 1,785 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 100 | 102,789 | sp_reporte_ordenes (trimestre) | 4 | 5,683 | 0 | 2.47 / 2.47 | 4 | 2.47 | 7.4 |
| 100 | 102,789 | sp_reporte_ordenes (año) | 4 | 22,269 | 0 | 48.35 / 42.72 | 4 | 46.38 | 98.1 |
| 100 | 102,789 | sp_lista_operaciones (2023-12-12) | 4 | 172 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 100 | 102,789 | sp_reporte_ordenes (mes) | todos | 1,785 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 100 | 102,789 | sp_reporte_ordenes (trimestre) | todos | 5,683 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 100 | 102,789 | sp_reporte_ordenes (año) | todos | 22,269 | 0 | 3.23 / 3.23 | 4 | 49.57 | 8.5 |
| 100 | 102,789 | sp_lista_operaciones (2023-12-12) | todos | 172 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 250 | 256,609 | sp_reporte_ordenes (mes) | 4 | 4,405 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 250 | 256,609 | sp_reporte_ordenes (trimestre) | 4 | 14,284 | 0 | 35.07 / 32.55 | 4 | 29.33 | 83.9 |
| 250 | 256,609 | sp_reporte_ordenes (año) | 4 | 56,147 | 0 | 56.58 / 48.95 | 4 | 46.11 | 97.7 |
| 250 | 256,609 | sp_lista_operaciones (2023-11-17) | 4 | 200 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 250 | 256,609 | sp_reporte_ordenes (mes) | todos | 4,405 | 0 | 0.0 / 0.0 | 0 | 0.0 | 0.0 |
| 250 | 256,609 | sp_reporte_ordenes (trimestre) | todos | 14,284 | 0 | 19.58 / 12.78 | 4 | 11.01 | 50.3 |
| 250 | 256,609 | sp_reporte_ordenes (año) | todos | 56,147 | 0 | 18.67 / 18.02 | 4 | 18.1 | 49.6 |
| 250 | 256,609 | sp_lista_operaciones (2023-11-17) | todos | 200 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 400 | 412,125 | sp_reporte_ordenes (mes) | 4 | 7,492 | 0 | 27.98 / 26.37 | 4 | 27.8 | 85.9 |
| 400 | 412,125 | sp_reporte_ordenes (trimestre) | 4 | 23,381 | 0 | 49.54 / 46.58 | 4 | 45.68 | 98.6 |
| 400 | 412,125 | sp_reporte_ordenes (año) | 4 | 89,444 | 0 | 57.35 / 52.54 | 4 | 44.39 | 98.5 |
| 400 | 412,125 | sp_lista_operaciones (2023-09-11) | 4 | 200 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |
| 400 | 412,125 | sp_reporte_ordenes (mes) | todos | 7,492 | 0 | 21.68 / 15.26 | 4 | 7.21 | 57.4 |
| 400 | 412,125 | sp_reporte_ordenes (trimestre) | todos | 23,381 | 0 | 23.46 / 21.21 | 4 | 22.67 | 66.8 |
| 400 | 412,125 | sp_reporte_ordenes (año) | todos | 89,444 | 0 | 24.73 / 24.08 | 4 | 24.03 | 67.5 |
| 400 | 412,125 | sp_lista_operaciones (2023-09-11) | todos | 200 | 0 | 0.0 / 0.0 | 0 | — | 0.0 |

**Lectura:**

- **El contrato se cumple siempre:** 0 inversiones entre pares con distinta fecha valor en las 40 mediciones.
- **El reporte mensual** (el periodo más corto del negocio) no invierte ningún empate con 250 operaciones por día.
  Con 400 invierte entre 26 % y 28 % de los pares empatados con MAXDOP 4, y entre 15 % y 22 % sin límite. El
  trimestral ya los invierte con 100 por día y MAXDOP 4.
- **La lista con `TOP` sin `ORDER BY` no varía** entre corridas en la misma instancia. Su daño es otro: re-corrida
  en OTRA instancia (el respaldo restaurado) devuelve otras filas (ver abajo).
- Con poco volumen el resultado no es monótono (con 25 por día el anual varía con MAXDOP 4 y no sin límite):
  depende del plan. Por eso se mide y no se supone.

**Decisión:** 400 operaciones por día (`Config.operaciones_por_dia`), el menor volumen probado con el que hasta el
reporte mensual invierte empates. Cada corrida del CI lo vuelve a comprobar en el motor real, en un runner de 4
núcleos (`test_control_negativo_en_inversiones_contrato_en_cero_y_empates_libres`).

## Piso REAL de la paridad: lo que el legado publicó contra la re-corrida sobre el respaldo

El oráculo de los reportes no es una re-corrida posterior: es la salida que el legado PUBLICÓ al tomar el respaldo.
`python -m legado respaldar` la captura en ese instante, sin que el legado se mueva (pantalla y conteos se leen
antes y después), y la guarda junto al manifiesto con su sha256. La radiografía la re-corre sobre el respaldo
restaurado en un contenedor limpio y la compara (`radiografia/informe/radiografia.md`).

| Salida publicada | Renglones (comunes) | Mismo contenido | Inversiones de contrato | Pares empatados invertidos |
|---|---:|---|---:|---:|
| Reporte del mes (1–29 dic) | 7,492 (7,492) | sí | 0 de 26,515,033 | 17.9 %, 21.9 % y 24.9 % en tres corridas del ciclo |
| Lista del día anterior (`TOP 200` sin `ORDER BY`) | 200 (183) | **no**: otra instancia devuelve 17 filas distintas | — (sin contrato) | 2.2 % de los comunes |

**Piso para S2:** en el reporte, 0 inversiones de contrato y entre 18 % y 25 % de pares empatados invertidos
entre el propio legado y su respaldo. Varía entre corridas, así que la paridad del TO-BE se juzga contra el piso
medido en la misma corrida, nunca contra una constante. En la lista, ni el contenido es contrato: se compara como
conjunto contra el universo del día, no contra las 200 filas que tocó mostrar.

## Volumen resultante (generación por omisión, semilla 20231229)

| Tabla | Filas al respaldo |
|---|---:|
| `operacion` | 412,125 |
| `orden_pago` | 270,616 |
| `partida_solicitada` | 244,869 |
| `partida_liquidada` | 893,174 |
| `bitacora` | 685,276 |
| `moneda` | 11 |
| `folio` | 2 |

El delta del día del respaldo (legado vivo) son 869 llamadas a procedimientos, 14 de ellas después del
congelamiento. Los archivos de interfaz son 1,562 (781 días de buzón del corresponsal y 781 de archivo de
sucursales, ≈ 45 MB). El respaldo comprimido de `BFN_DIVISAS` pesa 92 MB y el de msdb, 2.7 MB.

## Tiempos del ciclo completo (`./ciclo.sh`)

Medido en un clon limpio (venv nuevo, contenedor del legado recién creado y la imagen ya descargada), laptop de
12 núcleos:

| Paso | Segundos |
|---|---:|
| levantar el legado | 5.8 |
| esquema | 1.0 |
| generar (44 s, con 1,562 archivos de interfaz) y cargar y verificar (82 s) | 139.1 |
| pantalla | 1.0 |
| respaldo fechado (BFN_DIVISAS + msdb + manifiesto + salidas publicadas) | 2.7 |
| legado vivo (delta del día, congelamiento y choques de S3) | 11.2 |
| delta por la pantalla | 1.7 |
| restaurar en contenedor limpio, radiografiar y cuadrar contra el manifiesto | 28.3 |
| veredictos medidos (otra restauración limpia) | 12.2 |
| medir contra el catálogo | 0.0 |
| daño de `bcp -c` | 2.0 |
| **Total** | **≈ 205** |

Generar, respaldar, restaurar y radiografiar toman **≈ 170 s**. Las pruebas de integración suman 54 s, el control
de entrenamiento (WideWorldImporters) 50–65 s y el apartado (AdventureWorks) 26 s.
