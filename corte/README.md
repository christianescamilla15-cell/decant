# corte/ · semana 3

El corte del legado al TO-BE (plan: [`docs/s3/PLAN.md`](../docs/s3/PLAN.md)). Hoy trae:
- el paso 1: el inventario de salidas y consumidores del legado y su **puerta** (ADR 0014, criterio 1). La vista
  legible está en [`inventario/INVENTARIO.md`](inventario/INVENTARIO.md);
- el paso 2: el **corte medido por dos caminos** y las **cifras de control por documento** (ADR 0013 y 0016,
  criterios 3, 7 y 8). La vista legible está en [`cifras/CIFRAS.md`](cifras/CIFRAS.md).

## Qué hay

| Archivo | Qué hace |
|---|---|
| `sql.py` | Parser determinista del T-SQL de `legado/sql/` (sobre el léxico de la radiografía): qué crea cada script y, de cada módulo o paso de job, qué lee, qué escribe, a quién llama, efectos fuera de la base, reloj, SQL dinámico (también el texto que corre `sp_executesql`), `@@IDENTITY` y transacciones. |
| `fuentes.py` | La pantalla (sus cadenas de SQL) y las interfaces de entrada, leídas con `ast`. |
| `codigo.py` | El inventario desde el código, con el cierre de lo que llama cada objeto y de los triggers que disparan sus escrituras. Escritores = procedimientos, triggers y pasos de job. |
| `observar.py` | En el CI, mientras corre `./ciclo.sh`: sesiones (logins y aplicaciones), peticiones en curso, `dm_exec_*_stats` y lo ad hoc; al cerrar, Query Store, historial del job, catálogo del servidor y usuarios de la bitácora. Sólo lee. |
| `cruce.py` | Código × observación: `observada`, `observada_por_quien_la_usa` (vistas) o `sin_ejecucion_observada`. Clasifica; nunca recorta. |
| `renglones.py`, `puerta.py` | Los renglones y la puerta. |
| `vista.py`, `escribir.py` | `INVENTARIO.md` y la regeneración de lo versionado. |
| `caminos.py` | Paso 2, sin base: los caminos por sellos de cada tabla (consultas literales), sus límites desde las fotos del vivo, la diferencia de conjuntos contra la identidad, los huecos y la cobertura contra las tablas del inventario. |
| `cifras.py` | Paso 2, sin base: la forma canónica y la huella sha256 de cada documento, su destino (cargado o no viaja por motivo), los agregados por tipo + estado + mes, el cuadre, la reconstrucción del estatus con la bitácora y la conciliación por llave de negocio. |
| `medir.py` | En el CI, sobre el legado vivo que deja `./ciclo.sh`: lee la base (sólo lee), mide los dos caminos, arma los documentos al congelamiento y corre los controles negativos sobre los documentos reales. |
| `veredicto.py`, `vista_cifras.py` | Sin base: re-verifica la medición (recuenta desde el CSV documento por documento), compara con lo versionado, comprueba el digest de los artefactos publicados y versiona una corrida en `cifras/` con su `CIFRAS.md`. |

`inventario/`: `objetos.json` (sale del código), `observado.json` (artefacto de una corrida del CI, versionado con su
número de corrida), `renglones.yml` (a mano) e `INVENTARIO.md` (vista).

`cifras/`: `corte.json` y `cifras-de-control.json` de una corrida del CI, `huella.json` (el sha256 de las cifras y del
CSV de huellas por documento, con el id y el digest de sus artefactos) y `CIFRAS.md` (vista). El CSV (≈ 560 mil
documentos) no se versiona: vive en el artefacto, y su sha256 en `huella.json`.

## Uso

```bash
python -m corte.puerta                     # código de hoy + observación versionada + renglones; sale con 1 en rojo
python -m corte.escribir                   # regenera objetos.json e INVENTARIO.md (--verificar sólo compara)
python -m corte.medir --salida corte/medido-ci     # con el legado vivo arriba (después de ./ciclo.sh)
python -m corte.veredicto corte/medido-ci          # sin base: re-verifica y compara con corte/cifras/huella.json
python -m corte.veredicto <artefacto corte-medido> --versionar --artefactos artefactos.json   # a corte/cifras/
```

En el CI, el job `legado` deja el artefacto `ejecucion-observada` y el job `puerta` (aparte y fuera del ruleset) lo
juzga y publica los conteos por destino en su resumen. Para actualizar la observación versionada, se copia ese
artefacto a `inventario/observado.json` y se corre `python -m corte.escribir`.

Paso 2, con el mismo patrón: el job `legado`, al cerrar el ciclo y antes de las pruebas de integración, corre
`corte.medir` y deja el artefacto `corte-medido`. El job `corte` (aparte y fuera del ruleset) lo re-verifica sin base y
publica `cifras-de-control.json` y `huellas-por-documento.csv` como artefactos inmutables con 90 días de retención,
SIN comprimir (`archive: false`): el digest que GitHub calcula al publicarlos es el sha256 del archivo, y el job lo
comprueba y lo deja en su resumen. Para versionar una corrida:
`gh api repos/<dueño>/decant/actions/runs/<id>/artifacts > artefactos.json`, se descarga `corte-medido` y se corre
`python -m corte.veredicto <carpeta> --versionar --artefactos artefactos.json`.

## Reglas

- El código decide qué entra; lo observado sólo clasifica. Lo que el servidor tiene o ejecuta y el código no, también
  necesita renglón.
- Cada objeto y cada login lleva renglón: `comparado` o `reemplazado_con_paridad` (con evidencia `archivo::prueba` que
  exista), `retirado` (dueño, fecha y confirmación del vigía después del corte) o `pendiente`.
- «Sin ejecución observada» nunca pasa a retirado solo.

### El corte por dos caminos (paso 2)

- **Por identidad:** `MAX(id)` de cada tabla en la foto del respaldo (el corte) y en la del congelamiento.
- **Por sellos:** cada tabla con identidad declara en `caminos.py` cómo sabe cuándo se escribió una fila sin mirar su
  id: la bitácora (reloj del servidor, y por ella sus partidas), `fecha_registro` (hora de negocio de la interfaz) o el
  folio FX (el consumible de la operación). Los límites salen de las fotos del legado vivo, que desde el paso 2 anotan
  también el instante del servidor y esperan a que avance.
- La discrepancia es diferencia de CONJUNTOS: 0 ids mayores al corte en un camino y no en el otro, y lo mismo del lado
  del congelamiento. Un hueco de identidad (inserción revertida) no cuenta; dos errores opuestos no se cancelan.
- Las tablas salen del inventario del código: una tabla con identidad sin camino, o un camino huérfano, detiene el
  corte. El camino por `fecha_operacion` es el control negativo: pierde las altas fechadas hacia atrás y la comparación
  falla nombrándolas.

### Las cifras de control (paso 2)

- **Documento** = orden de pago por `(uetr, sucursal)` u operación por `(folio FX, sucursal)`. Los re-registros son la
  historia del documento, no otros documentos.
- Huella sha256 por documento sobre su forma canónica, sin ids; agregada por tipo + estado + mes (local). Destino:
  `cargado` o no viaja por motivo (`pendiente`, `sin_detalle`, `duplicado`, `dato_sucio`), con cargado + no viaja =
  origen por tipo y por grupo. El estado es el del congelamiento: el estatus de las órdenes se reconstruye deshaciendo
  con la bitácora lo posterior.
- Duplicados por documento = 0. El delta se concilia por llave de negocio; por id (control negativo) cada re-registro
  del día de un documento del corte queda dos veces.
- Controles negativos sobre los documentos REALES: un centavo (cambia su huella y la de su mes), la grieta UTC (cuadra
  en totales globales y no por mes) y un duplicado (falla nombrándolo).
- Las cifras y el CSV no dependen del reloj de la corrida: el job `corte` exige los sha256 versionados.

## Límites declarados

- Las sesiones se muestrean cada 0.25 s: una conexión más corta puede no verse. La bitácora cubre a quienes
  escribieron. El vigía de después del corte (ADR 0016) necesitará un evento de conexión, no un muestreo.
- El servidor no distingue qué cliente hizo cada llamada: la pantalla y las interfaces quedan «sin ejecución
  observada» aunque lo que llaman sí se vea.
- Query Store en captura `AUTO` puede omitir lo poco frecuente; por eso las estadísticas se leen cada 5 s.
- El SQL que un cliente arma por su cuenta no está en el código: sólo se ve si se ejecuta (lo ad hoc).
- Paso 2: `operacion` no tiene bitácora ni `fecha_registro`; su camino por sellos es el folio FX, un contador aparte de
  la identidad (se separan con una inserción revertida: la identidad deja hueco y el folio no). `operacion.estatus` y el
  catálogo no tienen bitácora: si algo los cambiara después del congelamiento, la foto no lo vería (en el vivo nada los
  cambia). La bitácora no guarda `horas_liquidacion`: si el job conciliara después del congelamiento, la medición
  falla en lugar de reconstruir mal.
- El CI mide sin escribir: el hueco de identidad se prueba sin base y se ensayó una vez en local contra el motor real
  (una inserción revertida: los dos caminos coinciden y se reporta 1 hueco).
