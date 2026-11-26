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
- **La puerta:** 0 objetos del código sin renglón y 0 CONSUMIDORES sin renglón. Los consumidores son los logins y
  aplicaciones conectados durante el ciclo: un lector que hace SELECT directo no es un objeto y se escaparía. Es un
  check del CI que falla nombrando el objeto o el login.
- **Oráculo capturado EN el corte:** la salida de cada objeto de lectura con parámetros representativos (incluido el
  borde de fin de mes) y el instante del servidor al correrla. El TO-BE las re-corre con ese reloj inyectado.
- **Lo latente** se mide con las variantes del plan del piso (ADR 0011). Si el legado no coincide consigo mismo, es
  un defecto a decidir, no un contrato.

## Al construir el oráculo (26-nov, paso 5)
Lo que el código decidió y la propuesta no decía (`corte/oraculo.py`, `corte/estado_ci.py`, `legado/vivo`):
- **Se captura dentro del legado vivo, en el congelamiento**: después de la foto del paso 2 y antes de lo que el
  legado sigue escribiendo, cuando lo pide `DECANT_ORACULO=1`. Sólo lo enciende el job del corte: el job que observa
  el ciclo para la puerta no, porque lo que ejecuta el arnés no es un consumidor y cambiaría la clasificación de los
  «sin ejecución observada».
- **Casos:** cada objeto de lectura del inventario (9 procedimientos, 2 vistas y la pantalla) con parámetros que salen
  de los datos en el congelamiento: una operación re-registrada, una sin orden, la más reciente, el corresponsal con
  más órdenes enviadas, el día del corte y su mes y el mes anterior. 21 casos, 7 en el borde del cierre de mes. Cada
  uno guarda el instante del servidor justo antes de correr. N de N: un objeto de lectura sin caso hace fallar el
  oráculo.
- **El TO-BE re-corre sobre la base cerrada con el delta del paso 4** (el estado del congelamiento), con el reloj del
  oráculo inyectado. Los conjuntos se comparan como multiconjuntos: los empates y el orden que no es contrato no
  cuentan. Los números van por valor, porque la escala de un ROUND es la de cada motor.
- **Tres comparaciones más, que son las que ven las trampas:**
  - **el orden prometido**, del objeto o de la vista que lee, se cuenta en los dos lados. Un legado que incumple lo que
    promete es defecto del legado (r2-T1);
  - **el reloj propio**: el TO-BE corre también con su reloj (el de negocio del congelamiento). Si así no coincide, el
    objeto depende del reloj y un TO-BE que no lo inyecte falla, nombrado (r1-T2; r3-T2, con el reloj dentro de una
    cadena que ningún detector ve);
  - **el SQL copiado tal cual**, donde los motores calculan distinto el mismo texto: si difiere, el TO-BE tiene que
    replicar al legado mientras negocio no decida (r2-T3).
- **El TOP sin ORDER BY** (T1 del catálogo original) de la lista del día se arbitra: el legado puede entregar otro
  subconjunto del día, del tamaño del TOP. Se audita que lo sea; si no, es defecto nuestro.

**Medido en el PR** (corrida 45898183988): 12 de 12 objetos de lectura y 21 casos, capturados en 1.9 s con el
reloj del servidor en 2026-11-26 15:29 (el del runner); el reloj propio del TO-BE, 2023-12-29 18:00. Con el reloj del
oráculo coinciden los 21 (uno por el árbitro del TOP: la lista del 30-nov). Las trampas:
- r1-T2: 108 órdenes por vencer; sin inyectar el reloj, 8;
- r3-T2: 108 órdenes con antigüedad (79 de un corresponsal); sin inyectar el reloj, 0;
- r2-T1: el legado entrega al revés 2,371 de 4,603 pares contiguos desde el 1-dic (88 de 161 desde el día del
  corte), por el procedimiento y leyendo la vista; el TO-BE, 0;
- r2-T3: el SQL copiado tal cual difiere en las horas de los 8 corresponsales, en los dos meses; con el truncado
  replicado, coincide.
Las latentes (r1-T1, r2-T2) coinciden hoy: son del paso siguiente, con el plan variado.

## Alternativas descartadas
- **Sólo el código:** no ve consumidores externos ni el SQL que se arma afuera.
- **Sólo las estadísticas (o que ellas recorten el inventario):** no ven los caminos que el ciclo no ejecutó
  (fin de mes, contingencia). Medido: los 3 procedimientos de la ronda 3 no se ejecutan en el ciclo y la paridad de
  salidas vio 0 de 3; la radiografía, 0 de 9 a ciegas en las tres rondas.
- **Comparar contra una corrida nueva del legado después del corte:** el reloj ya avanzó y la salida cambia por eso,
  no por el TO-BE.
- **Capturar el oráculo en el job que observa el ciclo:** sus ejecuciones contarían como consumo observado y la puerta
  dejaría de ver «sin ejecución observada» los objetos que sólo el arnés corre.
- **Comparar el orden tal como lo entrega el legado:** castigaría al TO-BE que ordena bien (r2-T1). El orden que
  cuenta es el que el código promete.

## Consecuencias
Las 6 trampas con efecto observable son la prueba de aceptación: cada una queda «vista» o con su renglón.
