# Semana 3 · El corte (borrador para revisión)

- Estado: borrador, sin implementar · Fecha: 2026-11-25 · Decisiones: ADR 0013–0016.
- Mientras corra la medición a ciegas de la ronda 3 (PR abierto) no se toca `paridad/`: S3 vive en `corte/` y en sus
  propios jobs.

## Objetivo
Pasar de «el TO-BE replica al legado» a «el TO-BE puede reemplazarlo un día concreto, con reversa». Se ensaya el corte
completo en el CI: carga histórica por mes, delta del mismo día, cuadre y reversa. Y se cierra la puerta de entrada
que dejó S2: toda salida del legado con consumidor queda comparada, reemplazada con paridad o retirada con dueño.

## Criterios de salida (todos medidos en el CI salvo los marcados «doc»)
1. **Cobertura de salidas:** TODO objeto que existe en el código lleva renglón: 0 sin renglón. Hoy, por código y
   con la ronda 3: 15 procedimientos, 2 vistas, 1 trigger, 1 job, 2 interfaces de entrada y la pantalla.
   - Las estadísticas de ejecución de un ciclo con cierre de mes (Query Store, `dm_exec_*_stats`) clasifican; no
     recortan. «No se vio ejecutar» NO es «no tiene consumidor»: lo no observado queda «sin ejecución observada».
   - Para retirar un objeto hacen falta tres cosas: dueño, fecha y la confirmación del vigía en sólo lectura después
     del corte de que nadie lo llama. Nunca se retira sólo por el silencio de las estadísticas.
2. **Trampas a ciegas como aceptación** (rN-Tk = ronda N, trampa k de `legado/TRAMPAS_CIEGAS*.md`; el catálogo de
   la ronda 3 llega con su PR): las 6 con efecto observable (r1-T2, r2-T1, r2-T3, r3-T1, r3-T2, r3-T3) quedan
   «vista» o con su renglón. Las 2 latentes (r1-T1, r2-T2) se miden con las variantes del plan del piso. La de los
   espacios finales (r1-T3) ya la ve S2.
   - Evidencia de por qué hace falta: la radiografía vio 0 de 9 a ciegas en las tres rondas, y la paridad de
     salidas vio 0 de 3 en la ronda 3 (`radiografia/CONTROL_CIEGO_3.md`, rama de la ronda 3). La ronda 3 sembró
     procedimientos NUEVOS que nada del ciclo ejecuta: no hubo efecto que comparar.
3. **Corte medido por dos caminos:** `MAX(id)` por tabla y sellos (bitácora / fecha de operación). Se exigen
   0 discrepancias entre ambos; si las hay, el corte no avanza.
4. **Carga por mes:** 36 meses (ene-2021 a dic-2023) por sólo INSERT y sólo ids > corte. Cada mes deja su huella
   sha256 por tabla, igual en origen y destino. 0 filas con id ≤ corte en destino tras cada mes.
5. **Reversa probada:** generada ANTES de cada mes. Aplicar y luego revertir deja las 7 tablas, los consumibles y las
   secuencias con la huella previa, en 36 de 36 meses.
6. **Grieta plantada:** detectada 1 de 1 por el cuadre mes a mes y NO por los totales globales (control negativo del
   propio cuadre).
7. **Delta del mismo día tras el congelamiento:**
   - entran las 5 altas de la sucursal 0012 fechadas hacia atrás (ids 412,185–412,189);
   - las 4 órdenes registradas después del congelamiento quedan sin duplicar;
   - 0 choques de folio: los 4 de OP-000150851 a 854 ya los usó el legado, y los consumibles se suben con margen;
   - el pendiente re-registrado el día del corte reaparece con el MISMO documento.
8. **Totales al cierre de TODAS las tablas:** las 7 del legado, catálogos (11 monedas) y consumibles (2 series de
   folio, 5 identidades). Origen = destino y cifras de control por documento firmadas (sha256) antes de cambiar.
9. **Paridad de estado de los procedimientos que escriben:** 6 de 6, corridos sobre el respaldo en una transacción
   revertida, incluidos los «sin ejecución observada» (la contingencia de r3-T3 es uno): es la única forma de ver
   su efecto.
   - r3-T1 aparece como 100,299 diferencias, clasificadas como defecto del legado;
   - r3-T3: `@@IDENTITY` devuelve un id ≠ la fila insertada y se detecta.
10. **Convivencia** (en el CI, con el vecino emulado):
    - las banderas se encienden en orden (marca → conciliar → vencer → avisar al emulador) y la prueba de humo pasa;
    - 3 noches en «sólo marca» contra la última bitácora del legado: 0 noches en que actúen los dos.
11. **Runbook ejecutable** (`ensayo | aplicar | reversa`) corrido completo en el CI sobre una foto con los MISMOS
    índices únicos. El job dura ≤ 15 min (hoy la paridad, 9–12 min).
12. «doc» **Reversa fijada antes y con números:** revierte cualquier diferencia de totales ≠ 0, cualquier mes que no cuadre,
    cualquier documento con cifra distinta o una noche con doble acción. Después del punto de no retorno, sólo hacia
    adelante.

## Piezas: qué corre en el CI y qué sólo se documenta
| Pieza | En el CI | Sólo documentado |
|---|---|---|
| Inventario de salidas y puerta (ADR 0014) | todo objeto del código con renglón; Query Store / `dm_exec_*_stats` del ciclo sólo clasifican («sin ejecución observada»); falla con 1 objeto sin renglón | dueño, fecha y confirmación del vigía de los retirados |
| Oráculo capturado EN el corte (ADR 0014) | salida de cada objeto de lectura con parámetros representativos e instante del servidor; el TO-BE la re-corre con ese reloj inyectado | – |
| Latentes (ADR 0011) | variantes del plan del piso (tal cual, estadísticas + caché vacía, MAXDOP 4); si el legado no coincide consigo mismo, es defecto a decidir | – |
| Paridad de estado (ADR 0015) | transacción revertida, volcado de las tablas afectadas, comparación con el TO-BE; `UPDATE…FROM` 1:N e identidad | – |
| Carga por mes con reversa y `setval` (ADR 0013) | huellas por mes, reversa, restaurar desde la corrida anterior | – |
| Grieta | un mes partido por la fecha UTC en vez de la local: las operaciones de la noche del último día del mes caen en el siguiente; los totales cuadran y el mes no | – |
| Delta del mismo día | por id y por bitácora, no por fecha; incluye el día del corte | camino por pantalla: se mide lo que pierde, no se usa |
| Convivencia (ADR 0016) | jobs con reloj apagados en el legado; noches en «sólo marca»; legado en sólo lectura con vigía; banderas en orden + humo | – |
| Operación del día | – | redirect o DNS, punto de no retorno, ventana con negocio, permisos de quién aplica y quién revierte, comunicación |

Se reusa lo que ya existe: la carga transaccional en bloque (S2) para el ensayo; `radiografia/veredictos.py` para
correr procedimientos en una transacción revertida; el piso de inversiones con plan variado; el legado vivo (delta,
choques preparados) y el emulador del corresponsal.

## Orden de construcción
1. Inventario y puerta en rojo: define el alcance y lista lo que falta.
2. Corte por dos caminos y cifras de control por documento.
3. Carga por mes (INSERT, reversa, `setval`) sobre la foto con índices únicos.
4. Cuadre mes a mes y grieta plantada.
5. Delta del mismo día, numerado DESPUÉS de subir los consumibles.
6. Paridad de estado (escriben) y oráculo del corte (leen): las 6 trampas.
7. Latentes con plan variado: las 2.
8. Runbook en el CI, banderas en orden y humo contra el vecino emulado.
9. Lo que sólo se documenta.

## Si aprieta, se recorta en este orden
- Gemelos de pantalla: a 1 caso.
- Oráculo del corte: a 1 juego de parámetros por objeto, más el borde del cierre de mes.
- Camino por pantalla: sólo la cifra de lo que pierde.
- **No se tocan:** la grieta, la puerta de cobertura, la paridad de estado y la reversa probada. Lo que pasa si
  se recortan ya está medido: radiografía 0 de 9 y paridad de salidas 0 de 3 en la ronda 3.

## Riesgos
- El ciclo vivo de hoy termina el 29-dic. Sin cierre de mes, Query Store no ve los caminos de fin de mes. Se extiende
  el vivo al 31-dic (cierre de mes y de año); si no alcanza, cada objeto no ejecutado queda «sin ejecución
  observada», con su renglón igual.
- SQL dinámico (r3-T2): el reloj vive dentro de una cadena y ningún detector lo ve. Lo atrapa el oráculo del corte
  (instante del servidor contra reloj inyectado). El SQL que se arma fuera del legado sólo aparece en las
  estadísticas: por eso el inventario tiene dos fuentes.
- `GETDATE()` no se puede inyectar en el legado: el oráculo guarda el instante del servidor y el TO-BE replica con
  ese reloj; para los procedimientos que escriben se usa una copia temporal en un esquema aparte, nunca el original.
- Tiempo y memoria del CI: 36 cargas con huella más la paridad de estado. Presupuesto ≤ 15 min, con topes de memoria
  medidos como en S2.
- Objetos de contingencia o de uso raro: casi nunca aparecen en las estadísticas, y si la puerta se alimentara de
  ellas los dejaría fuera. Ya pasó: los 3 procedimientos de la ronda 3 no se ejecutan en el ciclo, y la paridad de
  salidas vio 0 de 3 (la radiografía, 0 de 9 en las tres rondas). Mitigación: renglón para todo lo que está en el
  código y paridad de estado aunque no se haya observado su ejecución.
- La ronda 3 vive en `paridad/` (su PR): S3 no la toca hasta que se fusione.

## Qué se pedirá validar, y a quién
- **Negocio (dueño del proceso):**
  - los números del criterio de reversa;
  - la ventana del corte;
  - qué hacer con los defectos que la paridad de estado mostrará: replicar o corregir r3-T1, el truncado de r2-T3 y el
    desempate del último minuto de r1-T1;
  - dueño y fecha de cada objeto retirado.
- **Operación de la base:**
  - Query Store durante un ciclo con cierre;
  - apagar los jobs con reloj al cortar;
  - el legado en sólo lectura con su vigía.
- **Seguridad e infraestructura:** permisos de `aplicar` y `reversa` (separados), y redirect o DNS.
- **Vecino:** el contrato y la prueba de humo antes de encender el aviso real.
- **Revisión del plan:** coordinación y luego la revisión externa de la retro.
