# Decant

[![ci](https://github.com/christianescamilla15-cell/decant/actions/workflows/ci.yml/badge.svg)](https://github.com/christianescamilla15-cell/decant/actions/workflows/ci.yml)
[![seguridad](https://github.com/christianescamilla15-cell/decant/actions/workflows/seguridad.yml/badge.svg)](https://github.com/christianescamilla15-cell/decant/actions/workflows/seguridad.yml)

Implementación de referencia, pública y ejecutable, de la modernización de un sistema legado **ficticio**: el
back-office de divisas y pagos internacionales del *Banco Ficticio del Norte* (BFN). El método viene de tres
programas reales de modernización; aquí se aplica de punta a punta sobre un legado inventado, con la evidencia en
el repositorio.

> **Estado: semana 1 de 4** — el legado ejecutable, su versión «viva» y la radiografía con su control público.
> El TO-BE (.NET 10 + PostgreSQL), la paridad y el corte llegan en las semanas siguientes.

## Qué hay

| Carpeta | Qué es |
|---|---|
| [`legado/`](legado) | El legado: SQL Server 2022 en Docker (`docker-compose.yml`), 7 tablas, 7 procedimientos, 1 vista, 1 trigger de bitácora y 1 job en msdb ([`sql/`](legado/sql)); un generador DETERMINISTA de 3 años ([`generador/`](legado/generador)); la pantalla de sólo lectura que lee por procedimientos ([`pantalla/`](legado/pantalla)); el respaldo FECHADO ([`respaldo.py`](legado/respaldo.py)) y la medición del daño de `bcp -c` ([`bcp.py`](legado/bcp.py)). |
| [`legado/vivo/`](legado/vivo) | El legado «vivo»: inyecta el delta del mismo día después del respaldo (operaciones, re-registros, liquidaciones, cambios de catálogo, un reenvío de sucursal fechado hacia atrás) y sigue escribiendo tras el congelamiento. Deja preparados los choques de S3. [`extraer_pantalla.py`](legado/extraer_pantalla.py) es el camino del delta por la PANTALLA en lugar de la base. |
| [`legado/TRAMPAS.md`](legado/TRAMPAS.md) | El catálogo de las 9 trampas sembradas, 3 defectos para decidir con negocio, 1 defecto que encontró la radiografía sin que nadie lo sembrara y la preparación de S3. La radiografía NO lo lee. |
| [`legado/VOLUMEN.md`](legado/VOLUMEN.md) | El volumen que hace falta para que el control negativo no salga en 0 % y el piso de la paridad, medidos en inversiones, y los tiempos del ciclo. |
| [`universo/`](universo) | Lo que ENTRA al replay: la partición por columna (entrada o resultado), la lectura de los archivos de interfaz con sus llaves reales (buzón del corresponsal y archivo de sucursales) y las noches del job. |
| [`radiografia/`](radiografia) | La radiografía (Python): restaura el respaldo en un contenedor limpio, lo cuadra contra lo que el legado publicaba, mide el corte, inventaría y detecta por patrón genérico. Los detectores están congelados en el tag `detectores-v4`. [`informe/`](radiografia/informe) es su salida sobre el legado, con el veredicto medido de cada hallazgo, y [`CONTROL.md`](radiografia/CONTROL.md) sus dos controles públicos. |
| [`docs/adr/`](docs/adr) | Las decisiones de la semana 1. |

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
  de 0 inversiones de contrato siempre; los empatados invertidos VARÍAN mucho entre corridas (observado de 2.6 % a 25 %), por eso cada comparación se juzga contra el piso de la MISMA corrida, nunca contra una constante. La lista con `TOP` sin `ORDER BY` ni siquiera devuelve las
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
- **Control a ciegas, ronda 2** ([CONTROL_CIEGO_2.md](radiografia/CONTROL_CIEGO_2.md)). Otra siembra sobre
  `detectores-v3`, y otra vez **0 de 3**. Dos trampas cayeron en límites que la v3 ya había documentado (vistas y el
  `JOIN … ON`) y una en una clase nueva (división entera). Documentar un límite no lo cubre.
- **`detectores-v4`** ([CONTROL.md](radiografia/CONTROL.md)) agrega los 3 arreglos genéricos de la ronda 2:
  - `TOP 100 PERCENT … ORDER BY` en una vista o tabla derivada: un orden que no existe;
  - la unicidad de una asignación es la del CONJUNTO: cada tabla unida debe quedar fija por una llave única suya;
  - división entera, con una inferencia mínima de tipos.

  Con ellos, el catálogo propio sigue en 8 de 9 y las 6 trampas de las rondas 1 y 2 salen 6 de 6, medidas por
  separado. **Tampoco cuenta como control**: los dos catálogos ya eran conocidos. La v4 espera la ronda 3.
- **Controles públicos** ([CONTROL.md](radiografia/CONTROL.md)). Ninguno es ya de generalización:
  WideWorldImporters es de entrenamiento y AdventureWorks fue el apartado de la v2.
  - Con la v3 aparecen 14 hallazgos nuevos y los 14 tienen la forma real. 11 son valores con espacios finales de
    verdad en WideWorldImporters.
  - 3 son asignaciones en AdventureWorks que la v3 marca por la razón equivocada: lee el WHERE y el filtro está en
    el ON.
  - Con la v4, **0 falsos positivos nuevos** en los dos (273 y 173 hallazgos, los mismos de la v3). Las 3
    asignaciones de AdventureWorks salen ahora por la razón correcta: el historial entra por un JOIN que no cubre
    su llave única. ORDER BY que no ordena y división entera dan 0 en los dos controles: sólo hay especificidad
    medida (5 divisiones entre `100.0` bien ignoradas), no sensibilidad.
  - Se publican tal cual, con los límites que quedan.
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
| 2 | `detectores-v3` | `e2c565f39b293a9846cdb7c1bb884721f1e60f562abf5a3ef2ccc380c11bbfbc` | **0 de 3** ([CONTROL_CIEGO_2.md](radiografia/CONTROL_CIEGO_2.md)) |
| 3 | `detectores-v4` | *pendiente* | *en espera de la siembra* |

Procedimiento (ronda 3):

1. **Detectores congelados.** El tag `detectores-v4` fija `radiografia/tsql.py`, `patrones.py` y `datos.py`. Sus
   sha256 están en [`radiografia/CONTROL.md`](radiografia/CONTROL.md) y una prueba falla si cambian.
2. **Siembra.** OTRA sesión crea una rama desde `detectores-v4` (por ejemplo `siembra-ciega-3`). Ahí cambia SÓLO
   `legado/` (código T-SQL, generador o datos) y escribe su catálogo en un archivo NUEVO,
   `legado/TRAMPAS_CIEGAS_3.md`, con el mismo formato de tabla de medición que `legado/TRAMPAS.md` (señales
   `categoría → objeto`, o vacío si cree que no hay patrón). No debe repetir las trampas de las rondas 1 y 2: ésas
   ya son conocidas.
3. **Compromiso.** Antes de que nadie corra nada, publica SÓLO el sha256 de su catálogo (en esta tabla, en un commit
   de `main`), sin el archivo.
4. **Corrida.** En la rama se corre `./ciclo.sh` sin cambiar `radiografia/`. El informe queda escrito sin que nadie
   haya visto el catálogo.
5. **Revelación.** Se agrega el catálogo y se verifica que su sha256 sea el publicado. Luego se mide con
   `python -m radiografia.medicion --trampas legado/TRAMPAS.md --trampas legado/TRAMPAS_CIEGAS_3.md`.
6. **Publicación tal cual:** el % de detección, lo que no detectó y los hallazgos fuera de su catálogo. Ningún
   detector cambia antes de publicar; si después se mejora uno, es `detectores-v5` y pide otra siembra.

## Cómo ejecutar

Requiere Docker y Python 3.12.

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DECANT_SA_PASSWORD='Una-Clave-Larga-1'   # contraseña de sa del contenedor local
./ciclo.sh                                       # lo mismo que corre el CI, con tiempos por paso
pytest -m integracion                            # contra el legado que dejó arriba ciclo.sh
docker compose -f legado/docker-compose.yml down -v
```

Paso a paso:

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
python -m radiografia.medicion --trampas legado/TRAMPAS.md \
    --trampas legado/TRAMPAS_CIEGAS.md --conocido legado/TRAMPAS_CIEGAS.md \
    --trampas legado/TRAMPAS_CIEGAS_2.md --conocido legado/TRAMPAS_CIEGAS_2.md   # % por catálogo, con veredictos
```

## Pruebas

- `pytest`: 129 pruebas sin base. Cubren:
  - el determinismo del generador (huella fija) y la existencia de cada trampa en los datos;
  - el universo: partición por columna, llaves reales del buzón, liquidaciones descartadas y nombres sanos en el
    archivo de sucursales;
  - el orden por inversiones;
  - cada detector con casos positivos y negativos, incluidas regresiones de los controles;
  - la no circularidad (ningún detector lee el catálogo) y el congelamiento de los detectores.
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

## Seguridad

Ver [SECURITY.md](SECURITY.md). CodeQL, Semgrep (bloqueante), Trivy, gitleaks, SBOM y una revisión de
confidencialidad corren en cada cambio (`.github/workflows/seguridad.yml`). Todo dato es inventado: el banco, sus
clientes, sus corresponsales (BIC `FICT…`) y sus CLABE (banco `987`). Sólo los estándares son reales: ISO 4217,
ISO 20022 `pacs.008`, MT103 y el dígito de control de la CLABE.

## Licencia

[MIT](LICENSE).
