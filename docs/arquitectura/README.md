# Arquitectura · Decant

Modelo C4 en dos niveles: contexto y contenedores. Los diagramas son texto (Mermaid) y describen lo que hay en el
código de la semana 2, no un plan. Las decisiones están en [`docs/adr/`](../adr).

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
  Rel(operador, tobe, "Usará", "API JSON")
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
    Container(api, "API", "Decant.Api · Minimal API", "Detalle, lista y reporte; configuración por ambiente")
    ContainerDb(pg, "PostgreSQL 16", "EF Core + Npgsql", "Esquema decant: documentos por UETR, partidas por lo que SON, marcas")
  }
  Rel(extractor, respaldo, "Restaura y verifica sha256")
  Rel(extractor, universo, "Escribe")
  Rel(extractor, oraculo, "Escribe")
  Rel(cli, universo, "Lee (replay y carga)")
  Rel(cli, oraculo, "Lee (sólo la carga histórica)")
  Rel(cli, pg, "COPY binario en una transacción")
  Rel(api, pg, "Consultas LINQ")
  Rel(operador, api, "JSON/HTTP")
  Rel(arnes, pg, "Lee el TO-BE")
  Rel(arnes, api, "Gemelos: JSON del detalle")
```

## Capas del TO-BE (las hacen cumplir `tests/Decant.Architecture.Tests`)

| Proyecto | Depende de | Contiene |
|---|---|---|
| `Decant.Domain` | sólo la BCL | `OrdenDePago` (un documento por UETR), reglas de cambio, cargos, conciliación y vencimiento, lectura del MT910, `IClock`, `Resultado<T>`, invariante del reproceso |
| `Decant.Application` | Domain | casos de uso (carga histórica, replay, consultas, reproceso), puertos, mediador propio, banderas y destinos como records |
| `Decant.Infrastructure` | Application | EF Core + Npgsql (migraciones, consultas), almacén con COPY, lectores del universo y del oráculo, `SystemClock` |
| `Decant.Api`, `Decant.Cli` | Infrastructure | composición, presentación (cada hora en su zona) y configuración por ambiente |

## El flujo de S2 en una corrida

1. `./ciclo.sh` levanta el legado, lo carga, toma el respaldo fechado y aplica el delta del día (legado vivo).
2. `python -m paridad` restaura el respaldo en un contenedor limpio, mide el corte y extrae universo y oráculo.
3. `decant migrar` (carga histórica) y cuatro `decant reproducir`: hasta el corte con banderas encendidas, dos en
   «sólo marca» y uno con TODO el universo (el TO-BE en sombra).
4. El arnés verifica la migración, mide el motor, compara el reporte del TO-BE en sombra con el que el legado
   publicó, levanta la pantalla del legado y la API para los gemelos, y escribe `paridad/informe/paridad.md`.
