# ADR 0017 · GraphQL de sólo lectura junto a REST

- Estado: aceptada · Fecha: 2026-11-25
- Numeración: 0013–0016 son del plan de S3, en revisión en otra rama.

## Contexto
REST publica tres lecturas fijas: el detalle de una operación, la lista del día y el reporte de lo abonado. Un
consumidor que necesita la página del día con la orden y las partidas de cada operación hace una llamada al detalle
por operación. Medido contra PostgreSQL: 10 detalles son **40 consultas SQL** (4 por detalle).

GraphQL resuelve eso en una petición, pero trae riesgos propios:

- el N+1 se muda al servidor (cada campo se resuelve por separado);
- consultas abusivas: profundidad por los ciclos del grafo, alias que multiplican una página, documentos enormes;
- la introspección como mapa para quien ataca;
- un contrato de errores distinto al `problem+json` de REST;
- los tipos de la biblioteca pueden colarse a la aplicación.

## Decisión
1. **GraphQL de SÓLO LECTURA en `POST /graphql`, junto a REST, no en su lugar.** Usa el mismo mediador, las mismas
   reglas (T1, T2, T4 y las zonas de cada hora) y los mismos datos. No hay mutaciones ni suscripciones: escribir
   sigue siendo de los lotes (ADR 0005 y 0010).
2. **HotChocolate 16.7.7 (MIT)**, con versión EXACTA `[16.7.7]` en `Directory.Packages.props` y candado NuGet en
   modo bloqueado.
   - Avisos revisados el 25-nov-2026 en la base de avisos de GitHub y en los del repositorio de ChilliCream: hay 35
     publicados (34 tocan alguna 16.x) y **ninguno afecta a 16.7.7**.
   - El último alto (GHSA-jv3q-j8xr-p7q8, el costo con tipos de entrada recursivos) se corrige en 16.7.5. Antes,
     16.7.3 y 16.7.4 corrigieron 30 avisos, 5 de ellos críticos.
   - 16.7.7 además corrige el costo por omisión de los campos agregados por interceptores, que toca el límite de
     costo.
   - Tiene 4 días publicada y el `cooldown` de Dependabot es de 7. Esa regla gobierna las propuestas automáticas;
     ésta es una elección manual, con las notas de la versión leídas.
   - Los paquetes transitivos que no son de ChilliCream (`Yarp.ReverseProxy` 2.3.0 y `System.IO.Hashing` 8.0.0)
     tampoco tienen avisos que los afecten.
3. **Tipos propios en `Decant.Api.GraphQL`**: `Operacion`, `Orden`, `Partida` y `RenglonDeReporte`. La forma del
   esquema se decide en la API, con los mismos nombres de campo que el JSON de REST. La orden y su operación se
   navegan en los dos sentidos.
4. **Paginación por cursor** (conexiones de Relay) con llave de conjunto:
   - el cursor es opaco y lleva la POSICIÓN del último elemento más los argumentos de la consulta que lo dio;
   - un cursor de otro día, de otro rango o de otra lista se rechaza;
   - sólo hacia adelante, con páginas de 1 a 100 (20 por omisión) y sin `totalCount`.
5. **Filtros explícitos**: los argumentos de REST (un id, un día, un rango de fechas valor). No se usan
   `UseFiltering`, `UseSorting` ni `UseProjection`: ningún filtro arbitrario llega a la base y ningún `IQueryable`
   sale de la infraestructura (regla de ADR 0005).
6. **N+1**: cuatro cargadores por lote (DataLoader) sobre un puerto nuevo, `IConsultasEnLote`.
   - Cada llamada abre su contexto desde una fábrica: los cargadores consultan en paralelo y un `DbContext` no lo
     admite.
   - El documento de cada operación se elige con la MISMA regla que el detalle (`Proyecciones.DelMasReciente`).
   - Un lote se despacha cuando deja de recibir llaves, nunca por antigüedad. Con las opciones por omisión
     (despacho forzado a los 50 ms), una corrida bajo carga partió un lote en dos.
7. **Límites contra consultas abusivas**, todos rechazados ANTES de ejecutar:
   - profundidad 8, la de la consulta legítima más honda;
   - costo de 10,000 en campos y 10,000 en tipos: la página legítima más cara cuesta 4,112 y 1,203, así que caben
     dos en una petición y tres no;
   - documento de 64 KiB como máximo;
   - sin lotes de operaciones ni de variables;
   - sólo POST con JSON (ni GET, ni el método QUERY, ni multipart);
   - sin la herramienta Nitro y sin descarga del SDL por HTTP;
   - además, los topes propios de la biblioteca: ciclos de coordenadas y profundidad de la introspección.
8. **Introspección según el ambiente**, en la sección `GraphQL:Introspeccion` de los appsettings:
   - encendida en Desarrollo y Pruebas;
   - apagada en Producción y cuando la clave falta;
   - un valor que no es booleano detiene el arranque.

   El contrato público es el SDL versionado, `src/Decant.Api/GraphQL/esquema.graphql`. Una prueba de instantánea lo
   compara con el que sirve la API y clasifica cada diferencia como «rompe» o «no rompe». Un cambio que rompe se
   hace agregando el campo nuevo, marcando el viejo con `@deprecated` y retirándolo con aviso (no hay versión en la
   URL).
9. **Contrato de errores**: todo error lleva `extensions.code` y ninguno lleva la excepción, la pila, el SQL ni datos
   de la conexión. Los códigos propios son:
   - `ARGUMENTO_INVALIDO`, con `extensions.campo`;
   - `PROFUNDIDAD_EXCEDIDA`;
   - `COSTO_EXCEDIDO`;
   - `INTROSPECCION_DESHABILITADA`;
   - `CONSULTA_INVALIDA`;
   - `ERROR_INTERNO`.

   Los demás conservan su código `HCxxxx`. La normalización corre como filtro de errores (los de la ejecución) y como
   middleware al principio del pipeline: los errores de análisis y validación no pasan por los filtros.
10. **Sin autenticación (ADR 0012).** La prueba de superficie lista `* /graphql`. Con usuarios reales, la misma
    política que REST: `[Authorize]` por campo raíz con los roles del ADR 0012, pruebas 401/403 por campo y el
    presupuesto de costo por identidad.

## Alternativas descartadas
- **Reemplazar REST por GraphQL:** los gemelos de la paridad y los consumidores leen REST, y su contrato
  `problem+json` ya está probado. Conviven, y una prueba exige que digan lo mismo.
- **GraphQL.NET (MIT):** viable. Su análisis de complejidad es un modelo propio, no la especificación de costo que
  implementa HotChocolate, y la paginación por cursor se arma a mano.
- **Filtrado, orden y proyección automáticos sobre `IQueryable` (`HotChocolate.Data.EntityFramework`):** darían
  justo el filtrado arbitrario que llega a SQL sin una prueba por consulta, y romperían la regla de que `IQueryable`
  no sale de la infraestructura.
- **Paginación por desplazamiento (skip/take):** con datos que cambian, salta o repite elementos, y en PostgreSQL
  cuesta en proporción al desplazamiento.
- **Sólo operaciones persistidas (documentos registrados):** es el control más fuerte contra consultas abusivas,
  pero no hay clientes que registren sus documentos. Es el siguiente paso con consumidores reales.
- **Exponer tal cual los registros de la aplicación:** el esquema cambiaría con cada cambio interno. Lo impiden los
  tipos propios y una prueba de arquitectura.
- **Introspección siempre encendida o siempre apagada:** encendida le da el mapa a quien ataca en producción;
  apagada deja sin herramientas a quien desarrolla y prueba.

## Consecuencias
- Hay dos APIs que deben coincidir. `GraphQL.ParidadTests` compara cada campo de REST con su par en GraphQL: las
  selecciones salen de los registros de REST, así que un campo nuevo en REST sin su par rompe la prueba.
- Es una dependencia grande, 52 paquetes nuevos en el candado (50 de ChilliCream, incluida la herramienta Nitro, que
  no se expone), con avisos frecuentes. Trivy los inventaría y Dependabot los sube agrupados; en cada subida se
  revisan los avisos.
- Evidencia medida (pruebas en `tests/Decant.Api.Tests/GraphQL`):
  - una página de 1, 10 o 60 operaciones con su orden, sus partidas y la vuelta a la operación cuesta **5
    consultas SQL**;
  - lo rechazado por límites, argumentos o documento inválido cuesta **0**;
  - el detalle, la lista y el reporte coinciden campo por campo con REST, también en los días de 23 y 25 horas.
- La arquitectura lo hace cumplir: fuera de la API nadie conoce HotChocolate, GreenDonut ni ChilliCream (ni por
  tipos ni por referencias), y dentro de la API todo vive en `Decant.Api.GraphQL`.
