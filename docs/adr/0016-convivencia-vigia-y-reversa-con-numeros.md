# ADR 0016 · Convivencia en el corte, legado vigilado y criterio de reversa fijado con números

- Estado: propuesta (borrador de S3) · Fecha: 2026-11-25

## Contexto
El job del legado vence y concilia con el reloj del servidor. Si el TO-BE también actúa esa noche, el mismo
documento cambia dos veces. Y una reversa decidida «por criterio» el día del cambio llega tarde.

## Decisión
- **Corte medido por dos caminos:** `MAX(id)` por tabla y sellos (bitácora y fecha de operación). Deben coincidir.
  El delta INCLUYE el día del corte (el pendiente re-registrado ese día reaparece con el mismo documento).
- **Cifras de control por DOCUMENTO** en origen y destino, firmadas antes de cambiar.
- **Jobs con reloj:** se apagan en el legado al cortar. Las primeras noches el TO-BE corre en «sólo marca» contra la
  última bitácora del legado (ADR 0010). Nunca actúan los dos la misma noche.
- **Legado después del corte:** en sólo lectura y vigilado. El vigía cuenta conexiones y lecturas, no sólo EXEC:
  cualquier login o ejecución que no estaba en el inventario (ADR 0014) es un consumidor nuevo y abre un hallazgo.
- **Criterio de reversa, fijado ANTES:** revierte cualquiera de estas diferencias:
  - una diferencia de totales de una tabla distinta de 0;
  - un mes que no cuadra;
  - un documento con cifra distinta;
  - una noche con doble acción.

  El **punto de no retorno es un evento medible**: la primera escritura de negocio aceptada en el TO-BE o el primer
  aviso al exterior. El sistema lo registra, y desde ahí `reversa` se niega, porque volver a la huella previa borraría
  lo capturado (control negativo en el CI). Pasado ese punto, sólo se corrige hacia adelante.
- «Sólo marca» se mide en las dos mitades: 0 noches con doble acción y 0 diferencias entre lo que el TO-BE marca y
  la bitácora del legado, en 3 de 3 noches. No actuar no cumple el criterio.

## Alternativas descartadas
- **Correr los dos en paralelo actuando:** doble efecto sobre el mismo documento.
- **Reversa a juicio el día del cambio:** sin números previos no hay decisión, hay discusión.

## Consecuencias
El runbook se prueba en el CI con el vecino emulado. Lo que no se puede probar ahí (redirect o DNS, ventana,
permisos, comunicación) queda documentado con su responsable.
