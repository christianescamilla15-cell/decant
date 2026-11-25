# ADR 0011 · Cada diferencia se arbitra con una regla auditada; el orden se juzga contra el piso de la misma corrida

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
Un % global absuelve lo que no entiende, y un orden comparado por posición dice «todo cambió» con un solo renglón
movido. El legado tampoco se repite a sí mismo: su orden entre empates depende del plan.

## Decisión
- Cuatro categorías: defecto nuestro, regla real del legado, discrepancia del legado (ADR + pregunta cerrada) y avance
  de producción. Cada árbitro declara cuándo aplica y cómo se AUDITA; si la auditoría falla, la diferencia es defecto
  nuestro.
- El avance se clasifica contra el corte MEDIDO (`paridad/corte.py`) y se audita en el legado VIVO por identidad: la
  partida existe allá con id mayor al MAX(id) del respaldo. Una regla «por fecha» absolvería mal las altas fechadas
  hacia atrás.
- El orden se mide por inversiones y por llave natural (`uetr`, `concepto`): los pares de contrato (distinta fecha
  valor) deben dar 0; los empatados se juzgan contra el piso que la paridad mide EN LA MISMA corrida (el legado
  re-corrido sobre el respaldo contra lo que publicó). Si el legado no se repite (piso > 0), el orden de los empates no
  es contrato.

## Alternativas descartadas
- **Umbral fijo de % de empates:** el piso varió de 7.08 % a 22.3 % entre corridas de la misma laptop.
- **Comparar por id:** empareja documentos distintos (T9).

## Consecuencias
Sin el legado vivo el avance no se puede auditar y queda como defecto nuestro: la paridad no absuelve a ciegas.
