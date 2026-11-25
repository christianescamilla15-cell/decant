# Arquitectura · Decant

Modelo C4 en tres niveles: contexto, contenedores y los componentes de la API. Los diagramas son texto (Mermaid) y
describen lo que hay en el código de la semana 2 (más la API GraphQL, ADR 0017), no un plan. Las decisiones están en
[`docs/adr/`](../adr).

## 1. Contexto

```mermaid
C4Context
  title Contexto · Decant (modernización del back-office de divisas del Banco Ficticio del Norte)
  Person(operador, "Mesa de operaciones", "Consulta operaciones, órdenes de pago y su conciliación")
  Person(negocio, "Negocio", "Decide las preguntas cerradas de cada discrepancia del legado")
  System_Ext(legado, "Legado BFN_DIVISAS", "SQL Server 2022 + T-SQL: procedimientos, vista, trigger y job nocturno")
  System(tobe, "Decant TO-BE", ".NET 10 + PostgreSQL: el mismo flujo con las reglas reimplementadas y probadas")
  System(paridad, "Paridad", "Python: verifica la migración, mide el motor y arbitra cada diferencia")
  System_Ext(sucursales, "Sistemas de sucursal", "Archivo de sucursales (UTF-8, ;)")
  System_Ext(corresponsal, "Corresponsal en Nueva York", "Confirmaciones de abono (estilo MT910, :13D: con desfase)")
  Rel(operador, legado, "Usa hoy", "pantalla HTTP")
  Rel(operador, tobe, "Usará", "API JSON: REST y GraphQL de sólo lectura")
  Rel(sucursales, legado, "Archivo de las 22:00")
  Rel(corresponsal, legado, "Buzón de confirmaciones")
  Rel(paridad, legado, "Restaura su respaldo fechado; audita el avance en el legado vivo")
  Rel(paridad, tobe, "Carga el universo y compara")
  Rel(negocio, paridad, "Lee el informe y responde las preguntas cerradas")
```

## 2. Contenedores

```mermaid
C4Container
  title Contenedores · Decant (S2)
  Person(operador, "Mesa de operaciones")
  System_Ext(respaldo, "Respaldo fechado del legado", ".bak de BFN_DIVISAS y msdb + manifiesto con lo publicado")
  System_Boundary(p, "Paridad (Python)") {
    Container(extractor, "Extractor", "python -m paridad.extraer", "Restaura en un contenedor LIMPIO y escribe universo y oráculo por columna")
    ContainerDb(universo, "Universo", "JSON Lines + archivos de interfaz", "Entradas, buzón, sucursales, horario del job")
    ContainerDb(oraculo, "Oráculo", "JSON Lines", "Resultados del legado y salidas publicadas")
    Container(arnes, "Arnés de paridad", "python -m paridad", "Byte a byte, esquema, cuadres, % por regla, arbitraje, gemelos")
  }
  System_Boundary(t, "TO-BE (.NET 10)") {
    Container(cli, "Lotes", "Decant.Cli", "migrar · reproducir (sólo universo, reloj inyectado) · reporte · configuración")
    Container(api, "API", "Decant.Api · Minimal API + HotChocolate", "REST: detalle, lista, reporte y configuración · GraphQL de sólo lectura (POST /graphql): el mismo grafo por cursor")
    ContainerDb(pg, "PostgreSQL 16", "EF Core + Npgsql", "Esquema decant: documentos por UETR, partidas por lo que SON, marcas")
  }
  Rel(extractor, respaldo, "Restaura y verifica sha256")
  Rel(extractor, universo, "Escribe")
  Rel(extractor, oraculo, "Escribe")
  Rel(cli, universo, "Lee (replay y carga)")
  Rel(cli, oraculo, "Lee (sólo la carga histórica)")
  Rel(cli, pg, "COPY binario en una transacción")
  Rel(api, pg, "Consultas LINQ (una por lote en GraphQL)")
  Rel(operador, api, "JSON/HTTP · GraphQL")
  Rel(arnes, pg, "Lee el TO-BE")
  Rel(arnes, api, "Gemelos: JSON del detalle")
```

## 3. Componentes de la API (REST y GraphQL)

```mermaid
C4Component
  title Componentes · Decant.Api (ADR 0012 y 0017)
  Person(operador, "Mesa de operaciones")
  Container_Boundary(api, "Decant.Api") {
    Component(rest, "Rutas REST", "Minimal API", "GET detalle, lista del día, reporte y configuración · errores problem+json")
    Component(esquema, "Esquema GraphQL", "Decant.Api.GraphQL · HotChocolate 16.7.7", "Query: operacion, operaciones y reporteDeOrdenes · cursores opacos · sin mutaciones")
    Component(limites, "Límites y contrato de errores", "Decant.Api.GraphQL", "Profundidad 8 · costo 10,000 · 64 KiB · sólo POST · introspección por ambiente · extensions.code")
    Component(cargadores, "Cargadores por lote", "DataLoader (GreenDonut)", "Operaciones por id · órdenes por operación · partidas por UETR de cada lado")
  }
  Container_Boundary(app, "Decant.Application") {
    Component(mediador, "Mediador y casos de uso de lectura", "ISolicitud / IManejador", "Validan página 1..100 y rangos de fechas")
    Component(puertos, "Puertos de lectura", "IConsultasTobe · IConsultasEnLote", "Detalle y listas · páginas por llave de conjunto y lotes")
  }
  Container_Boundary(inf, "Decant.Infrastructure") {
    Component(ef, "ConsultasEf", "EF Core · DbContext por alcance", "Las lecturas de REST")
    Component(lotes, "ConsultasEnLoteEf", "EF Core · un contexto por llamada (fábrica)", "Keyset y = ANY(@llaves): una consulta por lote, en paralelo")
    Component(proyecciones, "Proyecciones", "Expresiones LINQ", "Una sola definición: el documento más reciente, las vistas y el día local")
  }
  ContainerDb(pg, "PostgreSQL 16", "esquema decant")
  Rel(operador, rest, "GET /api/...")
  Rel(operador, esquema, "POST /graphql")
  Rel(esquema, limites, "Cada petición pasa antes por")
  Rel(esquema, cargadores, "Resuelve los campos con")
  Rel(rest, mediador, "Envía consultas")
  Rel(esquema, mediador, "Envía consultas de página")
  Rel(cargadores, mediador, "Envía un lote por ola")
  Rel(mediador, puertos, "Llama")
  Rel(puertos, ef, "Implementado por")
  Rel(puertos, lotes, "Implementado por")
  Rel(ef, proyecciones, "Usa")
  Rel(lotes, proyecciones, "Usa")
  Rel(ef, pg, "SQL")
  Rel(lotes, pg, "SQL")
```

## Capas del TO-BE (las hacen cumplir `tests/Decant.Architecture.Tests`)

| Proyecto | Depende de | Contiene |
|---|---|---|
| `Decant.Domain` | sólo la BCL | `OrdenDePago` (un documento por UETR), reglas de cambio, cargos, conciliación y vencimiento, lectura del MT910, `IClock`, `Resultado<T>`, invariante del reproceso |
| `Decant.Application` | Domain | casos de uso (carga histórica, replay, consultas, páginas y lotes de lectura, reproceso), puertos, mediador propio, banderas y destinos como records |
| `Decant.Infrastructure` | Application | EF Core + Npgsql (migraciones, consultas, lecturas por página y por lote con una fábrica de contextos), almacén con COPY, lectores del universo y del oráculo, `SystemClock` |
| `Decant.Api`, `Decant.Cli` | Infrastructure | composición, presentación (cada hora en su zona) y configuración por ambiente; en la API, el esquema GraphQL de sólo lectura, SÓLO en `Decant.Api.GraphQL` (HotChocolate no se conoce en ninguna otra capa: `GraphQLTests`) |

## El flujo de S2 en una corrida

1. `./ciclo.sh` levanta el legado, lo carga, toma el respaldo fechado y aplica el delta del día (legado vivo).
2. `python -m paridad` restaura el respaldo en un contenedor limpio, mide el corte y extrae universo y oráculo.
3. `decant migrar` (carga histórica) y cuatro `decant reproducir`: hasta el corte con banderas encendidas, dos en
   «sólo marca» y uno con TODO el universo (el TO-BE en sombra).
4. El arnés verifica la migración, mide el motor, compara el reporte del TO-BE en sombra con el que el legado
   publicó, levanta la pantalla del legado y la API para los gemelos, y escribe `paridad/informe/paridad.md`.
