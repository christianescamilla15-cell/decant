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
- El piso se mide con el PLAN VARIADO (tal cual; estadísticas nuevas y caché de planes vacía; MAXDOP 4) sobre el
  contenedor limpio, y se toma el mayor. Una sola re-corrida no basta: en un clon limpio salió en 0 % mientras la
  radiografía del mismo ciclo, contra otra restauración, medía 13.78 %. Si las tres variantes dan 0, la paridad falla.

- **Control negativo del COMPARADOR** (retro del 24-nov): el piso calibra el ruido del legado, pero no demuestra que la
  comparación pueda fallar. Seis mutantes del reporte del TO-BE DEBEN fallar, en el job de pruebas normal (fixture
  chico) y en la corrida de paridad (reporte real): un par de contrato invertido, un renglón quitado, un renglón
  duplicado, un centavo distinto, una hora corrida con el desfase bien escrito y un avance que el legado vivo no tiene.
  La hora corrida es la clave: la regla «hora local sin zona» absuelve todos los renglones, y hay que demostrar que
  todavía rechaza algo.
- **Llaves secundarias candidatas:** con cada variante del plan se mide si el legado invierte los empates por moneda,
  corresponsal, concepto, folio, UETR, estatus, horas o monto. Una que nunca se invierte se publica como «posible orden
  de hecho, pregunta a negocio», y el TO-BE no la puede invertir. No se asume libre.
- **Punto ciego declarado:** en la hora que se repite, comparar la hora local por texto no distingue la primera vuelta
  de la segunda. El informe cuenta esas celdas; en el reporte de diciembre de 2023 son 0.

## Alternativas descartadas
- **Umbral fijo de % de empates:** el piso varió de 0 % a 22.3 % entre corridas de la misma laptop.
- **Una sola re-corrida como piso:** un plan que reproduce el orden convierte en «contrato» lo que no lo es.
- **Comparar por id:** empareja documentos distintos (T9).

## Consecuencias
Sin el legado vivo el avance no se puede auditar y queda como defecto nuestro: la paridad no absuelve a ciegas.
