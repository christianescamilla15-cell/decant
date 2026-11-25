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
- El respaldo se restaura en un contenedor LIMPIO y se verifica su sha256 contra el manifiesto. El criterio de
  salida es `COUNT(*)` de la tabla principal = la cifra que publicó la pantalla al tomar el respaldo. El corte
  (MAX(id), fechas) se mide de la fuente.
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
