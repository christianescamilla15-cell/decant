# Semana 3 · El corte (plan)

- Estado: revisado (25-nov), sin implementar · Fecha: 2026-11-25 · Decisiones: ADR 0013–0016.
- S3 vive en `corte/` y en sus propios jobs; `paridad/` (S2, ya medida a ciegas en la ronda 3) no se toca.

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
   - La puerta también cuenta CONSUMIDORES, no sólo objetos: un lector externo que hace SELECT directo a tablas o
     vistas no aparece como objeto. Se inventarían los logins y aplicaciones conectados durante el ciclo, con 0 logins
     sin renglón. Después del corte, el vigía cuenta conexiones y lecturas, no sólo EXEC.
2. **Trampas a ciegas como aceptación** (rN-Tk = ronda N, trampa k de `legado/TRAMPAS_CIEGAS*.md`): las 6 con
   efecto observable (r1-T2, r2-T1, r2-T3, r3-T1, r3-T2, r3-T3) quedan DETECTADAS 6 de 6 por una comparación que falla nombrándola. Tener renglón no basta, porque el criterio 1 ya le
   da renglón a todo. Las 2 latentes (r1-T1, r2-T2) se miden con las variantes del plan del piso. La de los
   espacios finales (r1-T3) ya la ve S2.
   - Evidencia de por qué hace falta: la radiografía vio 0 de 9 a ciegas en las tres rondas, y la paridad de
     salidas vio 0 de 3 en la ronda 3 (`radiografia/CONTROL_CIEGO_3.md`). La ronda 3 sembró
     procedimientos NUEVOS que nada del ciclo ejecuta: no hubo efecto que comparar.
3. **Corte medido por dos caminos:** `MAX(id)` por tabla y sellos (bitácora / fecha de operación). «Discrepancia» es
   diferencia de CONJUNTOS: se exigen 0 ids > corte presentes en un camino y ausentes en el otro. Los huecos de
   identidad hacen que `MAX(id)` y los sellos difieran sin que haya error. Si hay discrepancias, el corte no avanza.
4. **Carga por mes:** 36 meses (ene-2021 a dic-2023) por sólo INSERT y sólo ids > corte. Cada mes deja su huella
   sha256 por tabla, igual en origen y destino. 0 filas con id ≤ corte en destino tras cada mes.
   - En el PR corren 3 meses: el primero, el de la grieta y el último. Los 36 de 36 corren en un job nocturno.
5. **Reversa probada:** generada ANTES de cada mes. Aplicar y luego revertir deja las 7 tablas, los consumibles y las
   secuencias con la huella previa, en 36 de 36 meses.
   - Para saber qué ya trabajó el TO-BE, la reversa lee la bitácora de ACCIONES de negocio, no el token de
     concurrencia ni la fecha de modificación: una marca automática del TO-BE no hace pasar una fila por trabajada.
     Control negativo: una escritura informativa del sistema sobre una fila cargada no la saca de la reversa.
   - Guarda: `aplicar` se niega si hay automatismos del TO-BE encendidos.
   - Control negativo: una reversa plantada que no restaura el `setval` falla, y es la huella la que la ve.
6. **Grieta plantada:** detectada 1 de 1 por el cuadre mes a mes y NO por los totales globales (control negativo del
   propio cuadre).
7. **Delta del mismo día tras el congelamiento:**
   - entran las 5 altas de la sucursal 0012 fechadas hacia atrás (ids 412,185–412,189);
   - las 4 órdenes registradas después del congelamiento quedan sin duplicar;
   - 0 choques de folio: los 4 de OP-000150851 a 854 ya los usó el legado, y los consumibles se suben con margen;
   - el pendiente re-registrado el día del corte trae un id NUEVO: reaparece con el MISMO documento y el registro
     viejo SALE. Se concilia por llave de negocio (documento + sucursal), no por id: 0 duplicados por documento;
   - lo derivado por id (correcciones o enriquecimientos aplicados después de cargar) se RE-ARMA tras cada carga;
     no se reusa.
8. **Totales al cierre de TODAS las tablas:** las 7 del legado, catálogos (11 monedas) y consumibles (2 series de
   folio, 5 identidades). Origen = destino. Antes de cambiar, el job deja la huella sha256 por documento como
   artefacto inmutable, con retención, y su sha queda en el commit del corte. Es una huella, no una firma
   personal: la deja el job, y quien aprueba el corte la cita.
   - Las cifras van por documento + estado + mes, no sólo en totales: los totales globales no detectan los
     desplazamientos.
   - Lo que «no viaja» se cuenta por motivo (pendiente, sin detalle, duplicado, dato sucio) y la suma cuadra con el
     origen: cargado + no viaja = origen.
9. **Paridad de estado de los que escriben:** N de N, con los escritores sacados del inventario (procedimientos,
   triggers y pasos de jobs), no una cifra fija. Corren sobre el respaldo en una transacción revertida, incluidos los
   «sin ejecución observada» (la contingencia de r3-T3 es uno): es la única forma de ver su efecto.
   - El arnés falla si `@@TRANCOUNT` cambia: un procedimiento con su propio ROLLBACK se lleva la transacción externa
     y el volcado saldría vacío. Hoy ninguno lo trae, pero el arnés no lo da por hecho.
   - Los efectos fuera de la base (correo, arranque de jobs, servidores enlazados, archivos) no se revierten: se
     declaran por objeto y se neutralizan o emulan durante la corrida.
   - r3-T1 aparece como 100,299 diferencias, clasificadas como defecto del legado;
   - r3-T3: `@@IDENTITY` devuelve un id ≠ la fila insertada y se detecta.
10. **Convivencia** (en el CI, con el vecino emulado):
    - las banderas se encienden en orden (marca → conciliar → vencer → avisar al emulador) y la prueba de humo pasa;
    - 3 noches en «sólo marca» contra la última bitácora del legado: 0 noches en que actúen los dos, y 0 diferencias
      entre lo que el TO-BE marca y la bitácora del legado en 3 de 3 noches. Si no actuara, sólo cumpliría la
      primera mitad.
11. **Runbook ejecutable** (`ensayo | aplicar | reversa`) corrido completo en el CI sobre una foto con los MISMOS
    índices únicos. El job del PR dura ≤ 15 min (hoy la paridad, 9–12 min). Eso es el CI, no el corte: a volumen
    real, el corte medido dura ≤ 50 % de la ventana acordada, y el resto es margen para la reversa. Antes del día:
    - la configuración de ensayo contra la de producción da 0 llaves sin explicar;
    - todo queda PRECARGADO con los interruptores apagados: el día del corte sólo se enciende;
    - hay una sonda de punta a punta por cada salto (una llamada firmada contra el vecino emulado), porque los
      permisos entre sistemas sólo fallan así.
12. «doc» **Reversa fijada antes y con números:** revierte cualquier diferencia de totales ≠ 0, cualquier mes que no cuadre,
    cualquier documento con cifra distinta o una noche con doble acción. El **punto de no retorno es un evento
    medible**: la primera escritura de negocio aceptada en el TO-BE o el primer aviso al exterior. Lo registra el
    sistema, y desde ahí `reversa` se NIEGA, porque volver a la huella previa borraría lo capturado; el control
    negativo se prueba en el CI. Después de ese punto, sólo hacia adelante.

## Piezas: qué corre en el CI y qué sólo se documenta
| Pieza | En el CI | Sólo documentado |
|---|---|---|
| Inventario de salidas y puerta (ADR 0014) | todo objeto del código y todo login conectado en el ciclo con renglón; Query Store / `dm_exec_*_stats` del ciclo sólo clasifican («sin ejecución observada»); falla con 1 objeto o 1 login sin renglón | dueño, fecha y confirmación del vigía de los retirados |
| Oráculo capturado EN el corte (ADR 0014) | salida de cada objeto de lectura con parámetros representativos e instante del servidor; el TO-BE la re-corre con ese reloj inyectado | – |
| Latentes (ADR 0011) | variantes del plan del piso (tal cual, estadísticas + caché vacía, MAXDOP 4); si el legado no coincide consigo mismo, es defecto a decidir | – |
| Paridad de estado (ADR 0015) | transacción revertida con guarda de `@@TRANCOUNT`, volcado de las tablas afectadas, comparación con el TO-BE; `UPDATE…FROM` 1:N e identidad; N de N escritores del inventario | efectos fuera de la base declarados por objeto |
| Carga por mes con reversa y `setval` (ADR 0013) | 3 meses en el PR y 36 cada noche: huellas, reversa (con su control negativo), restaurar desde la corrida anterior | – |
| Grieta | un mes partido por la fecha UTC en vez de la local: las operaciones de la noche del último día del mes caen en el siguiente; los totales cuadran y el mes no | – |
| Delta del mismo día | por id y por bitácora, no por fecha; incluye el día del corte | camino por pantalla: se mide lo que pierde, no se usa |
| Convivencia (ADR 0016) | jobs con reloj apagados en el legado; noches en «sólo marca»; legado en sólo lectura con vigía de conexiones y lecturas; banderas en orden + humo; `reversa` negada después del punto de no retorno | – |
| Operación del día | la guarda de automatismos; temporizadores persistentes, que sobreviven a un reinicio; candados entre procesos por identificador, no por texto | redirect o DNS, punto de no retorno, ventana con negocio (sin lunes ni viernes), sesiones y credenciales que duren toda la ventana, permisos de quién aplica y quién revierte, comunicación |

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
- Tiempo y memoria del CI: 36 cargas con aplicar + reversa + huella, más la paridad de estado, no caben en 15 min.
  En el PR van 3 meses y los 36 en el job nocturno, con topes de memoria medidos como en S2.
- Objetos de contingencia o de uso raro: casi nunca aparecen en las estadísticas, y si la puerta se alimentara de
  ellas los dejaría fuera. Ya pasó: los 3 procedimientos de la ronda 3 no se ejecutan en el ciclo, y la paridad de
  salidas vio 0 de 3 (la radiografía, 0 de 9 en las tres rondas). Mitigación: renglón para todo lo que está en el
  código y paridad de estado aunque no se haya observado su ejecución.
- Lo que en un corte real salió caro (revisión del 25-nov), en orden:
  - los candados o avisos entre procesos que casan por TEXTO: uno mal redactado deja el recurso «tomado» un día;
  - configuración de producción distinta de la del ensayo;
  - dependencias entre sistemas que sólo fallan con una llamada firmada de punta a punta;
  - pendientes del legado que nadie va a terminar.
  El plan responde con el criterio 11, la fila «Operación del día» y una decisión de negocio.

## Qué se pedirá validar, y a quién
- **Negocio (dueño del proceso):**
  - los números del criterio de reversa;
  - la ventana del corte;
  - qué hacer con los defectos que la paridad de estado mostrará: replicar o corregir r3-T1, el truncado de r2-T3 y el
    desempate del último minuto de r1-T1;
  - dueño y fecha de cada objeto retirado;
  - quién procesa en el TO-BE los pendientes que el legado ya no va a terminar.
- **Operación de la base:**
  - Query Store durante un ciclo con cierre;
  - apagar los jobs con reloj al cortar;
  - el legado en sólo lectura con su vigía.
- **Seguridad e infraestructura:** permisos de `aplicar` y `reversa` (separados), y redirect o DNS.
- **Vecino:** el contrato y la prueba de humo antes de encender el aviso real.
- **Revisión del plan:** hecha el 25-nov por dos revisiones externas (quien pidió la retro de S2 y un equipo con
  un corte real reciente); sus observaciones ya están integradas.
