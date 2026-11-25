# ADR 0001 · El legado ficticio corre en SQL Server 2022 dentro de Docker

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
Las trampas que interesan demostrar son del MOTOR y de su dialecto. Un TOP sin ORDER BY que cambia con el plan
paralelo, `GETDATE()` en hora local, `smalldatetime` al minuto, `bcp`, jobs que viven en msdb y respaldos `.bak`
que se restauran en otro servidor. Un legado en SQLite o PostgreSQL no tendría ninguna de ellas de verdad. Además,
la radiografía necesita un respaldo real que restaurar en un contenedor limpio.

## Decisión
- SQL Server 2022 Developer (`ACCEPT_EULA=Y`) en `legado/docker-compose.yml`, con la imagen fijada por digest
  (CU28). El contenedor limpio de la radiografía usa la misma imagen, y una prueba exige que coincidan.
- El servidor vive en hora local (`TZ=America/Mexico_City`), como el legado que imita: `GETDATE()` devuelve la
  hora de la Ciudad de México.
- **El Agent queda apagado.** El job existe en msdb (`sp_add_job` funciona sin el Agent) y la radiografía lo
  inventaría desde la copia restaurada de msdb. Si el Agent corriera, a las 23:30 del reloj REAL (2026) el job
  vencería todo lo pendiente de datos de 2023 (trampa T8) y los datos dejarían de ser reproducibles.
- El respaldo incluye msdb porque ahí viven los jobs: un `.bak` sólo de la base no los trae.
- En CI, SQL Server corre como servicio del job con el MISMO `docker-compose.yml` (no con `services:`). Así el CI
  prueba el archivo que usa quien clona el repo, y la contraseña de sa se genera por corrida sin ser un secreto.

## Alternativas descartadas
- **PostgreSQL o SQLite como legado:** sin T-SQL, sin `.bak`, sin msdb y sin el comportamiento de planes de SQL
  Server.
- **Azure SQL Edge:** fuera de soporte; no trae el Agent ni `bcp` en la imagen.
- **`services:` de GitHub Actions:** el contenedor arranca antes del checkout, con una contraseña fija en el YAML,
  y obliga a mantener dos definiciones del legado.

## Consecuencias
- Hace falta Docker y unos 4 GB de RAM por contenedor (legado + contenedor limpio de la radiografía).
- El job no se ejecuta solo. Su efecto histórico lo simula el generador, y la prueba de integración lo ejecuta
  dentro de una transacción que se revierte.
