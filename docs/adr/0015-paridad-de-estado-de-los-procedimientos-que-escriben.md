# ADR 0015 · Paridad de ESTADO para los procedimientos que escriben

- Estado: propuesta (borrador de S3) · Fecha: 2026-11-25

## Contexto
Comparar la salida de un procedimiento que escribe no dice qué dejó en la base. Dos trampas lo muestran:
- `UPDATE … FROM` con un JOIN 1:N escribe el estado de una fila cualquiera: 100,299 operaciones quedan mal;
- `@@IDENTITY` después de un trigger que inserta devuelve el id de otra tabla.

## Decisión
- Cada procedimiento que escribe (6 hoy) corre sobre el respaldo restaurado dentro de una transacción que se
  REVIERTE, incluidos los que el ciclo nunca ejecuta («sin ejecución observada», ADR 0014). Antes de revertir se
  vuelcan las tablas que tocó.
- El mismo caso de uso corre en el TO-BE y se comparan las tablas afectadas, fila por fila por llave natural.
- Dos verificaciones fijas:
  - toda escritura con JOIN se prueba con datos 1:N;
  - todo id devuelto se cruza con la fila efectivamente insertada.
- Lo que el reloj decide se corre con el instante del corte. Como `GETDATE()` no se inyecta en el legado, la
  medición usa una copia temporal del procedimiento en un esquema aparte, nunca el original.
- Cada diferencia se arbitra como en S2: defecto nuestro, regla real del legado o defecto del legado a decidir.
- Los escritores salen del inventario (procedimientos, triggers y pasos de jobs): N de N, no una lista fija.
- El arnés falla si `@@TRANCOUNT` cambia durante la llamada. Un ROLLBACK propio se llevaría la transacción externa y
  el volcado saldría vacío sin avisar.
- La transacción revertida no deshace efectos fuera de la base (correo, arranque de jobs, servidores enlazados,
  archivos). Se declaran por objeto y se neutralizan o emulan durante la corrida.

## Al construirla (26-nov, paso 5)
Lo que el código decidió y la propuesta no decía (`corte/estado.py`, `corte/estado_ci.py`, `corte/estado_tobe.sql`):
- **La copia temporal lleva también las TABLAS.** Un disparador sólo puede vivir en el esquema de su tabla: para
  inyectar el reloj del disparador sin tocar el original, la copia en `estado` trae las 7 tablas con el DDL del código
  (índices y llaves incluidos) y los datos del respaldo con sus ids, el disparador y los escritores. Antes de correr
  nada se exige: el mismo catálogo que el original, 0 diferencias de datos, la identidad en el mismo valor, el código
  del respaldo igual al del repositorio, la copia guardada igual a la transformación y ninguna dependencia de `dbo`
  (lo dice el servidor). Al terminar, la copia se borra y lo original tiene la misma huella.
- **El reloj se inyecta por `SESSION_CONTEXT`.** La transformación cambia `GETDATE()` por esa lectura, por fichas (no
  dentro de cadenas ni comentarios). Sin el valor, las columnas NOT NULL del reloj rechazan la escritura: la copia no
  puede correr con un reloj inventado. Un reloj que no se inyecta con un solo valor (UTC, con zona), un servidor
  enlazado, un nombre de tres partes o SQL dinámico en un escritor detienen la copia.
- **Escenarios con las llamadas reales.** A: el día del corte (las 855 llamadas del guion anteriores al congelamiento,
  cada una con su instante) y su noche (el comando del paso del job, leído de msdb, a las 23:30). B: la mesa, sobre el
  respaldo. C: la contingencia, con la primera orden nueva del día y su operación. Cada escenario en UNA transacción
  revertida; las identidades se regresan a mano al salir (no son transaccionales) para que cada escenario numere desde
  el respaldo.
- **N de N lo dice el servidor**, no el arnés: `sys.dm_exec_procedure_stats` y `sys.dm_exec_trigger_stats` de la copia.
  El paso del job cuenta cuando su comando corrió y el servidor vio al procedimiento que llama.
- **El TO-BE es el efecto escrito en SQL sobre la base de referencia** (`estado_tobe.sql`): la base cerrada del paso 4
  es el estado del respaldo en PostgreSQL. Son las reglas del dominio .NET (una prueba ata las constantes) con los
  parches que el TO-BE ya decidió: el reloj entra, la mesa refleja la orden VIGENTE y la contingencia devuelve
  `RETURNING id`. El dominio .NET no tiene todavía la mesa ni la contingencia, y vive en otro esquema; cuando las
  tenga, su efecto se compara con éste.
- **Comparación por etapa y por llave de negocio**: el efecto de cada etapa en las 7 tablas, no sólo en las que el
  inventario declara (una tabla que cambia sin declararse se vería). En SQL Server, la diferencia de conjuntos copia −
  original, también en bytes (la intercalación ignora espacios finales y mayúsculas); en PostgreSQL, contra una foto
  md5 por fila.
- **Árbitros auditados**, como en S2: el 1:N se acepta como explicación sólo si la operación tiene varias órdenes, el
  TO-BE escribió el reflejo de la vigente y el legado el de OTRA de sus órdenes; `@@IDENTITY`, sólo si el id devuelto
  es una fila que la misma llamada insertó en otra tabla. Lo que ningún árbitro explica es defecto nuestro.
- **Los controles de las trampas aplican el parche del TO-BE a la copia del legado** (texto exacto, una sola vez): con
  él, el legado tiene que coincidir con el TO-BE en 0 diferencias.

**Medido en el PR** (corrida 45898183988, base construida porque no había volcado vigente):
- 8 de 8 escritores corridos, según el servidor: registrar operación 422 veces, orden 270, liquidación 162, el paso
  del job y `sp_conciliar` 1, la mesa 1, la contingencia 1, el disparador 574.
- Efecto igual por llave en A (421 operaciones; 270 órdenes y 139 re-registros que pasan a REEMPLAZADA; 893 partidas
  del cliente; 162 liquidaciones con 271 partidas del corresponsal; 164 órdenes de la noche; 736 renglones de
  bitácora) y en C (la orden y su bitácora).
- r3-T1: 100,259 diferencias en `operacion.estatus`, todas auditadas como el JOIN 1:N; con el parche, 0. El catálogo
  midió 100,299 con otro plan: «una orden cualquiera» depende del plan, y esa cifra con él (`variacion_de_plan_r3_t1`
  la cuenta en SQL en cada corrida).
- r3-T3: devolvió 685,277 (la bitácora) y la orden quedó con 270,617, que es lo que devuelve el TO-BE; con el parche,
  270,617 en los dos.
- Controles: un procedimiento con su propio ROLLBACK dispara la guarda (error 266, `@@TRANCOUNT` 1 → 0) y su volcado
  sale con 0 cambios; sin el escenario C, el N de N falla nombrando a `dbo.sp_alta_manual_orden`.

**Pendiente de decisión de negocio** (no se decide aquí, ADR 0006):
- r3-T1: ¿la mesa refleja la orden vigente (lo que hace el TO-BE) o se replica el «una cualquiera»?
- La contingencia tiene, además de r3-T3, reglas propias que el TO-BE replica tal cual: toma folio nuevo aunque el
  documento ya exista, no da de alta las partidas del cliente y no marca REEMPLAZADA al registro anterior.

## Alternativas descartadas
- **Confiar en las pruebas unitarias del TO-BE:** prueban la regla que escribimos, no la que el legado ejecuta.
- **Correrlo en una copia y no revertir:** deja estado que contamina la siguiente medición.
- **Copiar sólo los procedimientos y dejar las tablas en `dbo`:** el disparador original (con su `GETDATE()`) seguiría
  firmando la bitácora con el reloj del servidor, y desactivarlo sería tocar el original.
- **Correr el original y emparejar los relojes después:** `GETDATE()` decide filas (vencimiento), no sólo sellos.

## Consecuencias
Se reusa la ejecución revertida que ya tiene la radiografía. Los defectos del legado salen como diferencias con
nombre y no como «fallas de paridad».
