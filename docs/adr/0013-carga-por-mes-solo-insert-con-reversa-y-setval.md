# ADR 0013 · Carga del corte por mes: sólo INSERT, sólo ids > corte, reversa generada antes y setval al cierre

- Estado: propuesta (borrador de S3) · Fecha: 2026-11-25

## Contexto
En S2 el almacén reemplaza el estado completo en una transacción (TRUNCATE + COPY). Sirve para medir, pero no para un
corte: borra lo que el TO-BE ya hubiera capturado y no deja reversa fina. El corte tiene que poder correr por
partes, verificarse parte por parte y deshacerse sin tocar lo que no cargó.

## Decisión
- La carga histórica va por MES de negocio (36: ene-2021 a dic-2023). Sólo INSERT y sólo filas con id > corte
  MEDIDO, que es el mismo por los dos caminos (`MAX(id)` y sellos, ADR 0016).
- La reversa de cada mes se GENERA ANTES de aplicarlo: los ids exactos a borrar y los valores de secuencia y
  consumibles a restaurar. Se guarda junto con la huella previa. Segunda línea de defensa: restaurar desde la corrida
  anterior, una foto de la base del TO-BE tomada antes de aplicar.
- Al cierre, `setval` de cada secuencia por encima del máximo cargado. Los consumibles (folios, contadores) se suben
  con margen ANTES del delta, y el delta se numera DESPUÉS: el legado siguió usando folios tras el congelamiento.
- Cada mes deja su huella sha256 por tabla en origen y destino. El cuadre es mes a mes, no sólo de totales.
- Primero se ensaya sobre una foto con los MISMOS índices únicos que producción; un choque ahí detiene el corte.
- «Ya lo trabajó el TO-BE» se decide por la bitácora de ACCIONES de negocio, nunca por el token de concurrencia ni
  la fecha de modificación: las escrituras informativas del sistema (marcas, validaciones) los cambian y harían que
  la reversa se salte filas. `aplicar` se niega si hay automatismos del TO-BE encendidos.
- El delta concilia por llave de negocio (documento + sucursal): un re-registro trae id nuevo, el viejo sale y no
  queda ningún documento duplicado. Lo derivado por id se re-arma después de cada carga.

## Al construirla (26-nov, paso 3)
Lo que el código decidió y la propuesta no decía (`corte/carga.py`, `corte/runbook.py`, `corte/destino.sql`):
- **El esquema `legado` guarda los valores CRUDOS:** `char(n)` con su relleno, los centinelas tal cual, la hora local
  sin zona. Los parches del ADR 0007 se aplican de `legado` al TO-BE, como ya los aplica y mide S2. Si se aplicaran
  al cargar, la huella del mes no podría ser igual en origen y destino.
- **«Sólo ids > corte», mes a mes:** el corte de un mes es lo que el destino ya tiene, medido por dos caminos
  (`MAX(id)` y el registro de meses aplicados). Lo que no pasa del corte del respaldo (el medido en el paso 2) es la
  carga histórica; lo que pasa, el delta del paso 5.
- **El mes de cada fila es el de su sello en hora local.** Se comprobó sobre los 3 años que en las 5 tablas el mes del
  sello no retrocede con el id: cada mes es un rango contiguo. Si alguna vez se enciman, no hay plan.
- **Sin llaves foráneas mientras se carga:** un mes referencia filas de meses anteriores (re-registros, liquidaciones
  de órdenes viejas). Se agregan, validando, en el cierre.
- **El ensayo es el mismo `aplicar` en una transacción revertida sobre el mismo destino**, cuyos índices únicos se
  comparan contra el catálogo del origen. `aplicar` exige un ensayo verde del mismo mes y plan sobre la misma huella.
- **Permisos separados:** `aplicar` corre con un rol que sólo puede insertar en las tablas del legado; `reversa`, con
  uno que sólo puede borrar. Ninguno toca el punto de no retorno.
- **`setval` no es transaccional en PostgreSQL:** al revertir una transacción, el runbook regresa las secuencias a mano.
- **La grieta UTC tiene dos capas:** en `operacion` (su sello es la fecha de negocio) el plan con la grieta se encima
  y se rechaza antes de cargar; en las demás tablas lo ve el cuadre del mes. Los totales globales no la ven en ninguna.

## Al construir el delta (26-nov, paso 4)
Lo que el código del delta decidió (`corte/delta.py`, `corte/runbook_delta.py`, `corte/delta.sql`, `corte/base.py`):
- **Base:** el delta va sobre la base CERRADA (36 meses, `setval`, folios con margen, llaves foráneas). La nocturna la
  vuelca con `pg_dump` (artefacto `destino-cerrado`, 14 días) y el delta la RESTAURA en una base limpia: ésa es la
  segunda línea de defensa («restaurar desde la corrida anterior») y corre cada noche y en cada PR. A la foto no se le
  cree: se comprueban su sha256, la huella después de restaurar, el plan de ESTA corrida (mismos rangos y montos por
  mes), los 36 meses aplicados, las llaves foráneas y los totales del origen hasta el corte. Si no hay volcado vigente,
  la base se construye con el mismo runbook.
- **Qué entra, por id:** las filas entre el corte y el congelamiento por tabla, los dos medidos en el paso 2. La
  selección se compara con el rango de la identidad y lo que falta se nombra (un delta por fecha pierde las altas que
  la sucursal reenvió fechadas hacia atrás).
- **Cambios sobre filas ≤ corte:** salen de la bitácora posterior al corte y hasta el congelamiento, y se comprueban
  FILA POR FILA contra el origen al congelamiento. Las filas del corte que difieren tienen que ser exactamente las que
  la bitácora anota y diferir sólo en las columnas que el legado escribe sobre una orden ya registrada. El valor del
  destino tiene que ser el primer «anterior» de su cadena; si no, el destino no está en la foto del corte y no se
  aplica nada. Lo anotado después del congelamiento se deshace y queda para el barrido posterior al corte, junto con
  las filas de id > congelamiento.
- **UPDATE acotado, y por qué:** el re-registro y la liquidación cambian filas que ya cargó la histórica. Sin
  UPDATE, el documento queda dos veces (el registro viejo sigue vigente) o en un estado que ya no es el del legado.
  - La alternativa (borrar y volver a insertar la fila con el estado nuevo) le daría a `aplicar` el DELETE, que es más
    poder que un UPDATE de dos columnas. Además rompería las llaves foráneas de sus partidas.
  - Por eso el delta tiene sus propios roles y los de la carga por mes no cambian (`aplicar` sigue sólo insertando).
  - `decant_corte_delta_aplica` inserta y actualiza SÓLO `estatus` y `horas_liquidacion` de la orden y `activa` de la
    moneda: las columnas que escriben `sp_registrar_orden`, `sp_registrar_liquidacion`, el job y la baja del catálogo.
    Una prueba las compara con los procedimientos.
  - `decant_corte_delta_revierte` borra y devuelve esas mismas columnas a su valor previo. No inserta.
  - Ninguno toca el punto de no retorno.
  - El resto de las filas del corte se comprueba intacto por huella dentro de la misma transacción.
- **La reversa del delta** se genera ANTES de escribir, con los VALORES PREVIOS de cada fila actualizada y de cada
  moneda, leídos del destino. También guarda los rangos que se borran, las secuencias, los folios y la huella previa.
  Confirma sólo si el destino vuelve a esa huella, folios incluidos.
- **Secuencias y folios:** las secuencias suben a `IDENT_CURRENT` del legado de AHORA, por encima de las filas
  posteriores al congelamiento, que quedan para el barrido: el TO-BE no reusa un id que el legado ya dio. Los folios
  sólo suben, y el delta se niega si el siguiente del destino choca con un folio que el legado ya usó, también después
  del congelamiento.
- **Idempotencia:** a lo más un delta aplicado. Lo cuidan tres cosas: el registro, la guarda «el destino llega
  exactamente al corte» y un índice único parcial en la base.
- **Catálogo:** no tiene bitácora. La foto del congelamiento del legado vivo lo anota completo y el delta toma las
  monedas de ahí.
- **Lo derivado por id** se re-arma después del delta y de su reversa (`delta.DERIVADOS`). Hoy no hay nada derivado:
  el esquema `legado` guarda los valores crudos y los parches del ADR 0007 van al TO-BE, fuera del corte.

## Alternativas descartadas
- **TRUNCATE + COPY del estado completo (S2):** no convive con lo capturado y su reversa es todo o nada.
- **UPSERT / MERGE:** esconde duplicados que deberían fallar y hace que la reversa dependa del estado previo.
- **Réplica continua (CDC) hasta el día del cambio:** más piezas móviles y una deriva difícil de cuadrar. La foto
  más el delta del mismo día alcanza para este volumen (≈2.5 millones de filas).

## Consecuencias
El runbook tiene tres verbos (`ensayo`, `aplicar`, `reversa`) y el CI los corre completos. Una grieta plantada (un
mes partido por fecha UTC) prueba que el cuadre mes a mes ve lo que los totales no ven.
