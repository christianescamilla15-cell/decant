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
| [`legado/vivo/`](legado/vivo) | El legado «vivo»: inyecta el delta del mismo día después del respaldo (operaciones, re-registros, liquidaciones, cambios de catálogo) y sigue escribiendo tras el congelamiento. |
| [`legado/TRAMPAS.md`](legado/TRAMPAS.md) | El catálogo de las 9 trampas sembradas y 3 defectos para decidir con negocio, con su peso en los datos. La radiografía NO lo lee. |
| [`legado/VOLUMEN.md`](legado/VOLUMEN.md) | Cuánto volumen hace falta para que el control negativo no salga en 0 % (medido) y los tiempos del ciclo. |
| [`radiografia/`](radiografia) | La radiografía (Python): restaura el respaldo en un contenedor limpio, verifica el criterio de salida, mide el corte, inventaría y detecta por patrón genérico. [`informe/`](radiografia/informe) es su salida sobre el legado y [`CONTROL.md`](radiografia/CONTROL.md), su corrida sobre WideWorldImporters. |
| [`docs/adr/`](docs/adr) | Las decisiones de la semana 1. |

## Resultados de la semana 1

- **Criterio de salida:** el `COUNT(*)` de `dbo.operacion` en el respaldo restaurado (412,130) es la cifra que
  publicaba la pantalla del legado al tomarlo.
- **Detección:** la radiografía encuentra **8 de las 9 trampas (88.9 %)**
  ([medición](radiografia/informe/medicion.md)). La que no ve son los lados invertidos del detalle: no hay patrón
  de base de datos que la delate, y en S2 se atrapa leyendo el binding de la pantalla. También encuentra 1 de los 3
  defectos de negocio y 11 hallazgos fuera del catálogo, que quedan a la vista.
- **Control público** ([CONTROL.md](radiografia/CONTROL.md)): sobre WideWorldImporters, los detectores de alta
  señal dan 0 falsos positivos. INNER JOIN a una hija y centinelas numéricos dan 7 y 7, y se presentan como
  patrones de revisión. El detector de mojibake encontró daño real en la muestra de Microsoft («ChÃ¡vez» en 213
  facturas). La primera versión de los detectores tenía un defecto que el control destapó, y está documentado.
- **Control negativo:** con 400 operaciones por día, el reporte mensual del legado cambia de orden entre dos
  corridas sobre los mismos datos (44–76 % de las posiciones), así que la paridad de S2 tiene listón. Con 250 por día
  salía en 0 % ([medido](legado/VOLUMEN.md)).
- **Ciclo completo:** generar, cargar, respaldar, restaurar y radiografiar toma ≈ 2 minutos.

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
python -m legado.vivo                       # delta del mismo día y escrituras tras el congelamiento
python -m radiografia --manifiesto respaldos/respaldo_2023-12-29.json
python -m radiografia.medicion              # % de detección contra legado/TRAMPAS.md
```

## Pruebas

- `pytest`: 74 pruebas sin base. Cubren el determinismo del generador (huella fija), el volumen medido, la existencia
  de cada trampa en los datos, cada detector con casos positivos y negativos (incluidas regresiones del control
  público) y la no circularidad: ningún detector lee el catálogo de trampas.
- `pytest -m integracion`: 9 pruebas contra SQL Server real. Comprueban que el generador calcula lo mismo que los
  procedimientos del legado (tipo de cambio, comisión truncada, horas de liquidación, re-registro), el control
  negativo, que `GETDATE()` del job vence todo lo pendiente (dentro de una transacción que se revierte) y el daño
  de `bcp -c`.

## Seguridad

Ver [SECURITY.md](SECURITY.md). CodeQL, Semgrep (bloqueante), Trivy, gitleaks, SBOM y una revisión de
confidencialidad corren en cada cambio (`.github/workflows/seguridad.yml`). Todo dato es inventado: el banco, sus
clientes, sus corresponsales (BIC `FICT…`) y sus CLABE (banco `987`). Sólo los estándares son reales: ISO 4217,
ISO 20022 `pacs.008`, MT103 y el dígito de control de la CLABE.

## Licencia

[MIT](LICENSE).
