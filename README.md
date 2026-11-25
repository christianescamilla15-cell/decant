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
| [`radiografia/`](radiografia) | La radiografía (Python): restaura el respaldo en un contenedor limpio, lo cuadra contra lo que el legado publicaba, mide el corte, inventaría y detecta por patrón genérico. Los detectores están congelados en el tag `detectores-v2`. [`informe/`](radiografia/informe) es su salida sobre el legado, con el veredicto medido de cada hallazgo, y [`CONTROL.md`](radiografia/CONTROL.md) sus dos controles públicos. |
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
  de 18–25 % de empatados invertidos (tres corridas) y 0 de contrato. La lista con `TOP` sin `ORDER BY` ni siquiera devuelve las
  mismas filas en otra instancia (17 de 200 distintas).
- **Controles públicos** ([CONTROL.md](radiografia/CONTROL.md)):
  - WideWorldImporters es de entrenamiento: ahí se corrigió la v1, y su mojibake real («ChÃ¡vez» en 213
    facturas) sigue apareciendo.
  - AdventureWorks es el control APARTADO: se corrió una sola vez con los detectores congelados y se publica tal
    cual. Los detectores de alta señal dan 0 falsos positivos; apareció un límite nuevo (4 IF EXISTS que sólo
    escriben en una variable de tabla).
- **Universo para el replay** ([ADR 0004](docs/adr/0004-universo-por-columna-y-archivos-de-interfaz.md)):
  - partición por columna;
  - el buzón del corresponsal con las 5,779 liquidaciones que el legado descartó;
  - el archivo de sucursales en UTF-8 sano;
  - las 1,090 noches del job.
- **Ciclo completo:** generar, cargar, respaldar, restaurar, radiografiar, medir veredictos y medir la detección
  toma ≈ 3.5 minutos ([tiempos](legado/VOLUMEN.md)).

## Control a ciegas (pendiente)

Quien escribe las trampas y quien escribe los detectores aquí es la misma persona: falta medir la radiografía
contra trampas que su autor NO conozca. Procedimiento:

1. **Detectores congelados.** El tag `detectores-v2` fija `radiografia/tsql.py`, `patrones.py` y `datos.py`. Sus
   sha256 están en [`radiografia/CONTROL.md`](radiografia/CONTROL.md) y una prueba falla si cambian.
2. **Siembra.** OTRA sesión crea la rama `siembra-ciega` desde `detectores-v2`. Ahí cambia SÓLO `legado/` (código
   T-SQL, generador o datos) y escribe su catálogo en `legado/TRAMPAS_CIEGAS.md`, con el mismo formato de tabla de
   medición que `legado/TRAMPAS.md` (señales `categoría → objeto`, o vacío si cree que no hay patrón).
3. **Compromiso.** Antes de que nadie corra nada, publica SÓLO el sha256 de `TRAMPAS_CIEGAS.md` (en este README,
   en un commit de `main`), sin el archivo.
4. **Corrida.** En la rama se corre `./ciclo.sh` sin cambiar `radiografia/`. El informe queda escrito sin que nadie
   haya visto el catálogo.
5. **Revelación.** Se agrega `TRAMPAS_CIEGAS.md` y se verifica que su sha256 sea el publicado. Luego se mide con
   `python -m radiografia.medicion --trampas legado/TRAMPAS_CIEGAS.md`.
6. **Publicación tal cual:** el % de detección, lo que no detectó y los hallazgos fuera de su catálogo. Ningún
   detector cambia antes de publicar; si después se mejora uno, es `detectores-v3` y pide otra siembra.

sha256 del catálogo ciego: *pendiente.*

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
python -m radiografia.medicion              # % de detección contra legado/TRAMPAS.md, con los veredictos
```

## Pruebas

- `pytest`: 100 pruebas sin base. Cubren:
  - el determinismo del generador (huella fija) y la existencia de cada trampa en los datos;
  - el universo: partición por columna, llaves reales del buzón, liquidaciones descartadas y nombres sanos en el
    archivo de sucursales;
  - el orden por inversiones;
  - cada detector con casos positivos y negativos, incluidas regresiones de los controles;
  - la no circularidad (ningún detector lee el catálogo) y el congelamiento de los detectores.
- `pytest -m integracion`: 14 pruebas contra SQL Server real. Comprueban:
  - que el generador calcula lo mismo que los procedimientos del legado;
  - el criterio de salida contra el manifiesto;
  - el control negativo en inversiones;
  - que `GETDATE()` del job vence todo lo pendiente (dentro de una transacción que se revierte);
  - el daño de `bcp -c`;
  - los veredictos;
  - los choques preparados para S3;
  - las liquidaciones del buzón;
  - lo que pierde el delta por la pantalla.

## Seguridad

Ver [SECURITY.md](SECURITY.md). CodeQL, Semgrep (bloqueante), Trivy, gitleaks, SBOM y una revisión de
confidencialidad corren en cada cambio (`.github/workflows/seguridad.yml`). Todo dato es inventado: el banco, sus
clientes, sus corresponsales (BIC `FICT…`) y sus CLABE (banco `987`). Sólo los estándares son reales: ISO 4217,
ISO 20022 `pacs.008`, MT103 y el dígito de control de la CLABE.

## Licencia

[MIT](LICENSE).
