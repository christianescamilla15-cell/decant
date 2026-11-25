# Control a ciegas · ronda 2 · resultado ANTES de revelar el catálogo

- Siembra: rama `siembra-ciega-2`, commit `b693431`, hecha por otra persona sobre el tag `detectores-v3` (887514d).
- sha256 del catálogo sellado (TRAMPAS_CIEGAS_2.md): `e2c565f39b293a9846cdb7c1bb884721f1e60f562abf5a3ef2ccc380c11bbfbc`.
- `radiografia/` sin cambios respecto al tag; la siembra sólo cambia `legado/sql/03_vista.sql` y `legado/sql/05_procedimientos.sql`.
- Lo único que se sabía de antemano (lo dijo quien sembró): 2 trampas pegan en límites que v3 ya documentó y 1 es de una
  clase nueva. No se sabía cuáles.
- Corrida: `./ciclo.sh` completo en un clon limpio, sin leer el diff antes. Salida 0. Archivos tal cual: `radiografia/informe/ciega2/`.

## Lo que la radiografía reporta distinto respecto a v3 sin siembra (tal cual, sin interpretar)

Hallazgos: 62 → 66. Los 4 nuevos son todos `literal_magico`, en un procedimiento y una vista nuevos:

| Objeto | Línea | Literal | Fragmento |
|---|---|---|---|
| dbo.sp_tablero_corresponsales | 10 | 'CONCILIADA' | `SUM(CASE WHEN p.estatus = 'CONCILIADA' THEN 1 ELSE 0 END) * 100 / COUNT(*) AS pct_conciliadas` |
| dbo.sp_tablero_corresponsales | 11 | 60 | `AVG(DATEDIFF(minute, o.fecha_operacion, p.fecha_envio)) / 60 AS horas_promedio_envio` |
| dbo.sp_tablero_corresponsales | 14 | 'REEMPLAZADA' | `WHERE p.estatus <> 'REEMPLAZADA' AND p.fecha_envio >= @desde AND …` |
| dbo.vw_liquidaciones_recientes | 7 | 'ABONO' | `WHERE s.concepto = 'ABONO'` |

Ningún otro detector cambió su resultado (mismo conteo por categoría salvo `literal_magico` 35 → 39).

El cruce contra el catálogo sellado se agrega DEBAJO de esta sección cuando se revele, sin editar lo de arriba.

---

## Cruce con el catálogo revelado (agregado después; lo de arriba no se editó)

Catálogo: `legado/TRAMPAS_CIEGAS_2.md`, copiado byte a byte; sha256 verificado = `e2c565f3…bbfc` (coincide con el sellado).
Medición: `python -m radiografia.medicion --trampas legado/TRAMPAS_CIEGAS_2.md` → **0 de 3 (0 %)**
(detalle en `radiografia/informe/ciega2/medicion.md`).

| Id | Trampa | Tipo | Por qué no la vio `detectores-v3` |
|---|---|---|---|
| T1 | Vista con `TOP 100 PERCENT … ORDER BY` (el optimizador descarta ese orden) leída sin ORDER BY por un procedimiento: 96,959 de 144,182 pares al revés | límite documentado «vistas» | la vista SÍ trae ORDER BY, y eso engaña al detector de TOP sin ORDER BY |
| T2 | Asignación que parece única por la PK del FROM, pero un LEFT JOIN 1:N la multiplica (latente hoy: 0 de 104,773) | límite documentado «el ON» | la unicidad se decidió sólo con la tabla del FROM, sin mirar los JOIN |
| T3 | División entera (`* 100 / COUNT(*)`, `AVG(DATEDIFF(minute,…)) / 60`): trunca en SQL Server; en PostgreSQL `avg(integer)` devuelve `numeric` | clase NUEVA `division_entera` | ningún detector la cubre; el `60` salió como `literal_magico`, que es ruido, no detección |

**Lectura.** Segunda ronda, segundo 0/3. Lo que se buscaba medir era la GENERALIZACIÓN: 2 trampas caen en límites que
v3 ya había documentado (documentar un límite no lo cubre) y 1 en una clase nueva. La precisión sigue intacta (los
4 hallazgos nuevos son inventario `literal_magico`, no falsos positivos de detección), pero la radiografía por patrón
sólo cubre las formas que alguien ya escribió. Las dos rondas juntas: 0 de 6 a ciegas; 8 de 9 propias; 0 falsos
positivos de alta señal en los controles públicos. Ese es el número honesto.

**Siguiente (detectores-v4, cada arreglo pide otra siembra):**
1. Vistas: `TOP 100 PERCENT` / `TOP (100) PERCENT` con ORDER BY dentro de una vista = orden no garantizado (forma léxica).
2. El ON: la unicidad es la del CONJUNTO; cada tabla unida debe entrar por un ON que iguale una llave ÚNICA suya (PK o
   índice único); si entra por el lado N de una FK, se pierde aunque el WHERE cubra la PK del FROM.
3. División entera: inferencia mínima de tipos (int/smallint/bigint/tinyint, COUNT(*), DATEDIFF, literales enteros,
   AVG(<entero>)); se reporta `/` con ambos lados enteros. Control: las divisiones con `60.0` de `sp_conciliar` NO se marcan.
