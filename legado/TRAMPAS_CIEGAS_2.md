# Catálogo de la siembra a ciegas, ronda 2 · rama `siembra-ciega-2`

Sembrado por otra sesión, sin que el autor de los detectores lo conociera, sobre el tag `detectores-v3` (887514d).
Sólo cambia `legado/sql/` (una vista y tres procedimientos nuevos; nada de Python ni de datos). Por pedido del
autor, dos trampas pegan en límites que la v3 ya documentó (vistas; el JOIN … ON) y una es de una clase nueva. Las
cifras salen de la generación por omisión (semilla `20231229`) cargada en SQL Server 2022 CU28, el contenedor que fija
`legado/docker-compose.yml`.

## Tabla de medición

| Id | Trampa | Señales esperadas |
|---|---|---|
| T1 | Vista con `TOP 100 PERCENT … ORDER BY`: el orden que promete no existe | `top_sin_order_by → dbo.vw_liquidaciones_recientes` |
| T2 | Asignación que parece única por la PK pero el JOIN la multiplica | `top_sin_order_by → dbo.sp_constancia_operacion` |
| T3 | División entera y `AVG` de enteros (SQL Server trunca; PostgreSQL no en `avg`) | `division_entera → dbo.sp_tablero_corresponsales` |

`division_entera` no es una categoría de los detectores congelados: es la clase nueva. Si nadie la reporta, cuenta
como no detectada.

## Trampas

### T1 · El ORDER BY de una vista no ordena nada (límite: vistas)
- **Dónde:** `dbo.vw_liquidaciones_recientes` hace `SELECT TOP 100 PERCENT … ORDER BY s.fecha_hora DESC`, y
  `dbo.sp_liquidaciones_recientes` (consulta de tesorería) la lee sin `ORDER BY`, confiando en el orden de la vista.
  Desde SQL Server 2005 el optimizador descarta ese `TOP 100 PERCENT` y su `ORDER BY`: la vista no garantiza orden.
- **Clase:** orden no determinista (la de T1 del catálogo original), escondido en una vista y con un `ORDER BY`
  presente, que es justo lo que hace creer que está ordenado.
- **Medido** (`EXEC dbo.sp_liquidaciones_recientes`):
  - desde el 1-dic-2023: 4,442 filas; en 2,588 de los 4,441 pares contiguos la segunda es MÁS reciente que la
    primera (al revés de lo prometido). La primera fila que entrega es del 28-dic a las 08:19; la más reciente es
    del 28-dic a las 17:58;
  - desde 2021: 144,183 filas; 96,959 de 144,182 pares contiguos al revés. La primera fila que entrega es del
    12-ene-2021, no la más reciente.
- **Al modernizar:** la pantalla nueva que «respeta el orden del legado» copia un orden que no es contrato. La
  paridad lo debe tratar como pares libres; el TO-BE pone el `ORDER BY` en la consulta final.

### T2 · Asignación por PK que el JOIN multiplica (límite: JOIN … ON)
- **Dónde:** `dbo.sp_constancia_operacion`, la constancia para el cliente.
  `SELECT @folio = o.folio, … @estatus_orden = p.estatus, @fecha_envio = p.fecha_envio FROM dbo.operacion o
  LEFT JOIN dbo.orden_pago p ON p.operacion_id = o.id WHERE o.id = @operacion_id`. El filtro cubre la PK de
  `operacion`, pero `orden_pago` es 1:N con la operación (cada re-registro deja una fila `REEMPLAZADA`): la
  sentencia recorre varias filas y las variables se quedan con la última que entregue el plan.
- **Clase:** la de T1 de la ronda 1 (variable asignada desde varias filas), con la multiplicidad en el JOIN.
- **Medido:** 104,773 operaciones tienen varias filas de orden. Corrida la constancia para cada una, las 104,773
  muestran la orden vigente (0 con `REEMPLAZADA`; 0 con otra `fecha_envio`). Es **latente**: acierta porque el
  plan recorre `orden_pago` por `(operacion_id, id)` y la fila vigente siempre es la de id mayor. Ninguna regla lo
  asegura; un plan distinto o una fila vigente que no sea la última la rompe.
- **Al modernizar:** el TO-BE elige la orden vigente explícitamente (`estatus <> 'REEMPLAZADA'`, o la de
  `fecha_registro` mayor) y lo prueba con el caso de varias filas.

### T3 · División entera y AVG de enteros (clase nueva)
- **Dónde:** `dbo.sp_tablero_corresponsales`, el tablero por corresponsal.
  - `SUM(CASE … THEN 1 ELSE 0 END) * 100 / COUNT(*)`: entero entre entero, el porcentaje se trunca;
  - `AVG(DATEDIFF(minute, o.fecha_operacion, p.fecha_envio)) / 60`: en SQL Server `AVG` de un entero devuelve
    entero (trunca) y luego `/ 60` vuelve a truncar a horas enteras. En PostgreSQL `avg(integer)` devuelve
    `numeric`, así que el mismo SQL da horas con decimales.
- **Medido** (noviembre de 2023, 8 corresponsales): horas del legado 0, 1 o 2 contra exactas de 0.77 a 2.26 (dos
  corresponsales con 0.77 y 0.89 h salen en 0); porcentajes truncados hasta 0.94 puntos (94 contra 94.94).
- **Al modernizar:** en la paridad cada renglón del tablero difiere en horas aunque el TO-BE «copie el SQL». Es
  un defecto del legado a decidir con negocio (¿se replica el truncado?) y una diferencia de motor a documentar:
  el entero entre entero trunca en los dos motores, el `AVG` de enteros no.
