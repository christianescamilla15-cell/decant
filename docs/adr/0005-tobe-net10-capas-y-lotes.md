# ADR 0005 · El TO-BE es .NET 10 en cuatro capas, con un host de lotes junto a la API

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
El TO-BE tiene que reimplementar las reglas del legado (procedimientos, trigger y job) y probarse por capas: reglas
puras sin I/O, casos de uso con dobles, todo lo que el ORM traduce a SQL contra PostgreSQL real y la API completa. La
carga histórica y el replay mueven 2 millones de filas; la API sirve el detalle y el reporte.

## Decisión
- `Decant.Domain` sólo con la BCL: agregados (`OrdenDePago` como DOCUMENTO por UETR), reglas puras, `Resultado<T>` e
  `IClock`. Las reglas citan la línea del legado de donde salen (`docs/reglas.md`).
- `Decant.Application`: casos de uso con un mediador propio de 50 líneas, puertos (`IUniverso`, `IOraculoHistorico`,
  `IAlmacenTobe`, `IConsultasTobe`) y opciones como records inmutables.
- `Decant.Infrastructure`: EF Core + Npgsql para el ESQUEMA (migraciones) y las CONSULTAS; COPY binario de Npgsql para
  las cargas en bloque, en una transacción.
- Dos hosts con la misma composición: `Decant.Api` (Minimal API) y `Decant.Cli` (`decant migrar | reproducir |
  reporte-ordenes | configuracion`). La configuración por ambiente vive una sola vez, en la API.
- Pruebas de arquitectura (NetArchTest + Mono.Cecil) hacen cumplir las capas y que nadie lea el reloj del sistema
  salvo `SystemClock`. Desde la retro (2026-11-25) también: ningún tipo de EF, Npgsql ni fila de la persistencia sale
  de la infraestructura (el CLI compone con `Servicios.ConexionDeLote` y `AplicarMigracionesAsync`), nadie expone
  `IQueryable`, toda lectura de un DbSet es `AsNoTracking`, ni defaults de reloj en la base ni conversiones de zona
  fuera de `Zonas`, y la fecha valor es `DateOnly` guardada como `date`.
- **Lotes, archivo por archivo (retro 2026-11-25):** el buzón se lee por archivo; uno que no se puede leer (permisos,
  UTF-8 inválido) deja su resultado («no se pudo leer») y los demás se procesan. Cada corrida guarda en
  `resultado_archivo` los mensajes, leídos, rechazados (con su motivo) y repetidos de cada archivo; una confirmación
  repetida en el lote cuenta UNA vez. Un rechazo de validación o de negocio se cuenta y no se reintenta; un error
  técnico es una excepción y la transacción no deja nada a medias, así que reanudar es volver a correr (el estado
  se reemplaza completo e idempotente: dos cargas a la vez dejan una sola copia). El resultado no depende del orden
  del lote: operaciones y registros se ordenan por su id (la llegada del legado), no por cómo vienen. No aplica
  partir el lote por una pausa larga: el replay corre en segundos sobre el universo completo (8.7–11.5 min es el job
  de paridad ENTERO, con el ciclo del legado).

## Alternativas descartadas
- **MediatR:** dependencia externa (y de licencia cambiante) para lo que es un diccionario de manejadores.
- **`SaveChanges` fila por fila para las cargas:** minutos por corrida contra segundos del COPY.
- **Comandos de lotes dentro de la API:** mezcla un proceso de horas con un servicio HTTP y obliga a levantar Kestrel
  para cargar.

## Consecuencias
- El almacén escribe con SQL explícito (COPY y TRUNCATE) además de EF Core: las pruebas de infraestructura cubren las
  dos rutas contra PostgreSQL real.
