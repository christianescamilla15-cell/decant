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
  salvo `SystemClock`.

## Alternativas descartadas
- **MediatR:** dependencia externa (y de licencia cambiante) para lo que es un diccionario de manejadores.
- **`SaveChanges` fila por fila para las cargas:** minutos por corrida contra segundos del COPY.
- **Comandos de lotes dentro de la API:** mezcla un proceso de horas con un servicio HTTP y obliga a levantar Kestrel
  para cargar.

## Consecuencias
- El almacén escribe con SQL explícito (COPY y TRUNCATE) además de EF Core: las pruebas de infraestructura cubren las
  dos rutas contra PostgreSQL real.
