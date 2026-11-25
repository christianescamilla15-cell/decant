# Control a ciegas · ronda 2 · resultado ANTES de revelar el catálogo

- Siembra: rama `siembra-ciega-2`, commit `b693431`, hecha por otra persona sobre el tag `detectores-v3` (887514d).
- sha256 del catálogo sellado (TRAMPAS_CIEGAS_2.md): `e2c565f39b293a9846cdb7c1bb884721f1e60f562abf5a3ef2ccc380c11bbfbc`.
- `radiografia/` sin cambios respecto al tag; la siembra sólo cambia `legado/sql/03_vista.sql` y `legado/sql/05_procedimientos.sql`.
- Lo único que se sabía de antemano (lo dijo quien sembró): 2 trampas pegan en límites que v3 ya documentó y 1 es de una
  clase nueva. No se sabía cuáles.
- Corrida: `./ciclo.sh` completo en un clon limpio, sin leer el diff antes. Salida 0. Archivos tal cual: `radiografia/informe/ciega2/`.

## Lo que la radiografía reporta distinto respecto a v3 sin siembra (tal cual, sin interpretar)

Hallazgos: 62 → 66. Los 4 nuevos son todos `literal_magico`, en un procedimiento y una vista nuevos:

| Objeto | Línea | Literal | Fragmento |
|---|---|---|---|
| dbo.sp_tablero_corresponsales | 10 | 'CONCILIADA' | `SUM(CASE WHEN p.estatus = 'CONCILIADA' THEN 1 ELSE 0 END) * 100 / COUNT(*) AS pct_conciliadas` |
| dbo.sp_tablero_corresponsales | 11 | 60 | `AVG(DATEDIFF(minute, o.fecha_operacion, p.fecha_envio)) / 60 AS horas_promedio_envio` |
| dbo.sp_tablero_corresponsales | 14 | 'REEMPLAZADA' | `WHERE p.estatus <> 'REEMPLAZADA' AND p.fecha_envio >= @desde AND …` |
| dbo.vw_liquidaciones_recientes | 7 | 'ABONO' | `WHERE s.concepto = 'ABONO'` |

Ningún otro detector cambió su resultado (mismo conteo por categoría salvo `literal_magico` 35 → 39).

El cruce contra el catálogo sellado se agrega DEBAJO de esta sección cuando se revele, sin editar lo de arriba.
