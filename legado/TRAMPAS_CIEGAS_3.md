# Catálogo de la siembra a ciegas, ronda 3 · rama `siembra-ciega-3`

Sembrado por otra sesión, sin que el autor de los detectores lo conociera, sobre el tag `detectores-v4` (e1bb21b).
Sólo cambia `legado/sql/05_procedimientos.sql` (tres procedimientos nuevos; nada de Python ni de datos). Por pedido
del autor, dos trampas pegan en límites que la v4 ya documentó (`UPDATE … FROM` con JOIN 1:N; SQL dinámico sin
analizar) y una es de una clase nueva. Las cifras salen de la generación por omisión (semilla `20231229`) cargada en
SQL Server 2022 CU28, el contenedor que fija `legado/docker-compose.yml`; lo que escribe se midió dentro de una
transacción revertida.

## Tabla de medición

| Id | Trampa | Señales esperadas |
|---|---|---|
| T1 | `UPDATE … FROM` con un JOIN 1:N: cada operación toma el estado de una orden cualquiera | `top_sin_order_by → dbo.sp_reflejar_estatus_operacion` |
| T2 | Reloj del servidor dentro de SQL dinámico | `reloj_en_regla → dbo.sp_antiguedad_ordenes` |
| T3 | `@@IDENTITY` después de insertar en una tabla con trigger que inserta en otra con identidad | `identidad_con_trigger → dbo.sp_alta_manual_orden` |

`identidad_con_trigger` no es una categoría de los detectores congelados: es la clase nueva. Si nadie la reporta,
cuenta como no detectada.

## Trampas

### T1 · UPDATE … FROM con JOIN 1:N (límite documentado)
- **Dónde:** `dbo.sp_reflejar_estatus_operacion`, proceso de la mesa que refleja en `operacion.estatus` el estado de
  su orden: `UPDATE o SET estatus = CASE p.estatus … END FROM dbo.orden_pago p INNER JOIN dbo.operacion o
  ON o.id = p.operacion_id`. Una operación tiene varias filas en `orden_pago` (cada re-registro deja una
  `REEMPLAZADA`); con varias coincidencias SQL Server aplica UNA cualquiera y no avisa.
- **Clase:** selección no determinista, en un `UPDATE` (la escritura la vuelve dato).
- **Medido** (ejecutado y revertido): de 150,719 operaciones con orden, 104,773 tienen varias filas. En 100,299 de
  ellas (96 %) el estado que queda NO es el de la orden vigente: casi todas quedan `EN_PROCESO`, el mapeo de una
  fila `REEMPLAZADA`. NO es latente: con el plan de hoy ya escribe mal.
- **Al modernizar:** el TO-BE une sólo con la orden vigente y la paridad de `operacion.estatus` muestra 100,299
  diferencias que son del legado, no nuestras.

### T2 · Reloj del servidor dentro de SQL dinámico (límite documentado)
- **Dónde:** `dbo.sp_antiguedad_ordenes`, reporte de antigüedad con filtro opcional por corresponsal. El SQL se arma
  como texto: `… AND fecha_envio < DATEADD(day, -' + CAST(@dias AS nvarchar(10)) + N', GETDATE())` y se corre con
  `sp_executesql`. El reloj vive dentro de una cadena.
- **Clase:** la de T8 del catálogo original y T2 de la ronda 1 (reloj en la regla), en SQL dinámico.
- **Medido** sobre la carga al respaldo (antes del delta), con `@dias = 3`: con el reloj de hoy devuelve 139 órdenes
  (todas las ENVIADA); con el reloj del respaldo (29-dic-2023 06:00) devuelve 1.
- **Al modernizar:** reloj inyectado; el replay usa la hora de cada corrida.

### T3 · @@IDENTITY con un trigger que inserta (clase nueva)
- **Dónde:** `dbo.sp_alta_manual_orden`, alta manual de contingencia. Inserta en `dbo.orden_pago` y hace
  `SET @id = @@IDENTITY`. `@@IDENTITY` devuelve la última identidad generada en la SESIÓN, en cualquier tabla y
  alcance: el trigger `tr_orden_pago_bitacora` acaba de insertar en `dbo.bitacora` (identidad propia), así que
  `@id` es el id de la bitácora, no el de la orden. Lo correcto es `SCOPE_IDENTITY()` (lo que usan los otros
  procedimientos) o `OUTPUT inserted.id`.
- **Medido** (ejecutado y revertido): la orden quedó con id 270,617 y el procedimiento devolvió 685,277, el id de la
  bitácora. Ninguna orden tiene ese id: la pantalla de contingencia abriría un detalle vacío, y cualquier inserción
  hija con ese id violaría la llave foránea (o, con ids que se crucen, colgaría partidas de OTRA orden).
- **Patrón genérico:** `@@IDENTITY` tras un `INSERT` a una tabla que tiene un trigger `AFTER INSERT` que inserta en
  una tabla con columna de identidad. Se decide con el esquema restaurado (triggers, sus tablas destino e
  identidades).
