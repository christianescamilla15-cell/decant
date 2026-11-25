# ADR 0003 · La radiografía detecta por patrón genérico y se controla contra una base pública

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
Quien siembra las trampas también escribe la radiografía. Si ésta las buscara por nombre («la columna
`codigo_proposito`»), saldría al 100 % sin demostrar nada: sería circular. Una radiografía real se enfrenta a un
legado que nadie documentó.

## Decisión
- Los detectores buscan FORMAS genéricas, nunca nombres:
  - en el código: TOP sin ORDER BY, INNER JOIN a una tabla hija (según las llaves foráneas), reloj del servidor
    dentro de una regla, IF EXISTS sin ELSE que escribe, desfase horario fijo, literales mágicos y columnas que
    ningún módulo lee;
  - en los datos: centinelas por distribución, mojibake y llaves casi únicas que se repiten con el mismo documento.
- El catálogo de trampas (`legado/TRAMPAS.md`) vive aparte. Sólo `radiografia/medicion.py` lo lee, al final y como
  medición. Una prueba exige que ningún otro módulo de la radiografía lo mencione ni importe el legado.
- El respaldo se restaura en un contenedor LIMPIO y se verifica su sha256 contra el manifiesto. El corte
  (MAX(id), fechas) se mide de la fuente.
- **Criterio de salida NO tautológico** (revisión del 24-nov): el restaurado se compara contra lo que el legado
  decía de sí mismo al tomar el respaldo, no contra sí mismo.
  - COUNT y MAX(id) de CADA tabla y los contadores de folio del manifiesto deben cuadrar.
  - Cada cifra de la pantalla se INTERPRETA: la radiografía prueba COUNT(*) y COUNT(DISTINCT columna) hasta
    averiguar qué cuenta. «Órdenes de pago» cuenta documentos (uetr distintos), no filas: 119,897 filas son
    re-registros.
  - Las salidas que el legado publicó en ese instante se re-corren y se miden por inversiones: contrato en 0 y piso
    de los empates.
- **Veredicto medido** de cada hallazgo fuera del catálogo (`radiografia/veredictos.py`): una consulta sobre el
  respaldo restaurado decide si es latente, defecto real, inventario o señal de respaldo. Es revisión humana
  específica del legado; ningún detector la usa.
- **Detectores congelados y control apartado.** WideWorldImporters ya es de ENTRENAMIENTO: los arreglos de la v1
  se hicieron mirando sus falsos positivos. Los detectores (`tsql.py`, `patrones.py`, `datos.py`) se congelan en
  el tag `detectores-v2` con su sha256 en `CONTROL.md`, y una prueba falla si cambian. Después, y una sola vez, se
  corre AdventureWorks y se publica tal cual salió. La validación del detector de D1 (`round_trunca`, agregado
  después de la v1) sólo cuenta contra ese control.
- **Control a ciegas:** otra sesión siembra trampas en una rama sin que este autor las conozca y publica sólo el
  sha256 de su catálogo. El procedimiento está en el README.
  - La ronda 1 dio **0 de 3** con `detectores-v2` (`radiografia/CONTROL_CIEGO.md`): los detectores acertaban en
    precisión pero no generalizaban más allá de la forma literal.
  - `detectores-v3` agrega los 3 arreglos genéricos que propuso quien sembró y queda congelado en espera de la
    ronda 2. Detectar ahora las 3 trampas de la ronda 1 no cuenta como control.
- **Control:** la misma radiografía, sin cambios, corre sobre WideWorldImporters (respaldo oficial, sha256 fijado),
  y `radiografia/CONTROL.md` publica todo lo que encuentra ahí, falsos positivos incluidos. Un arreglo a un detector
  sólo se acepta si es genérico, tiene su prueba de regresión y no baja la detección en el legado. La versión 1 de
  los detectores se publica junto a la final.

## Alternativas descartadas
- **Un parser completo de T-SQL** (ScriptDom es de .NET y la herramienta es Python): más preciso, pero no cabía
  en la semana. El analizador léxico con niveles de paréntesis bastó, y el control dice dónde no basta (su primer
  defecto, el `END` de un `CASE`, lo encontró el control).
- **Detección por lista de objetos conocidos:** circular.
- **AdventureWorks como control:** válido; se eligió WideWorldImporters por tener más procedimientos (42), tablas
  temporales y un respaldo de 127 MB. AdventureWorks, con sus triggers, queda como segundo control posible.

## Consecuencias
- Algunos patrones (INNER JOIN a una hija, centinelas numéricos, columnas sin lectura) son de REVISIÓN: encuentran
  la forma, no la intención. El informe los presenta así.
- La trampa de los lados invertidos (T4) no tiene patrón de base de datos. Se mide como no detectada en S1 y se
  atrapa en S2 leyendo el binding de la pantalla.
