# ADR 0014 · Puerta de cobertura de salidas y oráculo capturado en el corte

- Estado: propuesta (borrador de S3) · Fecha: 2026-11-25

## Contexto
La paridad de S2 compara las tablas, el reporte de órdenes y la pantalla de detalle. Seis trampas a ciegas con
efecto observable viven en salidas que no compara, y por eso no las vio. Lo que no está en el inventario no se
compara, y lo que no se compara pasa.

## Decisión
- **Inventario por dos fuentes:**
  - el código del legado: procedimientos, vistas, triggers, jobs, interfaces y pantalla, incluido el texto de SQL
    dinámico;
  - lo que el servidor ejecuta de verdad: Query Store y estadísticas de ejecución durante un ciclo completo que
    incluya un cierre de mes.
- **TODO objeto que existe en el código lleva renglón.** El código decide qué entra; las estadísticas sólo
  clasifican. «No se vio ejecutar» NO es «no tiene consumidor»: un procedimiento de contingencia casi nunca aparece
  en Query Store ni en `dm_exec_*_stats`. Lo no observado queda «sin ejecución observada».
- Cada renglón termina en uno de tres destinos: **comparado**, **reemplazado con paridad** o **retirado**. Retirar
  exige dueño, fecha y la confirmación del vigía en sólo lectura después del corte (ADR 0016) de que nadie lo llama.
  Nunca se retira sólo por el silencio de las estadísticas.
- Lo que escribe pasa por la paridad de ESTADO (ADR 0015) se haya observado o no su ejecución: es la única forma de
  ver su efecto.
- **La puerta:** 0 objetos del código sin renglón. Es un check del CI que falla nombrando el objeto.
- **Oráculo capturado EN el corte:** la salida de cada objeto de lectura con parámetros representativos (incluido el
  borde de fin de mes) y el instante del servidor al correrla. El TO-BE las re-corre con ese reloj inyectado.
- **Lo latente** se mide con las variantes del plan del piso (ADR 0011). Si el legado no coincide consigo mismo, es
  un defecto a decidir, no un contrato.

## Alternativas descartadas
- **Sólo el código:** no ve consumidores externos ni el SQL que se arma afuera.
- **Sólo las estadísticas (o que ellas recorten el inventario):** no ven los caminos que el ciclo no ejecutó
  (fin de mes, contingencia). Medido: los 3 procedimientos de la ronda 3 no se ejecutan en el ciclo y la paridad de
  salidas vio 0 de 3; la radiografía, 0 de 9 a ciegas en las tres rondas.
- **Comparar contra una corrida nueva del legado después del corte:** el reloj ya avanzó y la salida cambia por eso,
  no por el TO-BE.

## Consecuencias
Las 6 trampas con efecto observable son la prueba de aceptación: cada una queda «vista» o con su renglón.
