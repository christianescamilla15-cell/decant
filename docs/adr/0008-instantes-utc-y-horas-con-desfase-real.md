# ADR 0008 · Instantes en UTC; las horas de liquidación REPLICAN la hora fija hasta que negocio decida; la hora repetida la decide el orden de llegada

- Estado: aceptada · Fecha: 2026-11-24 · Revisada el 24-nov (retro): las horas pasaron de «corregidas» a «réplica»

## Contexto
El legado guarda hora local sin zona (Ciudad de México y Nueva York) y calcula `horas_liquidacion` suponiendo que
Nueva York va siempre una hora adelante (T5). México quitó el horario de verano en oct-2022; Nueva York no. Los dos
calendarios dejaron de coincidir en tres tipos de ventana: de mediados de marzo a inicios de abril y de fines de
octubre a inicios de noviembre en 2021 y 2022 (cada país cambiaba en otra fecha), y de marzo a noviembre en 2023.

## Decisión
- **Se guardan instantes.** El TO-BE guarda `timestamptz` (UTC). La conversión desde el legado es un parche contado
  (T5_cdmx, T5_ny, T5_cdmx_llegada): el instante se guarda bien.
- **Las horas se REPLICAN (ADR 0006).** Negocio no ha decidido el cálculo, así que R08 aplica la fórmula del legado
  sobre las horas de pared que el TO-BE recupera de sus instantes: 100 % de coincidencia en los 144,183 casos. La
  réplica sólo afecta a esta regla; nada se guarda en hora local.
- **La corrección es una HIPÓTESIS medida.** Con los instantes reales coincidiría en 71.28 %. La paridad la audita en
  los dos sentidos, con fuentes independientes del TO-BE: Nueva York por el desfase explícito del `:13D:` del buzón;
  la Ciudad de México por la base de zonas de la paridad, y la hora repetida aparte. Lo que se prueba es «desfase
  extra ≠ 0 ⇔ el legado difiere», con la diferencia igual al extra. Las 41,414 diferencias se desglosan por ventana:
  34,595 de 2023 y 6,819 de 2021 y 2022 (2,498 en la primavera de 2021, 711 en el otoño de 2021, 2,878 en la
  primavera de 2022 y 732 en el otoño de 2022). La suma coincide con la verdad del generador.
- **Hora repetida.** En la 1:00–1:59 que se repite, el instante no está en la base. Las altas de órdenes llegan en el
  orden de su identidad: se toma la primera vuelta que no quede antes del alta anterior; el envío se ancla al PRIMER
  registro de su documento. Lo encontró la paridad (5 folios OP del 31-oct-2021 en otro orden) y, el envío, la verdad
  del generador (2 envíos del 30-oct-2022 que la paridad no podía ver porque el TO-BE y el parche se equivocaban igual).
- **Vencimiento:** los 3 días se cuentan en el calendario de la Ciudad de México, como `sp_conciliar`.
- **Publicación:** la API y el reporte publican cada hora en su zona CON su desfase. La regla real del legado (hora
  local sin zona) no se replica en el formato. El VALOR es el mismo; la paridad lo arbitra como «regla real del
  legado» y audita que el desfase sea el de la zona en ese instante.

## Alternativas descartadas
- **Guardar la hora local como el legado:** perpetúa la ambigüedad de la hora repetida; replicar no lo exige.
- **Corregir las horas sin firma** (la primera versión de este ADR): cambiaba 41,414 cifras sin decisión de negocio y
  contradecía el ADR 0006.

## Consecuencias
Pregunta cerrada a negocio: ¿las horas de liquidación se calculan con el desfase real de Nueva York? Hoy el legado suma
una hora de más en las semanas en que los dos calendarios no coincidieron (primavera y otoño de 2021 y 2022, y de marzo
a noviembre de 2023). La primera versión decía «entre marzo y noviembre desde 2023» y dejaba fuera 6,819 casos de 2021
y 2022. Si negocio decide corregir, se cambia una regla con su prueba, y el invariante del reproceso cuida lo ya
resuelto.

Las operaciones en la hora repetida conservan la primera vuelta: su orden de llegada no es su orden de negocio (el
canal ARCHIVO se carga a las 22:00).
