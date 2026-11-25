# Catálogo de la siembra a ciegas · rama `siembra-ciega`

Sembrado por otra sesión, sin que el autor de los detectores lo conociera, sobre el tag `detectores-v2` (21097fa).
Sólo cambia `legado/`. Las cifras salen de la generación por omisión (semilla `20231229`, 400 operaciones por día)
cargada en SQL Server 2022 CU28, el mismo contenedor que fija `legado/docker-compose.yml`.

## Tabla de medición

| Id | Trampa | Señales esperadas |
|---|---|---|
| T1 | Selección no determinista: variable asignada desde varias filas | `top_sin_order_by → dbo.sp_reporte_posicion` |
| T2 | Reloj del servidor que entra a la regla por una variable | `reloj_en_regla → dbo.sp_ordenes_por_vencer` |
| T3 | Espacios finales que SQL Server ignora al comparar y PostgreSQL no | `espacios_finales → dbo.partida_solicitada.referencia` |

`espacios_finales` no es una categoría de los detectores congelados. Se declara porque el patrón sí es genérico
(valores de texto con relleno al final, concentrados en una ventana de fechas); si nadie lo reporta, cuenta como no
detectada.

## Trampas

### T1 · Variable asignada desde varias filas
- **Dónde:** `dbo.sp_reporte_posicion`, el reporte regulatorio de posición por moneda. El tipo de cambio de cierre
  sale de `SELECT @tc_cierre = tipo_cambio FROM dbo.operacion WHERE moneda = @moneda AND <el día>`. El comentario
  dice «el de la última operación del día», pero la sentencia no tiene `TOP` ni `ORDER BY`: la variable se queda
  con la última fila que entregue el plan.
- **Clase:** la misma que T1 del catálogo original (orden no determinista), en otra forma sintáctica.
- **Medido** (el procedimiento corrido en todos los días del histórico, 9,341 pares día-moneda):
  - con el plan que elige hoy dentro del procedimiento (índice por fecha), coincide en 9,341 de 9,341 con la
    última operación por (fecha, id);
  - la MISMA sentencia en un lote suelto, con variables locales en vez del parámetro, elige el índice agrupado y
    devuelve la última por id. Con ese recorrido cambian 1,650 de 9,341 (18 %), por las operaciones del canal
    ARCHIVO, que se cargan a las 22:00 con horas de la mañana. Ejemplo: CAD el 28-dic-2023, 13.177961 por fecha
    contra 13.270531 por id;
  - en 28 pares la última hora del día (smalldatetime, al minuto) está empatada entre operaciones con distinto
    tipo de cambio: ahí la regla de negocio misma es ambigua.
- **Al modernizar:** hoy es latente y se vuelve real en cuanto cambie el plan. El TO-BE fija la regla
  (`ORDER BY fecha_operacion DESC, id DESC`) y negocio decide el desempate del último minuto.

### T2 · Reloj del servidor por una variable
- **Dónde:** `dbo.sp_ordenes_por_vencer`, la lista de la mesa de operaciones. `SET @hoy = GETDATE()` y
  `SET @limite = DATEADD(day, -2, @hoy)`; después, `WHERE fecha_envio < @limite` y un `CASE` con `@limite`. El
  reloj no aparece dentro del `WHERE`: entra por una variable, que es la forma más común en código real.
- **Clase:** la misma que T8 del catálogo original.
- **Medido** sobre la carga al respaldo (antes del delta): con el reloj de hoy devuelve 139 órdenes, todas
  «VENCE HOY» (son todas las ENVIADA). Con el reloj del respaldo (29-dic-2023 06:00) devuelve 6, una de ellas
  «VENCE HOY».
- **Al modernizar:** reloj inyectado; el replay usa la hora de cada corrida.

### T3 · Espacios finales en la referencia del corresponsal
- **Dónde:** `dbo.partida_solicitada.referencia`. Del 4-jul-2022 al 27-ene-2023, una versión de la interfaz SWIFT
  guardó el campo con su relleno de ancho fijo, hasta 35 caracteres. El buzón del corresponsal (universo) trae el
  mismo `:20:` SIN relleno.
- **Medido:**
  - 48,013 partidas (28,273 referencias) con relleno, todas dentro de la ventana;
  - SQL Server las trata como iguales a su versión recortada: `referencia = RTRIM(referencia)` es verdadero en las
    244,869 filas, y `LEN` no cuenta el relleno. Sólo `DATALENGTH` lo ve;
  - en PostgreSQL, `varchar` y `text` sí distinguen `'X   '` de `'X'`.
- **Al modernizar:** un ETL que copia tal cual lleva el relleno a PostgreSQL. Ahí falla cualquier cruce por igualdad
  con el buzón o con un valor recortado (28,273 referencias), y `DISTINCT` y `GROUP BY` cuentan distinto que el
  legado. Recortar es una decisión explícita y se documenta.
- **Hallazgo de la propia siembra:** el BCP de FreeTDS (`pymssql.bulk_copy`) recortaba los espacios finales en
  silencio, y la verificación del cargador no lo veía porque compara con `rstrip()` en los dos lados: la
  normalización absolvía justo el defecto. `legado/generador/cargar.py` ahora restaura el relleno después del BCP y
  lo comprueba con `DATALENGTH`.
