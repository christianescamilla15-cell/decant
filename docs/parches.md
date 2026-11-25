# Reglas para un parche de la verificación de la migración

Un parche le dice a la verificación byte a byte «esta diferencia es esperada». Por eso es la manera más fácil de
esconder un defecto, y por eso tiene reglas. Todo parche vive en `paridad/mapeo.py`. Hoy existen `char:n`, `T3_texto`,
`T3_numero`, `T5_cdmx`, `T5_ny`, `T5_cdmx_llegada` y `ciega1_T3` (ADR 0007 y 0008).

1. **Orden: diff → hallazgo fechado → ADR → parche.** Primero la verificación falla y se publica cuántas celdas y
   dónde. Después alguien explica la causa con fecha (el hallazgo). Después se escribe la decisión (el ADR). Al final, el
   parche. Si un parche se escribe sabiendo la causa de antemano (como `ciega1_T3`), el ADR lo dice; la historia no se
   reescribe.
2. **Exacto, nunca amplio.** El parche implementa el PREDICADO del hallazgo: ventana de fechas, ancho, caracteres,
   valor exacto. Lo que no cumple el predicado no se toca y sigue contando como diferencia. `rstrip`, `lower` o
   `strip` sobre toda una columna no son parches.
3. **Conteo esperado medido en el origen, en la misma corrida.** Cada (parche, columna) tiene en
   `paridad/migracion.py` (`MEDICIONES`) una consulta al legado restaurado que cuenta los valores que cumplen el
   predicado por OTRO camino: `DATALENGTH` y `LEN`, rangos de fecha, igualdad exacta. Si lo aplicado no es igual a lo
   medido, la verificación falla. Nunca se cuenta desde el diff que el parche hace desaparecer, y nunca se teclea la
   cifra en una prueba.
4. **Control negativo.** Por cada parche hay defectos DISTINTOS que se inyectan en una copia de la misma columna
   (`INYECCIONES` en `paridad/migracion.py`). Todos deben fallar, como falla la comparación de esquema sin
   `codigo_proposito` (T6).
5. **Independencia.** El verificador no comparte código con la fuente de la verdad. La paridad tiene su propia
   conversión de horas (`paridad/zonas.py`), contrastada por una prueba con la del generador.
6. **Publicado.** El informe de paridad lista cada (parche, columna) con lo aplicado, lo medido y el resultado de sus
   controles negativos.
