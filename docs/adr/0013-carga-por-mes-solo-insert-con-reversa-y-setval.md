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

## Alternativas descartadas
- **TRUNCATE + COPY del estado completo (S2):** no convive con lo capturado y su reversa es todo o nada.
- **UPSERT / MERGE:** esconde duplicados que deberían fallar y hace que la reversa dependa del estado previo.
- **Réplica continua (CDC) hasta el día del cambio:** más piezas móviles y una deriva difícil de cuadrar. La foto
  más el delta del mismo día alcanza para este volumen (≈2.5 millones de filas).

## Consecuencias
El runbook tiene tres verbos (`ensayo`, `aplicar`, `reversa`) y el CI los corre completos. Una grieta plantada (un
mes partido por fecha UTC) prueba que el cuadre mes a mes ve lo que los totales no ven.
