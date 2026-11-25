# Decant

[![ci](https://github.com/christianescamilla15-cell/decant/actions/workflows/ci.yml/badge.svg)](https://github.com/christianescamilla15-cell/decant/actions/workflows/ci.yml)
[![seguridad](https://github.com/christianescamilla15-cell/decant/actions/workflows/seguridad.yml/badge.svg)](https://github.com/christianescamilla15-cell/decant/actions/workflows/seguridad.yml)

Implementación de referencia, pública y ejecutable, de la modernización de un sistema legado **ficticio**: el
back-office de divisas y pagos internacionales del *Banco Ficticio del Norte* (BFN). El método viene de tres
programas reales de modernización; aquí se aplica de punta a punta sobre un legado inventado, con la evidencia en
el repositorio.

> **Estado: semana 2 de 4** — al legado ejecutable, su versión «viva» y la radiografía (S1) se suman el TO-BE en
> .NET 10 + PostgreSQL y la paridad medida contra el legado: «verificar la migración», «medir el motor», paridad de
> reporte con arbitraje y gemelos. El corte ensayable llega en S3.

## Qué hay

| Carpeta | Qué es |
|---|---|
| [`legado/`](legado) | El legado: SQL Server 2022 en Docker (`docker-compose.yml`), 7 tablas, 7 procedimientos, 1 vista, 1 trigger de bitácora y 1 job en msdb ([`sql/`](legado/sql)); un generador DETERMINISTA de 3 años ([`generador/`](legado/generador)); la pantalla de sólo lectura que lee por procedimientos ([`pantalla/`](legado/pantalla)); el respaldo FECHADO ([`respaldo.py`](legado/respaldo.py)) y la medición del daño de `bcp -c` ([`bcp.py`](legado/bcp.py)). |
| [`legado/vivo/`](legado/vivo) | El legado «vivo»: inyecta el delta del mismo día después del respaldo (operaciones, re-registros, liquidaciones, cambios de catálogo, un reenvío de sucursal fechado hacia atrás) y sigue escribiendo tras el congelamiento. Deja preparados los choques de S3. [`extraer_pantalla.py`](legado/extraer_pantalla.py) es el camino del delta por la PANTALLA en lugar de la base. |
| [`legado/TRAMPAS.md`](legado/TRAMPAS.md) | El catálogo de las 9 trampas sembradas, 3 defectos para decidir con negocio, 1 defecto que encontró la radiografía sin que nadie lo sembrara y la preparación de S3. La radiografía NO lo lee. |
| [`legado/VOLUMEN.md`](legado/VOLUMEN.md) | El volumen que hace falta para que el control negativo no salga en 0 % y el piso de la paridad, medidos en inversiones, y los tiempos del ciclo. |
| [`universo/`](universo) | Lo que ENTRA al replay: la partición por columna (entrada o resultado), la lectura de los archivos de interfaz con sus llaves reales (buzón del corresponsal y archivo de sucursales) y las noches del job. |
| [`radiografia/`](radiografia) | La radiografía (Python): restaura el respaldo en un contenedor limpio, lo cuadra contra lo que el legado publicaba, mide el corte, inventaría y detecta por patrón genérico. Los detectores están congelados en el tag `detectores-v3`. [`informe/`](radiografia/informe) es su salida sobre el legado, con el veredicto medido de cada hallazgo, y [`CONTROL.md`](radiografia/CONTROL.md) sus dos controles públicos. |
| [`src/`](src) | El TO-BE en .NET 10: `Decant.Domain` (sólo BCL: reglas puras, `IClock`, `Resultado<T>`), `Decant.Application` (casos de uso, puertos, mediador propio, banderas como records), `Decant.Infrastructure` (EF Core + Npgsql, migraciones, COPY binario) y dos hosts con la misma composición: `Decant.Api` (Minimal API) y `Decant.Cli` (lotes). |
| [`tests/Decant.*`](tests) | Pruebas por capa: dominio con casos reales del respaldo, aplicación con dobles a mano, infraestructura y API contra PostgreSQL real (Testcontainers) y arquitectura (NetArchTest + Mono.Cecil). |
| [`paridad/`](paridad) | La paridad en Python: universo y oráculo en archivos y funciones distintos, los dos ejercicios con nombre, la paridad de reporte con arbitraje y los gemelos. [`informe/`](paridad/informe) es su salida sobre el legado del ciclo. |
| [`docs/`](docs) | [Arquitectura C4](docs/arquitectura/README.md), [reglas → prueba → origen](docs/reglas.md) y las [decisiones](docs/adr) de S1 (0001–0004) y S2 (0005–0011). |

## Resultados de la semana 2 ([informe completo](paridad/informe/paridad.md))

Un comando, `python -m paridad`, restaura el respaldo en un contenedor limpio, mide el corte (29-dic-2023 03:44:36,
la última escritura), extrae universo y oráculo por columna, carga el TO-BE cinco veces y escribe el informe.

- **«Verificar la migración»** (carga histórica): las 7 tablas byte a byte, 13.7 millones de celdas y 138 MB después
  de los parches documentados, **0 faltan, 0 sobran, 0 distintas**. Cada parche es una transformación EXACTA con el
  predicado de su hallazgo ([reglas](docs/parches.md)). Lo que aplica se mide en el ORIGEN por otro camino (SQL en el
  legado restaurado) y debe coincidir. Los conteos aplicados y medidos son iguales: 107,265 CLABE y 128,220 BIC
  «NA» a NULL, 53,702 tipos de cambio en 0 a NULL y 48,013 referencias con el relleno de ancho fijo de la ronda 1 a
  ciegas. Además, cada defecto DISTINTO inyectado en su columna falla (relleno fuera de la ventana, tabulador,
  truncado, «N/A», una hora corrida). Las 119,897 filas REEMPLAZADA son copias exactas del documento y sus 395,618
  partidas se reconstruyen. El **esquema** se compara columna por columna después de cada una de las 5 cargas, y su
  control negativo (un TO-BE sin `codigo_proposito`, T6) falla nombrándola. El **cuadre por lado** («Σ partes = total
  del encabezado») da 0 violaciones en el legado (con los lados que pinta la pantalla) y en el TO-BE; con los lados
  según el NOMBRE de la tabla da 446,151.
- **«Medir el motor»** (replay sólo del universo, reloj de cada noche del job): las **11 reglas al 100 %**. Las horas
  de liquidación (R08) REPLICAN la hora fija del legado mientras negocio no decida (ADR 0006). La corrección se
  publica como hipótesis: con los instantes reales coincidiría en 71.28 %, y la auditoría va en los dos sentidos. Con
  Nueva York por el `:13D:` del buzón, desfase extra ≠ 0 ⇔ diferencia en los 144,183 casos, sin violaciones. Las
  41,414 diferencias se desglosan por ventana: 34,595 de 2023 y 6,819 de las primaveras y otoños de 2021 y 2022. La
  paridad encontró **un defecto nuestro**: 5 folios OP en otro orden en la hora que se repite el 31-oct-2021. Se
  corrigió con su regla (orden de llegada) y su prueba. Con las acciones del job en **«sólo marca»**, las 110,424
  marcas de vencimiento y las 144,183 de conciliación coinciden 100 % con la bitácora del legado, noche por noche.
- **Paridad de reporte**: el reporte del TO-BE en sombra (todo el universo) contra el que el legado publicó al
  respaldar, por llave natural: 0 defectos nuestros, 181 renglones de **avance de producción** (confirmaciones
  posteriores al corte, auditadas en el legado vivo por identidad) y 14,984 celdas por una **regla real del legado**
  (publica la hora local sin zona; el TO-BE publica la misma hora con su desfase). Orden: **0 inversiones de
  contrato**; los empates se juzgan contra el piso de la misma corrida, medido con el plan variado (una sola
  re-corrida llegó a reproducir el orden exacto en un clon limpio, mientras la radiografía del mismo ciclo medía
  13.78 %). Ninguna llave secundaria candidata se salva: el legado las invierte todas en alguna variante del plan.
  El comparador demuestra que puede fallar con **6 mutantes** del reporte del TO-BE (un par de contrato invertido, un
  renglón quitado o duplicado, un centavo, una hora corrida con el desfase bien escrito, un avance que el legado vivo
  no tiene), y todos fallan. El punto ciego de la hora repetida queda declarado (0 celdas en este reporte).
- **Gemelos** (pantalla de detalle del legado contra el JSON de la API) en 3 casos estratificados, y **T4** probado por
  el binding de la pantalla: el TO-BE publica en `liquidadoPorElCorresponsal` lo que la rejilla «Liquidado por el
  corresponsal» pinta, que vive en la tabla `partida_solicitada`.
- **Trampas de las rondas a ciegas, medido tal cual:** la verificación de la migración vio 1 de 6 (los espacios
  finales); 2 son latentes y 3 viven en salidas que la paridad de S2 no compara. La paridad sólo ve el efecto en lo
  que compara ([tabla](paridad/informe/paridad.md#trampas-de-las-rondas-a-ciegas-la-paridad-vio-su-efecto)).

## Resultados de la semana 1

- **Criterio de salida no tautológico** ([informe](radiografia/informe/radiografia.md)). El respaldo restaurado
  cuadra con lo que el legado decía de sí mismo al tomarlo: COUNT y MAX(id) de las 7 tablas y los contadores de
  folio. La pantalla publica «Órdenes de pago: 150,719», y la radiografía tuvo que averiguar que cuenta DOCUMENTOS
  (uetr distintos), no las 270,616 filas: 119,897 son re-registros.
- **Detección:** **8 de las 9 trampas (88.9 %)** ([medición](radiografia/informe/medicion.md)).
  - La que no ve son los lados invertidos del detalle: no hay patrón de base de datos que la delate, y en S2 se
    atrapa leyendo el binding de la pantalla.
  - De los defectos de negocio detecta D1 (con un detector genérico agregado después) y D3.
  - Los 11 hallazgos fuera del catálogo llevan cada uno su veredicto MEDIDO: 4 TOP latentes, 1 **defecto real que
    nadie sembró** (se puede operar en una moneda dada de baja), inventario, señales de respaldo de T9 y la bitácora
    como fuente del replay.
- **Control negativo en inversiones** ([medido](legado/VOLUMEN.md)). Con 400 operaciones por día, el reporte
  mensual del legado invierte 26–28 % de sus pares empatados entre dos corridas, con 0 inversiones de contrato.
  Con 250 por día salía en 0. El piso real, el respaldo restaurado contra lo que el legado PUBLICÓ al tomarlo, es
  de 18–25 % de empatados invertidos (tres corridas) y 0 de contrato. La lista con `TOP` sin `ORDER BY` ni siquiera devuelve las
  mismas filas en otra instancia (17 de 200 distintas).
- **Control a ciegas, ronda 1** ([CONTROL_CIEGO.md](radiografia/CONTROL_CIEGO.md)). Otra sesión sembró 3 trampas
  sin que el autor de los detectores las conociera, y `detectores-v2` detectó **0 de 3**. Los detectores acertaban
  en precisión pero no generalizaban más allá de la forma literal.
- **`detectores-v3`** ([CONTROL.md](radiografia/CONTROL.md)) agrega los 3 arreglos genéricos que propuso quien
  sembró:
  - asignación desde varias filas, según las llaves únicas reales del esquema;
  - reloj que entra a la regla por una variable;
  - espacios finales medidos en el motor.

  Con ellos, el catálogo propio sigue en 8 de 9. Las 3 trampas de la ronda 1 salen 3 de 3, pero **eso no cuenta
  como control**: el catálogo ya era conocido.
- **Controles públicos** ([CONTROL.md](radiografia/CONTROL.md)). Ninguno es ya de generalización:
  WideWorldImporters es de entrenamiento y AdventureWorks fue el apartado de la v2.
  - Con la v3 aparecen 14 hallazgos nuevos y los 14 tienen la forma real. 11 son valores con espacios finales de
    verdad en WideWorldImporters.
  - 3 son asignaciones en AdventureWorks que el detector marca por la razón equivocada: lee el WHERE y el filtro
    está en el ON.
  - Se publican tal cual, con los dos límites nuevos que muestran.
- **Universo para el replay** ([ADR 0004](docs/adr/0004-universo-por-columna-y-archivos-de-interfaz.md)):
  - partición por columna;
  - el buzón del corresponsal con las 5,779 liquidaciones que el legado descartó;
  - el archivo de sucursales en UTF-8 sano;
  - las 1,090 noches del job.
- **Ciclo completo:** generar, cargar, respaldar, restaurar, radiografiar, medir veredictos y medir la detección
  toma ≈ 3.5 minutos ([tiempos](legado/VOLUMEN.md)).

## Control a ciegas

Quien escribe las trampas y quien escribe los detectores aquí es la misma persona: hace falta medir la radiografía
contra trampas que su autor NO conozca.

| Ronda | Detectores | Catálogo sellado (sha256) | Resultado |
|---|---|---|---|
| 1 | `detectores-v2` | `b61937e5011df6576ad97bd9e560babd7e0ce3cac87adc937900eede03b90866` | **0 de 3** ([CONTROL_CIEGO.md](radiografia/CONTROL_CIEGO.md)) |
| 2 | `detectores-v3` | *pendiente* | *en espera de la siembra* |

Procedimiento (ronda 2):

1. **Detectores congelados.** El tag `detectores-v3` fija `radiografia/tsql.py`, `patrones.py` y `datos.py`. Sus
   sha256 están en [`radiografia/CONTROL.md`](radiografia/CONTROL.md) y una prueba falla si cambian.
2. **Siembra.** OTRA sesión crea una rama desde `detectores-v3` (por ejemplo `siembra-ciega-2`). Ahí cambia SÓLO
   `legado/` (código T-SQL, generador o datos) y escribe su catálogo en un archivo NUEVO,
   `legado/TRAMPAS_CIEGAS_2.md`, con el mismo formato de tabla de medición que `legado/TRAMPAS.md` (señales
   `categoría → objeto`, o vacío si cree que no hay patrón). No debe repetir las trampas de la ronda 1: ésas ya
   son conocidas.
3. **Compromiso.** Antes de que nadie corra nada, publica SÓLO el sha256 de su catálogo (en esta tabla, en un commit
   de `main`), sin el archivo.
4. **Corrida.** En la rama se corre `./ciclo.sh` sin cambiar `radiografia/`. El informe queda escrito sin que nadie
   haya visto el catálogo.
5. **Revelación.** Se agrega el catálogo y se verifica que su sha256 sea el publicado. Luego se mide con
   `python -m radiografia.medicion --trampas legado/TRAMPAS.md --trampas legado/TRAMPAS_CIEGAS_2.md`.
6. **Publicación tal cual:** el % de detección, lo que no detectó y los hallazgos fuera de su catálogo. Ningún
   detector cambia antes de publicar; si después se mejora uno, es `detectores-v4` y pide otra siembra.

## Cómo ejecutar

Requiere Docker, Python 3.12 y, para el TO-BE, el SDK de .NET 10.

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DECANT_SA_PASSWORD='Una-Clave-Larga-1'   # contraseña de sa del contenedor local
./ciclo.sh                                       # lo mismo que corre el CI, con tiempos por paso
pytest -m integracion                            # contra el legado que dejó arriba ciclo.sh
docker compose -f legado/docker-compose.yml down -v
```

TO-BE y paridad (requieren .NET 10 SDK y el legado que dejó `./ciclo.sh` arriba):

```
dotnet build Decant.slnx -c Release
dotnet test Decant.slnx                          # dominio, aplicación, arquitectura, infraestructura y API
export DECANT_PG_PASSWORD='otra-clave' DECANT_PG_PUERTO=15450
docker run -d --name decant-pg -e POSTGRES_USER=decant -e POSTGRES_PASSWORD="$DECANT_PG_PASSWORD" \
  -p 127.0.0.1:15450:5432 postgres:16-alpine
python -m paridad --manifiesto respaldos/respaldo_2023-12-29.json   # → paridad/informe/paridad.md
pytest -m paridad                                # T4 y las demás pruebas sobre el informe
dotnet src/Decant.Cli/bin/Release/net10.0/decant.dll configuracion   # banderas y destinos por ambiente
docker rm -f -v decant-pg                        # -v: también el volumen de datos (≈ 2.7 GB)
```

Paso a paso del legado:

```
docker compose -f legado/docker-compose.yml up -d --wait
python -m legado esquema --recrear
python -m legado cargar                     # 3 años, semilla fija → la misma huella siempre
python -m legado pantalla &                 # http://127.0.0.1:8080/
python -m legado respaldar                  # respaldos/bfn_divisas_2023-12-29.bak + msdb + manifiesto
python -m legado.vivo                       # delta del mismo día, escrituras tras el congelamiento y choques de S3
python -m legado.extraer_pantalla --fecha 2023-12-29 --salida legado/datos/delta_por_pantalla.jsonl
python -m radiografia --manifiesto respaldos/respaldo_2023-12-29.json
python -m radiografia.veredictos --manifiesto respaldos/respaldo_2023-12-29.json
python -m radiografia.medicion --trampas legado/TRAMPAS.md --trampas legado/TRAMPAS_CIEGAS.md \
    --conocido legado/TRAMPAS_CIEGAS.md     # % de detección por catálogo, con los veredictos
```

## Pruebas

- `pytest`: 164 pruebas sin base. Cubren:
  - el determinismo del generador (huella fija) y la existencia de cada trampa en los datos;
  - el universo: partición por columna, llaves reales del buzón, liquidaciones descartadas y nombres sanos en el
    archivo de sucursales;
  - el orden por inversiones;
  - cada detector con casos positivos y negativos, incluidas regresiones de los controles;
  - la no circularidad (ningún detector lee el catálogo) y el congelamiento de los detectores;
  - la paridad: universo y oráculo atados a la partición, cada parche exacto con su control negativo, la conversión
    de horas contra la del generador, esquema con su control de T6, arbitraje, R08 como hipótesis, los mutantes del
    reporte, cuadre por lado y el binding de la pantalla;
  - que `--reusar-cargas` sólo reutilice cargas hechas por el mismo código y el mismo respaldo (llave sha256), y que
    cada tabla de las migraciones tenga origen en el legado o declaración (sin esperar al job de paridad).
- `pytest -m integracion`: 16 pruebas contra SQL Server real. Comprueban:
  - que el generador calcula lo mismo que los procedimientos del legado;
  - el criterio de salida contra el manifiesto;
  - el control negativo en inversiones;
  - que `GETDATE()` del job vence todo lo pendiente (dentro de una transacción que se revierte);
  - el daño de `bcp -c`;
  - los veredictos;
  - los choques preparados para S3;
  - las liquidaciones del buzón;
  - lo que pierde el delta por la pantalla;
  - los espacios finales contados en el motor y la medición separada por catálogo.

- `dotnet test Decant.slnx`: 183 pruebas del TO-BE.
  - `Decant.Domain.Tests` (85): cada regla con casos reales del respaldo (operaciones, comisiones, horas en las tres
    ventanas de horario, una vencida la noche del cambio de horario, mensajes reales del buzón: una fila por cada
    variante de formato que existe entre sus 150,124 mensajes), bordes e invariantes. Mutación del dominio con
    Stryker.NET como compuerta (`.github/workflows/mutacion.yml`, ruptura en 80: en cada PR sólo lo cambiado, cada
    noche completo): **91.62 %** (153 de 164) con los textos de error excluidos por método (`stryker-config.json`);
    sin esa exclusión, 83.87 %. Sobreviven mutantes equivalentes, como `Sum` contra `Max` sobre el único principal.
  - `Decant.Application.Tests` (23): el replay, la carga histórica y el reproceso con dobles escritos a mano, y las
    invariantes del lote (dos veces no duplica, permutado da lo mismo, un archivo dañado no detiene a los demás, un
    rechazo de negocio no es error técnico ni se reintenta).
  - `Decant.Infrastructure.Tests` (25) y `Decant.Api.Tests` (33): EF Core, COPY y la API completa contra PostgreSQL
    real con Testcontainers: bordes de fecha (día local de 23 y 25 horas, rangos inclusivos), el estatus como texto
    de ida y vuelta, cargas simultáneas
    contra los índices únicos, la migración nueva sobre una base con datos (y su reversa), el contrato de errores
    `problem+json` (sin autenticación en el alcance: [ADR 0012](docs/adr/0012-api-sin-autenticacion-en-el-alcance-de-la-demo.md))
    y que cada propiedad de la configuración se lea de su clave.
  - `Decant.Architecture.Tests` (17): capas, el replay sin acceso al oráculo, nadie usa `DateTime.Now` salvo
    `SystemClock` (recorriendo el IL), ningún tipo de EF fuera de la infraestructura, lecturas sin rastreo, ni
    defaults de reloj en la base ni conversiones de zona fuera de `Zonas`, y la fecha valor como `date`.
- `pytest -m paridad`: 8 pruebas sobre el informe de paridad, entre ellas la de T4 por el binding de la pantalla.

## Seguridad

Ver [SECURITY.md](SECURITY.md). CodeQL, Semgrep (bloqueante), Trivy, gitleaks, SBOM y una revisión de
confidencialidad corren en cada cambio (`.github/workflows/seguridad.yml`). Todo dato es inventado: el banco, sus
clientes, sus corresponsales (BIC `FICT…`) y sus CLABE (banco `987`). Sólo los estándares son reales: ISO 4217,
ISO 20022 `pacs.008`, MT103 y el dígito de control de la CLABE.

## Licencia

[MIT](LICENSE).
