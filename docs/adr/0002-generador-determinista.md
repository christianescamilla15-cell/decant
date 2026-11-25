# ADR 0002 · Los datos del legado salen de un generador determinista que simula su código

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
La paridad de S2 y el corte de S3 se comparan contra el legado. Si sus datos cambian en cada corrida, ninguna
cifra es reproducible. Si se escriben a mano, no cruzan cambios de horario ni tienen el volumen que hace falta para
que el control negativo no salga en 0 %. Si se generan con reglas «parecidas» a las del legado, el TO-BE terminaría
comparándose contra una suposición.

## Decisión
- Semilla fija (`20231229`) y la base de zonas horarias del paquete `tzdata` FIJADO, no la del sistema operativo.
  La misma semilla da la misma huella sha256 por tabla, y una prueba fija la huella de un periodo corto.
- El generador SIMULA el código del legado sobre una línea de tiempo en UTC. Cada fila es lo que habrían escrito
  los procedimientos: alta, re-registro cada mañana hábil, liquidación con la hora de Nueva York, y el job nocturno
  con su `GETDATE()` de esa noche. Los ids se asignan en el orden en que la identidad los habría dado. La carga en
  bloque lo verifica fila por fila en una muestra.
- Lo anterior a la foto (29-dic-2023, 06:00) se carga en bloque. Lo posterior sale como guion de llamadas a los
  MISMOS procedimientos, que ejecuta el legado vivo.
- Las pruebas de integración comparan contra el motor que la simulación calcula lo mismo que los procedimientos:
  tipo de cambio, pesos, comisión truncada, horas de liquidación y re-registro.
- El volumen se MIDIÓ (`legado/VOLUMEN.md`): 400 operaciones por día, el menor volumen probado con el que el reporte
  mensual cambia de orden entre corridas.
- Período: 2021-2023, para cruzar los cambios de horario de México anteriores a oct-2022 con un corresponsal en
  Nueva York.
- El generador deja también los ARCHIVOS DE INTERFAZ que recibió el legado: el buzón del corresponsal y el
  archivo de sucursales (ADR 0004). Además prepara S3: un reenvío tardío de sucursal fechado hacia atrás y los
  documentos que el TO-BE capturará después del congelamiento.

## Alternativas descartadas
- **Faker sin semilla o datos aleatorios por corrida:** no reproducibles.
- **Insertar todo por los procedimientos:** 2.5 M de filas fila por fila tardarían decenas de minutos; el delta sí
  pasa por ellos.
- **Un dump fijo versionado:** 90 MB binarios en Git, imposibles de revisar, que no explican de dónde sale cada
  trampa.

## Consecuencias
- Cambiar el generador cambia la huella. Se actualiza a propósito y se dice en el commit.
- Simular el código del legado no basta para que los datos tengan sentido. Leer el buzón en su formato real destapó
  4 abonos negativos (gastos del corresponsal mayores que órdenes de pocos dólares), que ya estaban en los datos de
  la semana 1. Se corrigieron con su prueba de regresión.
- `random` y `math` de Python deben dar lo mismo en el CI que en local (mismo Python y glibc de Ubuntu 24.04). Si
  la huella fijada falla sólo en el CI, ése es el primer sospechoso.
