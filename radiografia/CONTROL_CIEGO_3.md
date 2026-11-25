# Control a ciegas · ronda 3 · resultado ANTES de revelar el catálogo

- Siembra: rama `siembra-ciega-3`, commit `fc99aef`, hecha por otra persona sobre el tag `detectores-v4` (e1bb21b).
- sha256 del catálogo sellado (TRAMPAS_CIEGAS_3.md): `04a311087162d9a32483d4d795e1fa017ffbf02bde393d9c10942bb36c5d054e`.
- `radiografia/` sin cambios respecto al tag; la siembra sólo cambia `legado/sql/05_procedimientos.sql`.
- Lo único que se sabía de antemano: al menos una trampa pega en un límite que v4 documentó y otra es de una clase nueva.
- Corrida: `./ciclo.sh` completo en un clon limpio, sin leer el diff antes. Salida 0. Archivos tal cual: `radiografia/informe/ciega3/`.

## Lo que la radiografía reporta distinto respecto a v4 sin siembra (tal cual, sin interpretar)

Hallazgos: 70 → 75. Los 5 nuevos son todos `literal_magico`, en dos procedimientos nuevos:

| Objeto | Línea | Literal | Fragmento |
|---|---|---|---|
| dbo.sp_alta_manual_orden | 20 | 'OP' | `UPDATE dbo.folio SET @n = siguiente, siguiente = siguiente + 1, actualizado = GETDATE() WHERE serie = 'OP';` |
| dbo.sp_alta_manual_orden | 21 | 9 | `SET @folio = 'OP-' + RIGHT('000000000' + CAST(@n AS varchar(9)), 9);` |
| dbo.sp_reflejar_estatus_operacion | 7 | 'CONCILIADA' | `SET estatus = CASE p.estatus WHEN 'CONCILIADA' THEN 'PAGADA'` |
| dbo.sp_reflejar_estatus_operacion | 8 | 'DIFERENCIA' | `WHEN 'DIFERENCIA' THEN 'PAGADA'` |
| dbo.sp_reflejar_estatus_operacion | 9 | 'VENCIDA' | `WHEN 'VENCIDA' THEN 'RECHAZADA'` |

Ningún otro detector cambió su conteo (sólo `literal_magico` 39 → 44).

Nota de operación: la corrida dejó vivo un contenedor de restauración de la radiografía (`decant-radiografia-*`); se
quitó a mano. Es un defecto del ciclo, no de la medición, y queda anotado para corregirse.

El cruce contra el catálogo sellado se agrega DEBAJO de esta sección cuando se revele, sin editar lo de arriba.
