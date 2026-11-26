# Corte medido por dos caminos y cifras de control

Generado por `python -m corte.veredicto --versionar` desde la corrida 45862730597 del CI (commit `9cd1b62d8b0c`). Plan: [`docs/s3/PLAN.md`](../../docs/s3/PLAN.md), criterios 3, 7 y 8. No se edita a mano.

## 1. El corte por dos caminos (criterio 3)

Corte = foto del respaldo; congelamiento = la del legado vivo cuando se congela. Reloj del servidor: `2026-11-26 10:54:59.543` → `2026-11-26 10:55:01.147`. Hora de negocio: `2023-12-29T12:00:00+00:00` → `2023-12-30T00:00:00+00:00` (UTC). Cada camino por sellos tiene que dar EXACTAMENTE los mismos ids que la identidad, del delta y de lo posterior: la diferencia de conjuntos es 0 o el corte no avanza.

| tabla | corte (MAX id) | congelamiento | delta | posterior | huecos | camino por sellos: delta + posterior | coincide |
|---|---|---|---|---|---|---|---|
| `dbo.bitacora` | 685,276 | 685,847 | 571 | 4 | 0 | bitácora (su fecha): 571 + 4 | sí |
| `dbo.folio` | – | – | – | – | – | sin identidad: catálogo o consumible, se compara completo | – |
| `dbo.moneda` | – | – | – | – | – | sin identidad: catálogo o consumible, se compara completo | – |
| `dbo.operacion` | 412,125 | 412,546 | 421 | 10 | 0 | folio FX (consumible): 421 + 10 | sí |
| | | | | | | fecha_operacion (control negativo): 416 + 10 | NO: 5 sólo por identidad, 0 sólo por sellos |
| `dbo.orden_pago` | 270,616 | 270,886 | 270 | 4 | 0 | bitácora (alta): 270 + 4 | sí |
| | | | | | | fecha_registro: 270 + 4 | sí |
| `dbo.partida_liquidada` | 893,174 | 894,067 | 893 | 13 | 0 | bitácora (alta de su orden): 893 + 13 | sí |
| | | | | | | fecha_hora (= fecha_registro): 893 + 13 | sí |
| `dbo.partida_solicitada` | 244,869 | 245,140 | 271 | 0 | 0 | bitácora (liquidación de su orden): 271 + 0 | sí |

**Control negativo.** El camino por `fecha_operacion` (fecha de negocio, no sello de registro) pierde 5 ids mayores al corte y la comparación falla nombrando 5 de 5 altas fechadas hacia atrás:
- `412185 (FX-000412185 · sucursal 0012 · fecha 2023-12-28 11:00:00)`
- `412186 (FX-000412186 · sucursal 0012 · fecha 2023-12-28 12:00:00)`
- `412187 (FX-000412187 · sucursal 0012 · fecha 2023-12-28 12:00:00)`
- `412188 (FX-000412188 · sucursal 0012 · fecha 2023-12-28 14:00:00)`
- `412189 (FX-000412189 · sucursal 0012 · fecha 2023-12-28 15:00:00)`

## 2. Totales de las tablas y consumibles (criterio 8)

| tabla | respaldo | + delta | = congelamiento | + posterior | = ahora | IDENT_CURRENT |
|---|---|---|---|---|---|---|
| `dbo.bitacora` | 685,276 | 571 | 685,847 | 4 | 685,851 | 685,851 |
| `dbo.folio` | 2 | – | 2 | – | 2 | – |
| `dbo.moneda` | 11 | – | 12 | – | 12 | – |
| `dbo.operacion` | 412,125 | 421 | 412,546 | 10 | 412,556 | 412,556 |
| `dbo.orden_pago` | 270,616 | 270 | 270,886 | 4 | 270,890 | 270,890 |
| `dbo.partida_liquidada` | 893,174 | 893 | 894,067 | 13 | 894,080 | 894,080 |
| `dbo.partida_solicitada` | 244,869 | 271 | 245,140 | 0 | 245,140 | 245,140 |

Folios (siguiente por serie): FX: 412,126 → 412,547 → 412,557 · OP: 150,720 → 150,851 → 150,855. Monedas: 12 (10 activas).

## 3. Cifras de control por documento (criterios 7 y 8)

563,410 documentos, cada uno con su huella sha256 en `huellas-por-documento.csv` (artefacto del CI; sha256 `b72436796260161e068d799deef100462aa996ecc517efbc800f8beb4e9a2fab`). Llave de negocio: orden = uetr + sucursal, operación = folio FX + sucursal. cargado + no viaja = origen, por tipo y por cada grupo tipo + estado + mes.

| tipo | origen | cargado | pendiente | sin_detalle | duplicado | dato_sucio | montos del origen |
|---|---|---|---|---|---|---|---|
| operacion | 412,556 | 412,546 | 10 | 0 | 0 | 0 | MXN 30,104,528,940.43 |
| orden | 150,854 | 150,850 | 4 | 0 | 0 | 0 | CAD 29,245,328.14 · CHF 9,184,030.07 · CNY 73,994,682.28 · EUR 62,660,066.22 · GBP 17,298,499.79 · HRK 48,910,542.05 · JPY 2,152,753,435.96 · KWD 1,729,694.86 · USD 405,441,498.28 |

Por estado (los 182 grupos tipo + estado + mes, con su huella, están en `cifras-de-control.json`):

| tipo | estado | meses | origen | cargado | no viaja |
|---|---|---|---|---|---|
| operacion | CANCELADA | 36 | 3,219 | 3,219 | 0 |
| operacion | CONCERTADA | 36 | 409,337 | 409,327 | 10 |
| orden | CONCILIADA | 36 | 138,177 | 138,177 | 0 |
| orden | DIFERENCIA | 36 | 6,006 | 6,006 | 0 |
| orden | ENVIADA | 1 | 112 | 108 | 4 |
| orden | LIQUIDADA | 1 | 162 | 162 | 0 |
| orden | VENCIDA | 36 | 6,397 | 6,397 | 0 |

Lo que no viaja, por motivo (muestra):
- **pendiente**: `operacion/FX-000412547/0999` (CONCERTADA, 2023-12): registrada después del congelamiento; `operacion/FX-000412548/0999` (CONCERTADA, 2023-12): registrada después del congelamiento; `operacion/FX-000412549/0999` (CONCERTADA, 2023-12): registrada después del congelamiento; `operacion/FX-000412550/0999` (CONCERTADA, 2023-12): registrada después del congelamiento; `operacion/FX-000412551/0999` (CONCERTADA, 2023-12): registrada después del congelamiento

**Conciliación del delta por llave de negocio (criterio 7).** Re-registros del día del corte: 139: 138 de documentos que ya estaban en la foto del corte y 1 de documentos dados de alta ese mismo día después del respaldo (viven enteros en el delta). Por llave: 0 duplicados y 138 registros viejos que salen. Por id (control negativo): 138 documentos quedan dos veces. Duplicados por documento: 0.

| control negativo | qué se planta | detectado | dónde |
|---|---|---|---|
| un centavo | `01c6de5c-b7b7-4030-a04e-28e23d290cb5/0999` +0.01 | sí | su huella y el grupo orden · LIQUIDADA · 2023-12; en los totales de orden: huella, montos |
| grieta UTC | el mes en UTC: 2,663 documentos cambian de mes | sí | 165 grupos por mes; totales globales distintos: 0 |
| duplicado | otro registro vigente de `01c6de5c-b7b7-4030-a04e-28e23d290cb5/0999` | sí | duplicados por documento: `orden/01c6de5c-b7b7-4030-a04e-28e23d290cb5/0999` |

## 4. Huella versionada

| archivo | sha256 | artefacto (id · digest de GitHub) |
|---|---|---|
| `cifras-de-control.json` | `bc45ff8978c9e47fd6ca904900dcfe158938611a8b67a581654c37c4a5b31e0d` | 15139112746 · `sha256:bc45ff8978c9e47fd6ca904900dcfe158938611a8b67a581654c37c4a5b31e0d` |
| `huellas-por-documento.csv` | `b72436796260161e068d799deef100462aa996ecc517efbc800f8beb4e9a2fab` | 15138139733 · `sha256:b72436796260161e068d799deef100462aa996ecc517efbc800f8beb4e9a2fab` |

El job `corte` vuelve a medir en cada corrida y exige estos mismos sha256: las cifras no dependen del reloj de la corrida. Si cambian a propósito (otro legado, otra forma canónica), se versionan de nuevo con `python -m corte.veredicto <artefacto corte-medido> --versionar --artefactos <gh api …>`.
