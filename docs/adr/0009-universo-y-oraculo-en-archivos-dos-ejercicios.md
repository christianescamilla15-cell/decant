# ADR 0009 · Universo y oráculo en archivos distintos; dos ejercicios con nombre

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
Un replay que pueda leer resultados del legado se mide contra sí mismo. Y «la migración cuadra» no dice nada del
motor: son preguntas distintas.

## Decisión
- `python -m paridad.extraer` restaura el respaldo en un contenedor limpio y escribe, POR COLUMNA según
  `universo/particion.py`, `universo/` (llaves internas, entradas, la parte de entrada de cada mixta, archivos de
  interfaz y horario del job) y `oraculo/` (resultados y las salidas publicadas). Una prueba ata cada consulta a la
  partición; el lector del TO-BE exige encabezados exactos.
- **«Verificar la migración»:** `decant migrar` lee universo + oráculo (la historia tal cual) y la paridad compara
  byte a byte, esquema tras cada carga y cuadre por lado.
- **«Medir el motor»:** `decant reproducir` recibe SÓLO `IUniverso` (prueba de arquitectura: el manejador no puede
  recibir el oráculo), con las noches del horario de msdb y el reloj de cada noche. Corre hasta el corte MEDIDO.
- Las llaves son las del formato: UETR del bloque 3 y `:21:`; el `:20:` sólo enlaza la partida con su mensaje.

## Alternativas descartadas
- **Que el TO-BE lea SQL Server directo:** no habría manera de demostrar que el replay no vio un resultado.
- **Un solo ejercicio «paridad»:** un 100 % de la migración escondería un motor que no sabe calcular.

## Consecuencias
Universo y oráculo pesan ≈ 320 MB por corrida y no se versionan; sus manifiestos con sha256 sí viajan en el artefacto
del CI.
