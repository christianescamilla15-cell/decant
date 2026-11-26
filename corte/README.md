# corte/ · semana 3

El corte del legado al TO-BE (plan: [`docs/s3/PLAN.md`](../docs/s3/PLAN.md)). Hoy trae el paso 1: el inventario de
salidas y consumidores del legado y su **puerta** (ADR 0014, criterio 1). La vista legible está en
[`inventario/INVENTARIO.md`](inventario/INVENTARIO.md).

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

`inventario/`: `objetos.json` (sale del código), `observado.json` (artefacto de una corrida del CI, versionado con su
número de corrida), `renglones.yml` (a mano) e `INVENTARIO.md` (vista).

## Uso

```bash
python -m corte.puerta                     # código de hoy + observación versionada + renglones; sale con 1 en rojo
python -m corte.escribir                   # regenera objetos.json e INVENTARIO.md (--verificar sólo compara)
```

En el CI, el job `legado` deja el artefacto `ejecucion-observada` y el job `puerta` (aparte y fuera del ruleset) lo
juzga y publica los conteos por destino en su resumen. Para actualizar la observación versionada, se copia ese
artefacto a `inventario/observado.json` y se corre `python -m corte.escribir`.

## Reglas

- El código decide qué entra; lo observado sólo clasifica. Lo que el servidor tiene o ejecuta y el código no, también
  necesita renglón.
- Cada objeto y cada login lleva renglón: `comparado` o `reemplazado_con_paridad` (con evidencia `archivo::prueba` que
  exista), `retirado` (dueño, fecha y confirmación del vigía después del corte) o `pendiente`.
- «Sin ejecución observada» nunca pasa a retirado solo.

## Límites declarados

- Las sesiones se muestrean cada 0.25 s: una conexión más corta puede no verse. La bitácora cubre a quienes
  escribieron. El vigía de después del corte (ADR 0016) necesitará un evento de conexión, no un muestreo.
- El servidor no distingue qué cliente hizo cada llamada: la pantalla y las interfaces quedan «sin ejecución
  observada» aunque lo que llaman sí se vea.
- Query Store en captura `AUTO` puede omitir lo poco frecuente; por eso las estadísticas se leen cada 5 s.
- El SQL que un cliente arma por su cuenta no está en el código: sólo se ve si se ejecuta (lo ad hoc).
