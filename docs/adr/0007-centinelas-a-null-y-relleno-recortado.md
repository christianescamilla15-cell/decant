# ADR 0007 · Centinelas a NULL y el relleno de ancho fijo se recorta, como parches documentados y contados

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
- T3: el legado guarda «NA» (CLABE y BIC intermediario) y 0 (tipo de cambio de referencia) donde no hay dato.
- Ronda 1 a ciegas, T3: del 4-jul-2022 al 27-ene-2023 una versión de la interfaz guardó la referencia del
  corresponsal con su relleno de 35 caracteres; el buzón la trae sin relleno y PostgreSQL sí distingue `'X  '` de `'X'`.
- `char(n)` rellena con espacios por tipo, no por dato.

## Decisión
- El TO-BE guarda NULL en lugar de los centinelas y la referencia sin relleno (la del buzón, que es su fuente).
- La verificación de la migración compara byte a byte DESPUÉS de aplicar al legado sólo estos parches, y los CUENTA:
  107,265 CLABE, 53,702 tipos de cambio, 128,220 BIC intermediarios, 48,013 referencias (el mismo número que midió
  la siembra a ciegas). Un parche que cambia algo más que eso deja la celda distinta y la verificación falla.

## Alternativas descartadas
- **Cargar tal cual:** inventa una CLABE «NA» y un tipo de cambio de cero, y rompe el cruce con el buzón en 28,273
  referencias.
- **Normalizar en la comparación sin contarlo:** la normalización absolvería justo el defecto (le pasó al cargador de
  la siembra con `rstrip()`).

## Consecuencias
Los reportes que cuenten «con CLABE» cuentan contenido. Si negocio quisiera conservar el relleno, se cambia el parche y
su conteo, no la comparación.
