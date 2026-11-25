# Control a ciegas · resultado ANTES de revelar el catálogo

- Siembra: rama `siembra-ciega`, commit `65ace22`, hecha por otra persona sobre el tag `detectores-v2`.
- sha256 del catálogo sellado (TRAMPAS_CIEGAS.md): `b61937e5011df6576ad97bd9e560babd7e0ce3cac87adc937900eede03b90866`.
- `radiografia/` sin cambios respecto al tag (0 líneas de diferencia; sha256 de los detectores en `CONTROL.md`).
- Corrida: `./ciclo.sh` completo en un clon limpio, sin leer el diff de la siembra antes de correr. Salida 0.

## Lo que la radiografía reporta distinto respecto al tag (tal cual, sin interpretar)

Hallazgos: 53 en el tag → 58 con la siembra. Los 5 nuevos son todos `literal_magico` en dos procedimientos nuevos:

| Objeto | Línea | Literal | Fragmento |
|---|---|---|---|
| dbo.sp_ordenes_por_vencer | 8 | -2 | `SET @limite = DATEADD(day, -2, @hoy);` |
| dbo.sp_ordenes_por_vencer | 13 | 'ENVIADA' | `WHERE estatus = 'ENVIADA' AND fecha_envio < @limite` |
| dbo.sp_reporte_posicion | 12 | 'C' | `SUM(CASE WHEN tipo = 'C' THEN monto_divisa ELSE 0 END)` |
| dbo.sp_reporte_posicion | 13 | 'V' | `SUM(CASE WHEN tipo = 'V' THEN monto_divisa ELSE 0 END)` |
| dbo.sp_reporte_posicion | 35 | 2 | `ROUND((p.compras - p.ventas) * p.tc_cierre, 2) AS posicion_mxn` |

Ningún detector de alta señal (TOP sin ORDER BY, reloj en regla, IF EXISTS que escribe, desfase fijo, ROUND que trunca,
mojibake, re-registro) ni de datos (centinelas, columnas sin lectura) cambió su resultado.

El cruce contra el catálogo sellado se agrega DEBAJO de esta sección cuando se revele, sin editar lo de arriba.
