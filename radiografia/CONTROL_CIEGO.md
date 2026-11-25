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

---

## Cruce con el catálogo revelado (agregado después; lo de arriba no se editó)

Catálogo: `legado/TRAMPAS_CIEGAS.md`, copiado byte a byte; sha256 verificado = `b61937e5…0866` (coincide con el sellado).
Medición: `python -m radiografia.medicion --trampas legado/TRAMPAS_CIEGAS.md` → **0 de 3 trampas detectadas (0 %)**
(detalle en `radiografia/informe/medicion_ciega.md`).

| Id | Trampa | Por qué no la vio la radiografía congelada |
|---|---|---|
| T1 | Variable asignada desde VARIAS filas (`SELECT @tc_cierre = tipo_cambio FROM … WHERE moneda AND día`) en `sp_reporte_posicion`: selección no determinista | `top_sin_order_by` sólo reconoce la forma con TOP; la misma clase de defecto en otra forma pasa |
| T2 | Reloj del servidor que entra a la regla por una variable (`SET @hoy = GETDATE()` → `@limite` → `WHERE`/`CASE`) en `sp_ordenes_por_vencer` | `reloj_en_regla` sólo ve el reloj escrito dentro de la regla; no sigue la variable |
| T3 | Espacios finales en `partida_solicitada.referencia` (48,013 filas, jul-2022 → ene-2023): SQL Server los ignora al comparar y PostgreSQL no | ningún detector cubre la clase; además la verificación del cargador los «absolvía» con `rstrip()` |

**Lectura.** Los detectores de alta señal acertaron en PRECISIÓN (no inventaron nada) pero NO generalizan más allá de la
forma literal que su autor conocía: exactamente el sesgo que un control a ciegas existe para medir. Los 5 `literal_magico`
son inventario, no detección (el `2` de `ROUND(…, 2)` es ruido del patrón). Resultado honesto: **0/3 a ciegas** frente a
8/9 con trampas propias y 0 FP en los controles públicos.

**Siguiente (detectores-v3, cada arreglo genérico pide otra siembra a ciegas):**
1. Asignación desde varias filas: `SELECT @v = col FROM …` sin TOP 1, sin agregado y SIN predicado único (control de falsos
   positivos dentro del legado: la de `sp_registrar_orden`, `WHERE id = @operacion_id`, NO debe marcarse).
2. Reloj por variable: propagar dentro del módulo las variables asignadas desde GETDATE/SYSDATETIME/CURRENT_TIMESTAMP
   (directas o vía DATEADD) hasta un WHERE, CASE o SET de UPDATE.
3. Espacios finales: `DATALENGTH(col) > LEN(col)` por columna de texto, medido EN EL MOTOR (no en Python tras un BCP),
   con su ventana de fechas.
