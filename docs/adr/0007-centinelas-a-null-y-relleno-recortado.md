# ADR 0007 · Centinelas a NULL y el relleno de ancho fijo se recorta, como parches EXACTOS, medidos en el origen y con control negativo

- Estado: aceptada · Fecha: 2026-11-24 · Revisada el 24-nov (retro): los parches pasan de normalizaciones a
  transformaciones exactas

## Contexto
- T3: el legado guarda «NA» (CLABE y BIC intermediario) y 0 (tipo de cambio de referencia) donde no hay dato.
- Ronda 1 a ciegas, T3: del 4-jul-2022 al 27-ene-2023 una versión de la interfaz guardó la referencia del
  corresponsal con su relleno de 35 caracteres; el buzón la trae sin relleno y PostgreSQL sí distingue `'X  '` de `'X'`.
- `char(n)` rellena con espacios por tipo, no por dato.

## Decisión
- El TO-BE guarda NULL en lugar de los centinelas y la referencia sin relleno (la del buzón, que es su fuente).
- La verificación de la migración compara byte a byte DESPUÉS de aplicar al legado sólo estos parches. Cada parche es
  una transformación EXACTA con el predicado de su hallazgo (`paridad/mapeo.py`):
  - `ciega1_T3`: fecha de la partida dentro de la ventana, valor de exactamente 35 caracteres y relleno final sólo de
    espacios después de un carácter que no es blanco;
  - `char:n`: el ancho del tipo y sólo espacios;
  - `T3_texto` y `T3_numero`: el texto exacto «NA» y el número exacto 0.

  Lo que no cumple el predicado no se toca y sigue contando como diferencia.
- **Conteo medido en el origen.** Cada parche declara su conteo y se mide en la MISMA corrida, en el legado
  restaurado, con SQL y nunca desde el diff que el parche hace desaparecer. Ejemplo para `ciega1_T3`:
  `DATALENGTH = 35`, relleno sólo de espacios y la ventana. Si lo aplicado no es igual a lo medido, la verificación
  falla. Esto sustituye las constantes tecleadas en las pruebas.
- **Control negativo por parche.** En una copia de renglones reales se inyecta en la misma columna un defecto DISTINTO
  y la celda debe quedar distinta. Los defectos: relleno fuera de la ventana, un tabulador antes del relleno, un
  truncado rellenado, un relleno que no llega al ancho, «N/A» o «NA » por «NA», 0.000001 por 0 y una hora corrida.
- **Independencia.** La paridad convierte horas con `zoneinfo` directo (`paridad/zonas.py`), sin el código del
  generador; una prueba contrasta las dos conversiones en los días de cambio de horario y en la hora repetida.
- En la revisión se quitaron dos parches tan amplios como el de la referencia: un `char` aplicado a `folio.serie`, que
  es `varchar(10)`, y un `uuid` que no transformaba nada.

## La historia real de la referencia con relleno (sin reescribirla)
1. Siembra a ciegas, ronda 1: otra sesión plantó el relleno, y la radiografía con `detectores-v2` no lo vio (0 de 3).
2. El catálogo se reveló en `352eb29` (24-nov), antes de S2. `detectores-v3` agregó `espacios_finales` y su ventana.
3. En S2 (`1b597af`), el parche `ciega1_T3` se escribió CONOCIENDO ya la causa, antes de la primera comparación byte a
   byte, y la primera corrida contó 48,013 aplicaciones. Nunca hubo una corrida en la que la verificación fallara con
   48,013 celdas y la causa se supiera después. Esa secuencia, «diff → hallazgo → ADR → parche», no ocurrió para esta
   trampa, y aquí no se finge que ocurrió.
4. Retro del 24-nov: el parche era una normalización (`rstrip(' ')` sobre toda la columna). Se volvió exacto, su conteo
   se mide en el origen y tiene control negativo. Lo que sí está medido: sin el parche, la verificación falla en
   exactamente las celdas que el origen cuenta con su predicado.

Para los parches futuros el orden es obligatorio: diff → hallazgo fechado → ADR → parche ([`docs/parches.md`](../parches.md)).

## Alternativas descartadas
- **Cargar tal cual:** inventa una CLABE «NA» y un tipo de cambio de cero, y rompe el cruce con el buzón en 28,273
  referencias.
- **Normalizar en la comparación (`rstrip`, `lower`, sin predicado):** absuelve justo el defecto que debería verse.
  Le pasó al cargador de la siembra con `rstrip()`, y a la primera versión de este parche.
- **Contar el parche con su propio diff:** se prueba a sí mismo; el conteo tiene que salir del origen.

## Consecuencias
Los reportes que cuenten «con CLABE» cuentan contenido. Si negocio quisiera conservar el relleno, se cambia el parche,
su predicado y su medición, no la comparación.
