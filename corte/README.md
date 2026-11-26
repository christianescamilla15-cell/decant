# corte/ · semana 3

El corte del legado al TO-BE (plan: [`docs/s3/PLAN.md`](../docs/s3/PLAN.md)). Hoy trae:
- el paso 1: el inventario de salidas y consumidores del legado y su **puerta** (ADR 0014, criterio 1). La vista
  legible está en [`inventario/INVENTARIO.md`](inventario/INVENTARIO.md);
- el paso 2: el **corte medido por dos caminos** y las **cifras de control por documento** (ADR 0013 y 0016,
  criterios 3, 7 y 8). La vista legible está en [`cifras/CIFRAS.md`](cifras/CIFRAS.md);
- el paso 3: la **carga histórica por mes** con sólo INSERT, la reversa generada antes y el `setval` al cierre
  (ADR 0013 y 0016, criterios 4, 5, 6 y 12), con su runbook `ensayo | aplicar | reversa`;
- el paso 4: el **delta del mismo día** sobre la base cerrada, restaurada del volcado de la nocturna, con la reversa
  de sus UPDATE con los valores previos y sus 6 controles negativos (ADR 0013 y 0016, criterios 5, 7, 8 y 12);
- el paso 5: la **paridad de estado** de los escritores del inventario, corridos sobre el respaldo en transacciones
  revertidas y comparados con el TO-BE por llave de negocio, y el **oráculo del corte** para los que leen, capturado
  en el congelamiento y re-corrido por el TO-BE con el reloj del servidor inyectado (ADR 0014 y 0015, criterios 2 y 9).

## Qué hay

| Archivo | Qué hace |
|---|---|
| `sql.py` | Parser determinista del T-SQL de `legado/sql/` (sobre el léxico de la radiografía): qué crea cada script y, de cada módulo o paso de job, qué lee, qué escribe, a quién llama, efectos fuera de la base, reloj, SQL dinámico (también el texto que corre `sp_executesql`), `@@IDENTITY` y transacciones. |
| `fuentes.py` | La pantalla (sus cadenas de SQL) y las interfaces de entrada, leídas con `ast`. |
| `codigo.py` | El inventario desde el código, con el cierre de lo que llama cada objeto y de los triggers que disparan sus escrituras. Escritores = procedimientos, triggers y pasos de job. |
| `observar.py` | En el CI, mientras corre `./ciclo.sh`: sesiones (logins y aplicaciones), peticiones en curso, `dm_exec_*_stats` y lo ad hoc; al cerrar, Query Store, historial del job, catálogo del servidor y usuarios de la bitácora. Sólo lee. |
| `cruce.py` | Código × observación: `observada`, `observada_por_quien_la_usa` (vistas) o `sin_ejecucion_observada`. Clasifica; nunca recorta. |
| `renglones.py`, `puerta.py` | Los renglones y la puerta. |
| `vista.py`, `escribir.py` | `INVENTARIO.md` y la regeneración de lo versionado. |
| `caminos.py` | Paso 2, sin base: los caminos por sellos de cada tabla (consultas literales), sus límites desde las fotos del vivo, la diferencia de conjuntos contra la identidad, los huecos y la cobertura contra las tablas del inventario. |
| `cifras.py` | Paso 2, sin base: la forma canónica y la huella sha256 de cada documento, su destino (cargado o no viaja por motivo), los agregados por tipo + estado + mes, el cuadre, la reconstrucción del estatus con la bitácora y la conciliación por llave de negocio. |
| `medir.py` | En el CI, sobre el legado vivo que deja `./ciclo.sh`: lee la base (sólo lee), mide los dos caminos, arma los documentos al congelamiento y corre los controles negativos sobre los documentos reales. |
| `carga.py` | Paso 3, sin base: las 7 tablas (tipos del legado), las consultas literales al origen, el plan por mes (rangos contiguos de ids por el sello de cada fila), la huella del mes, las guardas (sólo ids > corte) y la reversa. |
| `destino.sql` | Paso 3: el esquema `legado` de PostgreSQL (valores CRUDOS, los mismos índices únicos, sin llaves foráneas hasta el cierre) y el esquema `corte` (registro de meses y ensayos, interruptores, acciones de negocio, avisos y punto de no retorno, y los dos roles). |
| `runbook.py` | Paso 3: `python -m corte.runbook preparar\|ensayo\|aplicar\|reversa\|cierre\|estado --mes AAAA-MM`. |
| `carga_ci.py` | Paso 3, en el CI (`.github/workflows/carga.yml`): restaura el respaldo, corre los meses y los controles negativos y deja `carga.json`; de noche, con `--volcar`, vuelca la base cerrada. |
| `delta.py` | Paso 4, sin base: qué entra (por id), los cambios sobre filas del corte desde la bitácora y su comprobación fila por fila, el catálogo del congelamiento, los choques de folio, la reversa con los valores previos, las cifras contra las del paso 2 y el gancho de lo derivado por id. |
| `delta.sql` | Paso 4: el registro del delta y sus ensayos (a lo más un delta aplicado) y sus dos roles: aplicar (INSERT y UPDATE acotado) y reversa (DELETE y UPDATE acotado). |
| `runbook_delta.py` | Paso 4: `python -m corte.runbook_delta preparar\|ensayo\|aplicar\|reversa\|cifras\|estado`. |
| `base.py` | Paso 4: la base cerrada como `pg_dump`: volcar, restaurar, verificar sin creerle o, si no hay volcado, construir. |
| `delta_ci.py` | Paso 4, en el CI: la base (restaurada o construida), el delta con sus 6 controles negativos y las cifras contra el paso 2; deja `delta.json`. |
| `estado.py` | Paso 5, sin base: los escenarios con las llamadas reales del guion, la copia temporal del legado (esquema `estado` del respaldo, con el reloj inyectado), la guarda de `@@TRANCOUNT`, el efecto de cada etapa por llave de negocio, sus árbitros (UPDATE … FROM 1:N, `@@IDENTITY`) y el N de N de los escritores del inventario. |
| `estado_tobe.sql` | Paso 5: el efecto del TO-BE sobre la base de referencia (las reglas R01–R12 sobre el esquema `legado`, con sus parches: el reloj entra, la orden vigente, `RETURNING id`). Se crea dentro de cada transacción revertida. |
| `oraculo.py` | Paso 5: los casos del oráculo (cada objeto de lectura, con parámetros representativos y el borde del cierre de mes), su captura en el congelamiento y la re-corrida del TO-BE con el reloj inyectado, con su reloj propio y, donde los motores calculan distinto, con el SQL copiado tal cual. |
| `trampas.py` | Paso 5: los catálogos sellados de las trampas a ciegas, para NOMBRAR lo que falla. La detección no los lee. |
| `estado_ci.py` | Paso 5, en el CI (job `estado` de `carga.yml`): el respaldo, la base cerrada y su copia con el delta del paso 4, la copia temporal verificada, los escenarios en los dos lados, los controles negativos, el oráculo y la aceptación de las trampas; deja `estado.json`. |
| `veredicto.py`, `vista_cifras.py` | Sin base: re-verifica la medición (recuenta desde el CSV documento por documento), compara con lo versionado, comprueba el digest de los artefactos publicados y versiona una corrida en `cifras/` con su `CIFRAS.md`. |

`inventario/`: `objetos.json` (sale del código), `observado.json` (artefacto de una corrida del CI, versionado con su
número de corrida), `renglones.yml` (a mano) e `INVENTARIO.md` (vista).

`cifras/`: `corte.json` y `cifras-de-control.json` de una corrida del CI, `huella.json` (el sha256 de las cifras y del
CSV de huellas por documento, con el id y el digest de sus artefactos) y `CIFRAS.md` (vista). El CSV (≈ 560 mil
documentos) no se versiona: vive en el artefacto, y su sha256 en `huella.json`.

## Uso

```bash
python -m corte.puerta                     # código de hoy + observación versionada + renglones; sale con 1 en rojo
python -m corte.escribir                   # regenera objetos.json e INVENTARIO.md (--verificar sólo compara)
python -m corte.medir --salida corte/medido-ci     # con el legado vivo arriba (después de ./ciclo.sh)
python -m corte.veredicto corte/medido-ci          # sin base: re-verifica y compara con corte/cifras/huella.json
python -m corte.veredicto <artefacto corte-medido> --versionar --artefactos artefactos.json   # a corte/cifras/
# paso 3: con el respaldo restaurado como BFN_DIVISAS_CORTE y PostgreSQL arriba (DECANT_PG_PASSWORD, DECANT_PG_PUERTO)
python -m corte.runbook preparar [--recrear]
python -m corte.runbook ensayo  --mes 2021-01
python -m corte.runbook aplicar --mes 2021-01
python -m corte.runbook reversa --mes 2021-01
python -m corte.runbook cierre                     # con los 36 meses aplicados
python -m corte.carga_ci --meses pr --salida corte/carga-ci        # lo del CI: restaura, carga y controles
# paso 4: con el legado vivo (después de ./ciclo.sh) y la base cerrada en decant_corte
python -m corte.runbook_delta preparar
python -m corte.runbook_delta ensayo
python -m corte.runbook_delta aplicar
python -m corte.runbook_delta reversa
python -m corte.runbook_delta cifras               # el destino contra las cifras versionadas del paso 2
python -m corte.delta_ci --base corte/base --salida corte/delta-ci   # lo del CI (--construir-base sin volcado)
# paso 5: el ciclo con el oráculo capturado en el congelamiento, y luego la paridad de estado y el oráculo
DECANT_ORACULO=1 ./ciclo.sh
python -m corte.estado_ci --base corte/base --salida corte/estado-ci   # lo del CI (--construir-base sin volcado)
```

En el CI, el job `legado` deja el artefacto `ejecucion-observada` y el job `puerta` (aparte y fuera del ruleset) lo
juzga y publica los conteos por destino en su resumen. Para actualizar la observación versionada, se copia ese
artefacto a `inventario/observado.json` y se corre `python -m corte.escribir`.

Paso 2, con el mismo patrón: el job `legado`, al cerrar el ciclo y antes de las pruebas de integración, corre
`corte.medir` y deja el artefacto `corte-medido`. El job `corte` (aparte y fuera del ruleset) lo re-verifica sin base y
publica `cifras-de-control.json` y `huellas-por-documento.csv` como artefactos inmutables con 90 días de retención,
SIN comprimir (`archive: false`): el digest que GitHub calcula al publicarlos es el sha256 del archivo, y el job lo
comprueba y lo deja en su resumen. Para versionar una corrida:
`gh api repos/<dueño>/decant/actions/runs/<id>/artifacts > artefactos.json`, se descarga `corte-medido` y se corre
`python -m corte.veredicto <carpeta> --versionar --artefactos artefactos.json`.

## Reglas

- El código decide qué entra; lo observado sólo clasifica. Lo que el servidor tiene o ejecuta y el código no, también
  necesita renglón.
- Cada objeto y cada login lleva renglón: `comparado` o `reemplazado_con_paridad` (con evidencia `archivo::prueba` que
  exista), `retirado` (dueño, fecha y confirmación del vigía después del corte) o `pendiente`.
- «Sin ejecución observada» nunca pasa a retirado solo.

### El corte por dos caminos (paso 2)

- **Por identidad:** `MAX(id)` de cada tabla en la foto del respaldo (el corte) y en la del congelamiento.
- **Por sellos:** cada tabla con identidad declara en `caminos.py` cómo sabe cuándo se escribió una fila sin mirar su
  id: la bitácora (reloj del servidor, y por ella sus partidas), `fecha_registro` (hora de negocio de la interfaz) o el
  folio FX (el consumible de la operación). Los límites salen de las fotos del legado vivo, que desde el paso 2 anotan
  también el instante del servidor y esperan a que avance.
- La discrepancia es diferencia de CONJUNTOS: 0 ids mayores al corte en un camino y no en el otro, y lo mismo del lado
  del congelamiento. Un hueco de identidad (inserción revertida) no cuenta; dos errores opuestos no se cancelan.
- Las tablas salen del inventario del código: una tabla con identidad sin camino, o un camino huérfano, detiene el
  corte. El camino por `fecha_operacion` es el control negativo: pierde las altas fechadas hacia atrás y la comparación
  falla nombrándolas.

### Las cifras de control (paso 2)

- **Documento** = orden de pago por `(uetr, sucursal)` u operación por `(folio FX, sucursal)`. Los re-registros son la
  historia del documento, no otros documentos.
- Huella sha256 por documento sobre su forma canónica, sin ids; agregada por tipo + estado + mes (local). Destino:
  `cargado` o no viaja por motivo (`pendiente`, `sin_detalle`, `duplicado`, `dato_sucio`), con cargado + no viaja =
  origen por tipo y por grupo. El estado es el del congelamiento: el estatus de las órdenes se reconstruye deshaciendo
  con la bitácora lo posterior.
- Duplicados por documento = 0. El delta se concilia por llave de negocio; por id (control negativo) cada re-registro
  del día de un documento del corte queda dos veces.
- Controles negativos sobre los documentos REALES: un centavo (cambia su huella y la de su mes), la grieta UTC (cuadra
  en totales globales y no por mes) y un duplicado (falla nombrándolo).
- Las cifras y el CSV no dependen del reloj de la corrida: el job `corte` exige los sha256 versionados.

### La carga histórica por mes (paso 3)

- **Origen:** el respaldo FECHADO restaurado como `BFN_DIVISAS_CORTE` (sha256 contra su manifiesto y VERIFYONLY). El
  corte de cada tabla es el `MAX(id)` del manifiesto y tiene que ser el medido por dos caminos en el paso 2
  (`cifras/corte.json`); si no, el runbook se niega.
- **Destino:** el esquema `legado` de PostgreSQL con las 7 tablas fila por fila, CON sus ids y sus valores CRUDOS
  (`char(n)` con su relleno, los centinelas tal cual, la hora local sin zona, cada decimal con su escala). Los parches
  del ADR 0007 se aplican de `legado` al TO-BE, como ya los aplica y mide S2; aquí la huella del mes tiene que ser
  igual en los dos lados.
- **Plan:** el mes de cada fila es el de su SELLO en hora local (`fecha_operacion`, `fecha_registro`, la bitácora
  «→ LIQUIDADA» de su orden, `fecha_hora`, `fecha`). Por tabla y mes, `MIN(id)`, `MAX(id)` y filas en el origen;
  cada mes es el rango `(fin del anterior, MAX(id)]` y el plan exige que no se enciman y que los meses sumen el
  origen hasta el corte. Su sha256 ata el ensayo con lo que se aplica.
- **Sólo INSERT y sólo ids > corte:** el corte de un mes es lo que el destino ya tiene, por dos caminos (`MAX(id)` y
  el registro de meses aplicados). Un mes que empieza antes, o un lote con un id ≤ corte, se niega; `aplicar` corre
  con un rol que sólo puede insertar (y `reversa`, con uno que sólo puede borrar).
- **Huella del mes:** por tabla, `cifras.huella` de cada fila; en el origen se toman por su sello (el mes de verdad) y
  en el destino por el rango del plan. `aplicar` confirma sólo si son iguales, si las filas con id ≤ corte siguen
  idénticas y si no quedó nada después del mes.
- **Reversa:** se guarda ANTES de insertar (en `corte.carga_mes` y en `reversa_AAAA-MM.json`): los rangos, el valor
  previo de cada secuencia y de cada folio, y la huella previa (las 7 tablas, las secuencias y los consumibles). Sólo
  revierte el último mes aplicado y confirma sólo si el destino vuelve a esa huella.
- **Lo que ya trabajó el TO-BE** lo dice la bitácora de ACCIONES de negocio (`corte.accion_negocio`), nunca el token
  de concurrencia: la primera acción o el primer aviso al exterior (`corte.aviso_exterior`) registran, por disparador,
  el punto de no retorno (`corte.no_retorno`), y desde ahí `reversa` se niega. `aplicar` se niega con un interruptor
  de `corte.interruptor` encendido (son las banderas del TO-BE, precargadas apagadas).
- **Ensayo:** el mismo `aplicar` en una transacción que se revierte, sobre el mismo destino (los mismos índices únicos,
  comparados contra el catálogo del origen). `aplicar` exige un ensayo verde del mismo mes y plan sobre la misma
  huella previa: un choque en el ensayo detiene el corte.
- **Cierre:** con los 36 meses aplicados, `setval` desde `IDENT_CURRENT` del origen (no desde `MAX(id)`), los folios
  con margen por encima de lo que el legado vivo ya usó, las llaves foráneas validadas y los totales globales.
- `setval` no es transaccional en PostgreSQL: cuando una transacción se revierte (el ensayo, o una verificación que no
  cuadra), el runbook regresa las secuencias a mano; si no, la huella lo ve.

### El delta del mismo día (paso 4)

- **Base:** la cerrada. La nocturna la vuelca (`pg_dump -Fc` desde el contenedor, artefacto `destino-cerrado`) y el
  delta la restaura en una base limpia: la segunda línea de defensa del ADR 0013, probada cada noche y en cada PR. A la
  foto no se le cree:
  - sha256 del volcado;
  - huella al restaurar;
  - el plan de esta corrida;
  - los 36 meses aplicados con ese plan;
  - las llaves foráneas del cierre;
  - los totales del origen hasta el corte;
  - sin punto de no retorno ni automatismos encendidos.
- **Qué entra, por id:** `(corte, congelamiento]` en las 5 tablas con identidad, los dos medidos en el paso 2. La
  selección se compara con la identidad y lo que falta se nombra.
- **Filas del corte que cambian:** las dice la bitácora y se comprueban contra el origen al congelamiento, fila por fila:
  - REEMPLAZADA por re-registro y LIQUIDADA; si el job concilia, también `horas_liquidacion`;
  - las distintas son exactamente las anotadas y sólo en las columnas mutables.
  Lo anotado después del congelamiento queda para el barrido.
- **`aplicar`** exige un ensayo verde del mismo plan sobre la misma huella y se niega con un automatismo encendido o si
  el delta ya está aplicado. Escribe con su rol (INSERT y UPDATE acotado) y guarda la reversa antes. Confirma sólo si:
  - cada lote es igual en origen y destino;
  - las filas actualizadas quedan como el origen;
  - el resto del corte sigue idéntico;
  - no hay nada después del congelamiento;
  - el catálogo es el de la foto;
  - hay 0 duplicados por documento y 0 choques de folio.
- **Reversa:** borra los rangos, devuelve los valores previos (de la orden y del catálogo), las secuencias y los folios,
  y confirma sólo si vuelve a la huella previa. Desde el punto de no retorno se niega.
- **Cifras de control:** los documentos del destino, con la forma canónica del paso 2, contra las cifras VERSIONADAS
  (su sha256 es el de `cifras/huella.json`). Por tipo y por grupo tipo + estado + mes, destino = cargado del paso 2 y
  destino + no viaja = origen.

### La paridad de estado y el oráculo del corte (paso 5)

- **Escritores:** los del inventario del CÓDIGO (`corte.codigo`), no una lista fija: hoy 8 (6 procedimientos, el
  disparador y el paso del job). Cada uno tiene su etapa (o corre dentro de otra: el disparador en cada escritura de
  la orden y `sp_conciliar` en el paso del job) y el SERVIDOR tiene que verlo correr (`sys.dm_exec_procedure_stats` y
  `sys.dm_exec_trigger_stats` de la copia). Uno nuevo sin escenario, o uno que no corre, hace fallar el N de N
  nombrándolo.
- **La copia temporal:** en el esquema `estado` del respaldo restaurado (`BFN_DIVISAS_CORTE`), nunca en el original:
  - las 7 tablas con el DDL del código (sus índices, llaves primarias y foráneas) y los datos del respaldo con sus
    ids. Se exige el mismo catálogo que el original, 0 diferencias de datos y la identidad en el mismo valor;
  - el disparador y los escritores con el código del RESPALDO (que tiene que ser el del repositorio), transformados por
    fichas: `dbo.<objeto>` → `estado.<objeto>` y `GETDATE()` → el reloj de `SESSION_CONTEXT`. El servidor confirma que
    ningún objeto de la copia depende de `dbo` y que el disparador vive en `estado.orden_pago`;
  - un reloj que no se puede inyectar con un solo valor (UTC, con zona), un servidor enlazado, un nombre de tres partes
    o SQL dinámico en un escritor detienen la copia en vez de cambiar lo que el original hace.
- **Efectos fuera de la base:** se declaran por objeto desde el inventario (`estado.efectos_declarados`). Los de un
  procedimiento del sistema (correo, arranque de jobs, archivos) se EMULAN: la copia llama a `estado.emulado_<nombre>`,
  que sólo anota la llamada. Servidor enlazado, otra base, SSIS: la corrida se niega. Hoy ningún escritor tiene; el
  paso del job corre como su comando T-SQL (de msdb) con el Agent apagado, nunca con `sp_start_job`.
- **Escenarios** (`estado.ESCENARIOS`), cada uno en UNA transacción revertida (`radiografia.veredictos.revertida`), con
  las identidades regresadas a mano al salir (no son transaccionales):
  - A, el día del corte y su noche: el catálogo del guion, las operaciones, las órdenes y las liquidaciones de la fase
    anterior al congelamiento, cada llamada con su instante; el paso del job a las 23:30 de la noche del corte. El día
    va por escritor: ninguna liquidación del guion precede al registro de su orden y ningún re-registro sigue a una
    liquidación del mismo documento (una prueba lo verifica sobre el guion);
  - B, la mesa (`sp_reflejar_estatus_operacion`, sin ejecución observada) sobre el respaldo;
  - C, la contingencia (`sp_alta_manual_orden`, sin ejecución observada): la primera orden nueva del día, con su
    operación, dada de alta a mano con los argumentos de sus llamadas reales.
- **Guarda:** `@@TRANCOUNT` antes y después de CADA llamada, también si el servidor la rechazó. Si cambia, la corrida
  se detiene nombrando el objeto.
- **El TO-BE:** el mismo escenario sobre la base cerrada (el estado del respaldo, con los consumibles alineados), en
  una transacción revertida, con las funciones de `estado_tobe.sql`. Las secuencias se regresan a mano y al final la
  base vuelve a su huella.
- **Comparación:** el efecto de cada etapa en las 7 tablas (copia − original en SQL Server, también en bytes; contra
  una foto md5 por fila en PostgreSQL), por LLAVE DE NEGOCIO: la operación por (folio, sucursal), la orden por (uetr,
  número de registro), sus partidas por renglón y la bitácora como multiconjunto de lo que anota. Cada diferencia la
  arbitra una explicación que se AUDITA sobre el respaldo; la que no se explica es defecto nuestro y deja el job en
  rojo.
- **Verificaciones fijas:** todo id devuelto se cruza con la fila que insertó ESA llamada; cada UPDATE … FROM se mide
  con sus datos 1:N.
- **El oráculo:** se captura en el legado vivo, en el congelamiento, cuando lo pide `DECANT_ORACULO=1` (el job
  `legado`, que observa el ciclo para la puerta, no lo enciende). El TO-BE lo re-corre sobre la base cerrada CON el
  delta del paso 4 (el estado del congelamiento), con el instante del servidor de cada caso y con su reloj propio
  (el de negocio del congelamiento). Cada conjunto se compara como multiconjunto (los números por valor); el orden
  prometido se cuenta en los dos lados; donde los motores calculan distinto el mismo texto, se re-corre también la
  copia literal.
- **Aceptación de las trampas:** una trampa observable cuenta como detectada si una comparación de su objeto FALLA y la
  misma comparación sin la trampa (el parche del TO-BE, aplicado a la copia del legado o al TO-BE) PASA. El nombre
  sale de los catálogos sellados, después de la detección.

## Límites declarados

- Las sesiones se muestrean cada 0.25 s: una conexión más corta puede no verse. La bitácora cubre a quienes
  escribieron. El vigía de después del corte (ADR 0016) necesitará un evento de conexión, no un muestreo.
- El servidor no distingue qué cliente hizo cada llamada: la pantalla y las interfaces quedan «sin ejecución
  observada» aunque lo que llaman sí se vea.
- Query Store en captura `AUTO` puede omitir lo poco frecuente; por eso las estadísticas se leen cada 5 s.
- El SQL que un cliente arma por su cuenta no está en el código: sólo se ve si se ejecuta (lo ad hoc).
- Paso 2: `operacion` no tiene bitácora ni `fecha_registro`; su camino por sellos es el folio FX, un contador aparte de
  la identidad (se separan con una inserción revertida: la identidad deja hueco y el folio no). `operacion.estatus` y el
  catálogo no tienen bitácora: si algo los cambiara después del congelamiento, la foto no lo vería (en el vivo nada los
  cambia). La bitácora no guarda `horas_liquidacion`: si el job conciliara después del congelamiento, la medición
  falla en lugar de reconstruir mal.
- Paso 3: con la grieta UTC, `operacion` deja de partir en rangos contiguos (su sello es la fecha de NEGOCIO y las
  altas por archivo de las 22:00 traen horas del día): el plan la rechaza antes de cargar. Las otras tablas sí parten
  contiguo y es el cuadre del mes el que la ve. El control lo reporta en sus dos capas.
- Paso 3: la segunda línea de defensa (restaurar el destino desde una foto) corre desde el paso 4: el delta restaura
  la base cerrada que volcó la nocturna. Una foto tomada antes de CADA mes no se guarda: la reversa del mes, sí.
- Paso 4: `operacion.estatus` lo escribe un procedimiento sin bitácora (`sp_reflejar_estatus_operacion`). El delta no
  puede derivar ese cambio: si corriera dentro de la ventana, lo verían las cifras por documento, no el delta. En el
  vivo nada lo corre.
- Paso 4: `sp_registrar_orden` no es atómico (el INSERT de la orden nueva y el UPDATE a REEMPLAZADA de la vieja van por
  separado). Un respaldo tomado entre los dos dejaría dos registros vigentes en la base. El delta lo deja bien, pero
  la conciliación lo reporta: exige que el registro vigente haya entrado en el delta. En el ciclo, el respaldo se toma
  antes de que el vivo escriba.
- El CI mide sin escribir: el hueco de identidad se prueba sin base y se ensayó una vez en local contra el motor real
  (una inserción revertida: los dos caminos coinciden y se reporta 1 hueco).
- Paso 5: el lado TO-BE de la paridad de estado y del oráculo es SQL de PostgreSQL sobre el esquema `legado` de la base
  de referencia (`estado_tobe.sql`, `oraculo.TOBE`), no el dominio .NET corriendo: el TO-BE de S2 vive en otro esquema
  y aún no tiene los casos de uso de la mesa ni de la contingencia. Son sus reglas (una prueba ata las constantes al
  código .NET) y sus parches; S2 ya mide el dominio contra el legado (motor, R01–R12). Cuando el TO-BE tenga esos casos
  de uso, su efecto se compara con éste.
- Paso 5: en el CI el reloj del servidor del legado es el del runner (otro año que los datos). El reloj PROPIO del TO-BE
  es el de negocio del congelamiento: los dos caen a lados distintos de las órdenes ENVIADA y por eso una re-corrida
  sin el reloj inyectado falla. En un corte real estarían a horas de distancia: la detección depende de que algún dato
  caiga entre los dos relojes.
- Paso 5: el oráculo usa parámetros representativos (2 casos por objeto, uno de ellos en el borde del cierre de mes) y
  la pantalla con 1 caso (lista y un detalle), no todos los parámetros posibles. Los números se comparan por valor: la
  escala de un ROUND es la de cada motor.
- Paso 5: el usuario de la bitácora es el login del arnés (`sa`) en los dos lados; en producción, el de cada
  consumidor. El disparador se emula en PostgreSQL con dos disparadores de sentencia dentro de la transacción revertida.
- Paso 5: el UPDATE … FROM de `sp_conciliar` no tiene datos 1:N (una PRINCIPAL por orden y la suma agrupada): con estos
  datos no se puede probar su multiplicidad. El de `sp_reflejar_estatus_operacion` sí (r3-T1).
- Paso 5: las dos latentes (r1-T1 y r2-T2) coinciden hoy en el oráculo: no se detectan aquí; son del paso siguiente,
  con el plan variado.
- Paso 5: lo que el legado escribe después del congelamiento no entra en la paridad de estado (lo ve el barrido del
  paso 4). La paridad de estado mide el efecto POR LLAMADA sobre el respaldo, no el día completo del legado vivo.
