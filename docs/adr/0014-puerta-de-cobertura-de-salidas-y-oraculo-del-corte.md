# ADR 0014 · Puerta de cobertura de salidas y oráculo capturado en el corte

- Estado: propuesta (borrador de S3) · Fecha: 2026-11-25

## Contexto
La paridad de S2 compara las tablas, el reporte de órdenes y la pantalla de detalle. Seis trampas a ciegas con
efecto observable viven en salidas que no compara, y por eso no las vio. Lo que no está en el inventario no se
compara, y lo que no se compara pasa.

## Decisión
- **Inventario por dos fuentes:**
  - el código del legado: procedimientos, vistas, triggers, jobs, interfaces y pantalla, incluido el texto de SQL
    dinámico;
  - lo que el servidor ejecuta de verdad: Query Store y estadísticas de ejecución durante un ciclo completo que
    incluya un cierre de mes.
- Cada objeto con consumidor tiene un renglón con uno de tres destinos: **comparado**, **reemplazado con paridad** o
  **retirado con dueño y fecha**.
- **La puerta:** 0 objetos con consumidor y sin renglón. Es un check del CI que falla nombrando el objeto.
- **Oráculo capturado EN el corte:** la salida de cada objeto de lectura con parámetros representativos (incluido el
  borde de fin de mes) y el instante del servidor al correrla. El TO-BE las re-corre con ese reloj inyectado.
- **Lo latente** se mide con las variantes del plan del piso (ADR 0011). Si el legado no coincide consigo mismo, es
  un defecto a decidir, no un contrato.

## Alternativas descartadas
- **Sólo el código:** no ve consumidores externos ni el SQL que se arma afuera.
- **Sólo las estadísticas:** no ve los caminos que el ciclo no ejecutó (fin de mes, contingencia).
- **Comparar contra una corrida nueva del legado después del corte:** el reloj ya avanzó y la salida cambia por eso,
  no por el TO-BE.

## Consecuencias
Las 6 trampas con efecto observable son la prueba de aceptación: cada una queda «vista» o con su renglón.
