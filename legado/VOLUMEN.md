# Volumen del legado: medido, no adivinado

**Pregunta:** ¿cuántos datos necesita el legado para que el CONTROL NEGATIVO no salga en 0 %?

El control negativo compara el legado consigo mismo: la misma salida, sobre los mismos datos, tomada dos veces. Si
siempre sale idéntica, una comparación por posición parece perfecta y el arnés de paridad de S2 no tiene listón.
Con pocos datos, SQL Server entrega un orden estable aunque la consulta tenga empates.

**Cómo se midió:** `python -m legado.medir_volumen --volumenes 25,50,100,250,400 --corridas 5`. Para cada volumen
se recreó la base, se cargó y se corrieron 5 veces:

- el reporte del legado (`sp_reporte_ordenes`, `ORDER BY fecha_valor`, con cientos de empates por día) para un
  mes, un trimestre y un año;
- la lista de la pantalla (`sp_lista_operaciones`, `TOP` sin `ORDER BY`) del día con más operaciones.

Se probó con `MAXDOP 4` (los núcleos del runner de GitHub) y sin límite (12 núcleos de la laptop). «En otro
momento» es la misma salida después de actualizar estadísticas y vaciar el caché de planes.

## Resultado (24-nov-2026)

| ops/día | operaciones | salida | MAXDOP | renglones | % posiciones que cambian (máx / prom) | corridas distintas | % en otro momento | s/corrida |
|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 25 | 25,649 | sp_reporte_ordenes (mes) | 4 | 423 | 0.0 / 0.0 | 0 | 0.0 | 0.02 |
| 25 | 25,649 | sp_reporte_ordenes (trimestre) | 4 | 1,350 | 0.0 / 0.0 | 0 | 0.0 | 0.03 |
| 25 | 25,649 | sp_reporte_ordenes (año) | 4 | 5,328 | 17.6 / 17.2 | 4 | 15.7 | 0.12 |
| 25 | 25,649 | sp_lista_operaciones (2023-06-02) | 4 | 46 | 0.0 / 0.0 | 0 | — | — |
| 25 | 25,649 | sp_reporte_ordenes (mes) | todos | 423 | 0.0 / 0.0 | 0 | 0.0 | 0.01 |
| 25 | 25,649 | sp_reporte_ordenes (trimestre) | todos | 1,350 | 0.0 / 0.0 | 0 | 0.0 | 0.03 |
| 25 | 25,649 | sp_reporte_ordenes (año) | todos | 5,328 | 0.0 / 0.0 | 0 | 0.0 | 0.11 |
| 25 | 25,649 | sp_lista_operaciones (2023-06-02) | todos | 46 | 0.0 / 0.0 | 0 | — | — |
| 50 | 51,317 | sp_reporte_ordenes (mes) | 4 | 897 | 0.0 / 0.0 | 0 | 0.0 | 0.04 |
| 50 | 51,317 | sp_reporte_ordenes (trimestre) | 4 | 2,810 | 0.0 / 0.0 | 0 | 0.0 | 0.06 |
| 50 | 51,317 | sp_reporte_ordenes (año) | 4 | 10,861 | 46.6 / 45.1 | 4 | 45.9 | 0.23 |
| 50 | 51,317 | sp_lista_operaciones (2023-11-24) | 4 | 87 | 0.0 / 0.0 | 0 | — | — |
| 50 | 51,317 | sp_reporte_ordenes (mes) | todos | 897 | 0.0 / 0.0 | 0 | 0.0 | 0.02 |
| 50 | 51,317 | sp_reporte_ordenes (trimestre) | todos | 2,810 | 0.0 / 0.0 | 0 | 0.0 | 0.06 |
| 50 | 51,317 | sp_reporte_ordenes (año) | todos | 10,861 | 28.4 / 27.8 | 4 | 26.1 | 0.22 |
| 50 | 51,317 | sp_lista_operaciones (2023-11-24) | todos | 87 | 0.0 / 0.0 | 0 | — | — |
| 100 | 102,792 | sp_reporte_ordenes (mes) | 4 | 1,690 | 0.0 / 0.0 | 0 | 0.0 | 0.07 |
| 100 | 102,792 | sp_reporte_ordenes (trimestre) | 4 | 5,596 | 10.5 / 10.5 | 4 | 10.5 | 0.11 |
| 100 | 102,792 | sp_reporte_ordenes (año) | 4 | 22,236 | 98.7 / 86.9 | 4 | 98.5 | 0.44 |
| 100 | 102,792 | sp_lista_operaciones (2023-12-12) | 4 | 172 | 0.0 / 0.0 | 0 | — | — |
| 100 | 102,792 | sp_reporte_ordenes (mes) | todos | 1,690 | 0.0 / 0.0 | 0 | 0.0 | 0.05 |
| 100 | 102,792 | sp_reporte_ordenes (trimestre) | todos | 5,596 | 0.0 / 0.0 | 0 | 0.0 | 0.11 |
| 100 | 102,792 | sp_reporte_ordenes (año) | todos | 22,236 | 34.6 / 33.4 | 4 | 98.8 | 0.43 |
| 100 | 102,792 | sp_lista_operaciones (2023-12-12) | todos | 172 | 0.0 / 0.0 | 0 | — | — |
| 250 | 256,613 | sp_reporte_ordenes (mes) | 4 | 4,392 | 0.0 / 0.0 | 0 | 0.0 | 0.13 |
| 250 | 256,613 | sp_reporte_ordenes (trimestre) | 4 | 14,274 | 85.9 / 83.9 | 4 | 79.9 | 0.27 |
| 250 | 256,613 | sp_reporte_ordenes (año) | 4 | 55,578 | 97.7 / 95.4 | 4 | 97.3 | 1.03 |
| 250 | 256,613 | sp_lista_operaciones (2023-11-17) | 4 | 200 | 0.0 / 0.0 | 0 | — | — |
| 250 | 256,613 | sp_reporte_ordenes (mes) | todos | 4,392 | 0.0 / 0.0 | 0 | 0.0 | 0.1 |
| 250 | 256,613 | sp_reporte_ordenes (trimestre) | todos | 14,274 | 44.0 / 39.3 | 4 | 22.3 | 0.27 |
| 250 | 256,613 | sp_reporte_ordenes (año) | todos | 55,578 | 48.3 / 47.6 | 4 | 48.4 | 1.12 |
| 250 | 256,613 | sp_lista_operaciones (2023-11-17) | todos | 200 | 0.0 / 0.0 | 0 | — | — |
| 400 | 412,130 | sp_reporte_ordenes (mes) | 4 | 7,148 | 75.8 / 66.2 | 4 | 82.5 | 0.2 |
| 400 | 412,130 | sp_reporte_ordenes (trimestre) | 4 | 22,733 | 98.4 / 97.2 | 4 | 98.0 | 0.47 |
| 400 | 412,130 | sp_reporte_ordenes (año) | 4 | 88,768 | 98.2 / 97.1 | 4 | 97.7 | 1.7 |
| 400 | 412,130 | sp_lista_operaciones (2023-09-11) | 4 | 200 | 0.0 / 0.0 | 0 | — | — |
| 400 | 412,130 | sp_reporte_ordenes (mes) | todos | 7,148 | 44.4 / 43.7 | 4 | 57.2 | 0.16 |
| 400 | 412,130 | sp_reporte_ordenes (trimestre) | todos | 22,733 | 62.4 / 60.7 | 4 | 63.7 | 0.4 |
| 400 | 412,130 | sp_reporte_ordenes (año) | todos | 88,768 | 68.9 / 67.3 | 4 | 66.4 | 1.56 |
| 400 | 412,130 | sp_lista_operaciones (2023-09-11) | todos | 200 | 0.0 / 0.0 | 0 | — | — |

**Lectura:**

- **El reporte mensual** (el periodo más corto del negocio) es estable con 250 operaciones por día. Con 400 cambia
  en 44 % a 76 % de las posiciones entre corridas. El trimestral ya es inestable con 100 por día y MAXDOP 4.
- **La lista con `TOP` sin `ORDER BY` sale idéntica a cualquier volumen.** Su trampa (T1) es de significado:
  «las primeras 200 del día» en orden de índice, no «las últimas». No es inestabilidad de corrida a corrida.
- Con poco volumen el resultado no es monótono: con 25 por día el reporte anual varía con MAXDOP 4 y no sin límite.
  La paralelización depende del plan. Por eso se mide y no se supone.

**Decisión:** 400 operaciones por día (`Config.operaciones_por_dia`), el menor volumen probado con el que hasta el
reporte mensual es inestable. Cada corrida del CI lo vuelve a comprobar en el motor real, en un runner de 4 núcleos
(`test_control_negativo_el_reporte_mensual_del_legado_no_se_repite_a_si_mismo`). Si un día sale en 0 %, la prueba
falla y pide más volumen.

> La medición se hizo con el generador de ese día. Los arreglos posteriores (re-registro sólo en días hábiles, BIC
> intermediarios variados) no cambian la forma de los datos que decide el plan; la prueba de integración es la que
> manda.

## Volumen resultante (generación por omisión, semilla 20231229)

| Tabla | Filas |
|---|---:|
| `operacion` | 412,130 |
| `orden_pago` | 270,621 |
| `partida_solicitada` | 244,862 |
| `partida_liquidada` | 893,190 |
| `bitacora` | 685,273 |
| `moneda` | 11 |
| `folio` | 2 |

El delta del día del respaldo (legado vivo) son 863 llamadas a procedimientos, 14 de ellas después del
congelamiento. El respaldo comprimido de `BFN_DIVISAS` pesa 92 MB y el de msdb, 2.7 MB.

## Tiempos del ciclo completo (`./ciclo.sh`, laptop de 12 núcleos)

| Paso | Segundos |
|---|---:|
| levantar el legado (contenedor ya descargado) | 0.5 |
| esquema | 0.6 |
| generar (17 s) y cargar y verificar (65 s) | 82.3 |
| pantalla | 1.0 |
| respaldo fechado (BFN_DIVISAS + msdb + manifiesto) | 1.6 |
| legado vivo (delta del día + congelamiento) | 6.8 |
| restaurar en contenedor limpio y radiografiar | 23.9 |
| medir contra el catálogo | 0.0 |
| daño de `bcp -c` | 1.8 |
| **Total** | **≈ 119** |

Lo que pidió el plan (generar, respaldar, restaurar, radiografiar) toma **≈ 108 s**. El control público sobre
WideWorldImporters suma 48 s.
