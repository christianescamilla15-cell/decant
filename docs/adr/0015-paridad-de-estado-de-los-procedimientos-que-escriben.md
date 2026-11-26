# ADR 0015 · Paridad de ESTADO para los procedimientos que escriben

- Estado: propuesta (borrador de S3) · Fecha: 2026-11-25

## Contexto
Comparar la salida de un procedimiento que escribe no dice qué dejó en la base. Dos trampas lo muestran:
- `UPDATE … FROM` con un JOIN 1:N escribe el estado de una fila cualquiera: 100,299 operaciones quedan mal;
- `@@IDENTITY` después de un trigger que inserta devuelve el id de otra tabla.

## Decisión
- Cada procedimiento que escribe (6 hoy) corre sobre el respaldo restaurado dentro de una transacción que se
  REVIERTE, incluidos los que el ciclo nunca ejecuta («sin ejecución observada», ADR 0014). Antes de revertir se
  vuelcan las tablas que tocó.
- El mismo caso de uso corre en el TO-BE y se comparan las tablas afectadas, fila por fila por llave natural.
- Dos verificaciones fijas:
  - toda escritura con JOIN se prueba con datos 1:N;
  - todo id devuelto se cruza con la fila efectivamente insertada.
- Lo que el reloj decide se corre con el instante del corte. Como `GETDATE()` no se inyecta en el legado, la
  medición usa una copia temporal del procedimiento en un esquema aparte, nunca el original.
- Cada diferencia se arbitra como en S2: defecto nuestro, regla real del legado o defecto del legado a decidir.
- Los escritores salen del inventario (procedimientos, triggers y pasos de jobs): N de N, no una lista fija.
- El arnés falla si `@@TRANCOUNT` cambia durante la llamada. Un ROLLBACK propio se llevaría la transacción externa y
  el volcado saldría vacío sin avisar.
- La transacción revertida no deshace efectos fuera de la base (correo, arranque de jobs, servidores enlazados,
  archivos). Se declaran por objeto y se neutralizan o emulan durante la corrida.

## Alternativas descartadas
- **Confiar en las pruebas unitarias del TO-BE:** prueban la regla que escribimos, no la que el legado ejecuta.
- **Correrlo en una copia y no revertir:** deja estado que contamina la siguiente medición.

## Consecuencias
Se reusa la ejecución revertida que ya tiene la radiografía. Los defectos del legado salen como diferencias con
nombre y no como «fallas de paridad».
