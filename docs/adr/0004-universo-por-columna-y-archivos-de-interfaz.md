# ADR 0004 · El universo es por columna e incluye los archivos de interfaz y las noches del job

- Estado: aceptada · Fecha: 2026-11-24

## Contexto
Separar universo (entradas) de oráculo (resultados) por TABLA no alcanza. En `orden_pago` el monto, las fechas y
los BIC entran de fuera, mientras el estatus y las horas de liquidación los calcula el legado. Además, varias
decisiones de negocio pendientes necesitan datos que el respaldo NO tiene:

- D3: las 5,776 confirmaciones que el legado descartó por llegar después del vencimiento no dejaron rastro en la
  base.
- T5: el legado guardó la hora de Nueva York sin su desfase.
- T7: guardó el nombre del cliente ya dañado.
- T8: el reloj del job no está en ninguna columna «de negocio».

Un modernizador real tiene el respaldo y también los archivos que el legado recibió.

## Decisión
- **Partición por columna** en `universo/particion.py`: `llave_interna`, `entrada`, `resultado` o `mixta` para
  cada columna de cada tabla, con su origen o su regla. Una prueba exige que cada columna del esquema tenga
  exactamente una categoría.
- **Archivos de interfaz** que deja el generador (`legado/datos/interfaces/`):
  - el buzón del corresponsal: confirmaciones estilo MT910 simplificado, separadas por `$` como un archivo RJE,
    con TODAS las liquidaciones (tardías incluidas) y `:13D:` con el desfase UTC;
  - el archivo de sucursales: UTF-8 sano, con la referencia natural de cada operación y los reenvíos tardíos.
- **Llaves reales del formato:** `universo/interfaces.py` cruza por la UETR del bloque 3 y por `:21:` (nuestra
  referencia). Nunca por `:20:`, que es la referencia propia del corresponsal y el primer campo «parecido». Una
  prueba demuestra que cruzar por `:20:` no encuentra ningún documento.
- **Noches del job** (`universo/noches.py`): horario de msdb y sellos `svc_agente` de la bitácora. Son el reloj
  que el replay inyecta en lugar de `GETDATE()`.
- El replay de S2 se alimenta SÓLO de: columnas de `entrada` del respaldo + archivos de interfaz + noches.

## Alternativas descartadas
- **Universo = tablas de entrada completas:** mezclaría resultados (estatus, horas) con entradas, y el replay
  copiaría lo que debe calcular.
- **Que el generador entregue la «verdad» en JSON:** ningún legado real la da. Los archivos de interfaz sí
  existen en la vida real.

## Consecuencias
- El generador produce unos 1,560 archivos (≈ 45 MB) que se regeneran con la semilla y no se versionan.
- Leer el buzón en su formato real destapó un defecto del propio generador: 4 abonos negativos en órdenes de pocos
  dólares. Se corrigió con su prueba de regresión.
