# ADR 0006 · Los defectos del legado se replican mientras negocio no decida, y la diferencia queda visible

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
`legado/TRAMPAS.md` cataloga defectos con decisión pendiente (D1–D3, H1) y la radiografía no separa «regla» de
«accidente». Corregir sin decisión cambia cifras que negocio ya firmó; replicar en silencio vuelve permanente el error.

## Decisión
Regla de oro: ninguna regla cambia sin decisión con nombre y fecha. Mientras tanto el TO-BE replica y la diferencia se
MIDE en el informe de paridad (`python -m paridad`):

| Defecto | El TO-BE hoy | Lo que queda visible | Pregunta cerrada |
|---|---|---|---|
| D1 comisión que trunca | trunca (100 % de R05) | redondear coincidiría en 81.72 %: 27,544 comisiones subirían un centavo | ¿se trunca o se redondea? |
| D2 decimales ISO 4217 | compara con centavos (DIFERENCIA en yenes) | 4,317 órdenes en yenes en DIFERENCIA sólo por centavos | ¿se redondea al número de decimales de la moneda? |
| D3 liquidaciones tardías | las descarta como el legado | `liquidacion_descartada`: 5,776 confirmaciones con su motivo (R12) | ¿se registran y se reabre la orden, o se rechazan con error? |
| H1 moneda dada de baja | acepta la operación | ninguna regla la bloquea (veredicto de la radiografía) | ¿se rechaza? ¿desde qué fecha de baja (dato que no existe)? |
| T2 reporte sin órdenes sin abono | un renglón por partida abonada | 6,536 órdenes sin partidas no salen (como en el legado) | ¿el reporte de órdenes incluye las que no tienen abono? |
| T7 nombres dañados | conserva el nombre del legado | 21,189 nombres tienen su versión sana en el archivo de sucursales | ¿se corrigen con el archivo o se conservan? |

Las excepciones ya decididas en el catálogo (T3, T4, T5, T8, T9 y la referencia con relleno de la ronda 1 a ciegas)
tienen su propio ADR (0007, 0008).

## Alternativas descartadas
- **Corregir todo de una vez «porque es lo correcto»:** cifras distintas sin firma; la paridad ya no distinguiría un
  defecto nuestro de una corrección.
- **Una bandera por regla para elegir réplica o corrección:** ruido (ADR 0010); la alternativa se mide en el informe.

## Consecuencias
Cuando negocio decida, el cambio es una regla con su prueba y su fecha, y el invariante del reproceso (ADR 0010)
impide que la regla nueva quite lo ya resuelto.
