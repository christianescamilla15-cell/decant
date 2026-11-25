# ADR 0008 · Instantes en UTC; horas de liquidación con el desfase real; la hora repetida la decide el orden de llegada

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
El legado guarda hora local sin zona (Ciudad de México y Nueva York) y calcula `horas_liquidacion` suponiendo que
Nueva York va siempre una hora adelante (T5). México quitó el horario de verano en oct-2022; Nueva York no.

## Decisión
- El TO-BE guarda `timestamptz` (UTC). La conversión desde el legado es un parche contado (T5_cdmx, T5_ny).
- **Horas con los instantes.** En 41,414 de 144,183 conciliaciones el legado tiene una hora de más. Se publican como
  discrepancia del legado con un árbitro AUDITADO: la diferencia debe ser exactamente (desfase NY − desfase CDMX − 1 h)
  en esos instantes. La cifra coincide con la verdad del generador (41,414).
- **Hora repetida.** En la 1:00–1:59 que se repite, el instante no está en la base. Las altas de órdenes llegan en el
  orden de su identidad: se toma la primera vuelta que no quede antes del alta anterior; el envío se ancla al PRIMER
  registro de su documento. Lo encontró la paridad (5 folios OP del 31-oct-2021 en otro orden) y, el envío, la verdad
  del generador (2 envíos del 30-oct-2022 que la paridad no podía ver porque el TO-BE y el parche se equivocaban igual).
- **Vencimiento:** los 3 días se cuentan en el calendario de la Ciudad de México, como `sp_conciliar`.
- **Publicación:** la API y el reporte publican cada hora en su zona CON su desfase. La regla real del legado (hora
  local sin zona) no se replica en el formato; la paridad la arbitra como «regla real del legado» y audita que el
  desfase sea el de la zona en ese instante (14,984 celdas del reporte).

## Alternativas descartadas
- **Guardar la hora local como el legado:** perpetúa T5 y la ambigüedad de la hora repetida.
- **Replicar la hora fija del legado:** daría 100 % en R08 con un número que está mal; la pregunta queda abierta.

## Consecuencias
Pregunta cerrada a negocio: ¿las horas de liquidación se publican con el desfase real (TO-BE) o con la hora fija del
legado? Las operaciones en la hora repetida conservan la primera vuelta: su orden de llegada no es su orden de negocio
(el canal ARCHIVO se carga a las 22:00).
