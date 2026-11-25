# ADR 0010 · Banderas sólo para efectos laterales, modo «sólo marca» e invariante del reproceso

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
Una bandera por regla en un TO-BE que calca el legado es ruido. Lo que sí necesita interruptor es lo que cambia algo
fuera de la regla: el job que vence y concilia documentos, y el aviso al corresponsal.

## Decisión
- `Banderas(VencerAutomatico, ConciliarAutomatico, NotificarCorresponsal)`, por ambiente en `appsettings.{ambiente}.json`
  y validadas: fuera de producción el corresponsal es SIEMPRE el emulador; en producción el aviso no se enciende sin
  contrato y humo (S4). El CI imprime banderas y destinos de los tres ambientes.
- Con una bandera apagada el motor NO actúa: evalúa y deja una marca ✔/✘ por caso (`decant.marca`). Producción
  arranca así. La paridad cruza las marcas con la bitácora del legado noche por noche: 110,424 marcas de vencimiento
  y 144,183 de conciliación, 100 % iguales.
- Invariante: reprocesar con reglas nuevas nunca quita lo resuelto (CONCILIADA o DIFERENCIA). Lo que se conservaría
  como estaba se devuelve y se reporta (`Reprocesamiento.Combinar`, probado en dominio, aplicación y PostgreSQL).

## Alternativas descartadas
- **Una bandera por regla (D1, D2…):** multiplica combinaciones sin probar; las alternativas se miden (ADR 0006).
- **Encender el job directo en producción:** sin marcas no hay evidencia previa de que decide como el legado.

## Consecuencias
Encender una acción es cambiar una bandera de un ambiente, con la evidencia de sus marcas ya publicada.
