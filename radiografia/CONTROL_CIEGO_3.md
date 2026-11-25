# Control a ciegas · ronda 3 · resultado ANTES de revelar el catálogo

- Siembra: rama `siembra-ciega-3`, commit `fc99aef`, hecha por otra persona sobre el tag `detectores-v4` (e1bb21b).
- sha256 del catálogo sellado (TRAMPAS_CIEGAS_3.md): `04a311087162d9a32483d4d795e1fa017ffbf02bde393d9c10942bb36c5d054e`.
- `radiografia/` sin cambios respecto al tag; la siembra sólo cambia `legado/sql/05_procedimientos.sql`.
- Lo único que se sabía de antemano: al menos una trampa pega en un límite que v4 documentó y otra es de una clase nueva.
- Corrida: `./ciclo.sh` completo en un clon limpio, sin leer el diff antes. Salida 0. Archivos tal cual: `radiografia/informe/ciega3/`.

## Lo que la radiografía reporta distinto respecto a v4 sin siembra (tal cual, sin interpretar)

Hallazgos: 70 → 75. Los 5 nuevos son todos `literal_magico`, en dos procedimientos nuevos:

| Objeto | Línea | Literal | Fragmento |
|---|---|---|---|
| dbo.sp_alta_manual_orden | 20 | 'OP' | `UPDATE dbo.folio SET @n = siguiente, siguiente = siguiente + 1, actualizado = GETDATE() WHERE serie = 'OP';` |
| dbo.sp_alta_manual_orden | 21 | 9 | `SET @folio = 'OP-' + RIGHT('000000000' + CAST(@n AS varchar(9)), 9);` |
| dbo.sp_reflejar_estatus_operacion | 7 | 'CONCILIADA' | `SET estatus = CASE p.estatus WHEN 'CONCILIADA' THEN 'PAGADA'` |
| dbo.sp_reflejar_estatus_operacion | 8 | 'DIFERENCIA' | `WHEN 'DIFERENCIA' THEN 'PAGADA'` |
| dbo.sp_reflejar_estatus_operacion | 9 | 'VENCIDA' | `WHEN 'VENCIDA' THEN 'RECHAZADA'` |

Ningún otro detector cambió su conteo (sólo `literal_magico` 39 → 44).

Nota de operación: la corrida dejó vivo un contenedor de restauración de la radiografía (`decant-radiografia-*`); se
quitó a mano. Es un defecto del ciclo, no de la medición, y queda anotado para corregirse.

El cruce contra el catálogo sellado se agrega DEBAJO de esta sección cuando se revele, sin editar lo de arriba.

---

## Cruce con el catálogo revelado (agregado después; lo de arriba no se editó)

Catálogo: `legado/TRAMPAS_CIEGAS_3.md`, copiado byte a byte; sha256 verificado = `04a31108…054e` (coincide con el sellado).
Medición: `python -m radiografia.medicion --trampas legado/TRAMPAS_CIEGAS_3.md` → **0 de 3 (0 %)**
(detalle en `radiografia/informe/ciega3/medicion.md`). Esta vez las tres hacen daño YA (ninguna latente):

| Id | Trampa | Tipo | Daño medido |
|---|---|---|---|
| T1 | `UPDATE o … FROM orden_pago p JOIN operacion o` con relación 1:N | límite documentado de v4 («UPDATE … FROM») | 100,299 de 104,773 operaciones quedan con el estado de una fila REEMPLAZADA |
| T2 | `GETDATE()` dentro del texto que ejecuta `sp_executesql` | límite documentado de v4 («SQL dinámico») | 139 órdenes con el reloj de hoy frente a 1 con el del respaldo |
| T3 | `SET @id = @@IDENTITY` tras insertar en una tabla cuyo trigger inserta en otra con identidad propia | clase NUEVA | devuelve el id de la bitácora (685,277) en vez del de la orden (270,617) |

**Lectura.** Tercera ronda, tercer 0/3. Total a ciegas: **0 de 9**, frente a 8 de 9 propias y 0 falsos positivos de alta
señal en los controles públicos. La conclusión ya no es «falta un detector»: un analizador léxico de patrones encuentra
lo que su autor ya sabe nombrar y documentar un límite no lo cubre. Por eso Decant no apuesta la paridad a la
radiografía: la radiografía orienta, y lo que decide es la paridad medida contra el oráculo (semana 2), que no
necesita saber qué trampa hay para encontrar su efecto (las tres de esta ronda cambian datos o salidas que la
paridad SÍ compara).

**Si hay detectores-v5 (cada uno pediría otra ronda):** unicidad del conjunto aplicada al destino de `UPDATE … FROM`
(control: por PK no se marca); literales concatenados que llegan a `sp_executesql`/`EXEC(…)` tratados como código para
los detectores léxicos, y lo no resoluble como inventario `sql_dinamico`; `@@IDENTITY` tras INSERT a tabla con trigger
AFTER INSERT que inserta en otra con identidad = defecto (control: `SCOPE_IDENTITY()` no se marca).

## Medición a ciegas de la paridad (25-nov-2026)

El job `paridad` del PR de esta ronda corrió con el código de la semana 2 tal como quedó en `main` (2949a09), que no
conoce esta ronda, sobre un legado que sí trae las tres trampas. **Resultado: 0 de 3.** Los 11 veredictos salen ✔ y
las cifras son IDÉNTICAS a las de la misma corrida sin la ronda 3 (PR de detectores-v4): R01–R12 al 100 %, reporte con
0 defectos nuestros, 14,984 celdas de regla real y 181 de avance. Sólo cambia el piso de empatados invertidos
(21.25 % → 13.71 %), que varía entre corridas por diseño.

**La lectura de arriba se equivocó.** Decía que las tres trampas «cambian datos o salidas que la paridad SÍ compara». No
es así: son tres procedimientos NUEVOS que nada del ciclo ejecuta (ni el job, ni la pantalla, ni el legado vivo). Su
daño es real (medido ejecutándolos en una transacción revertida), pero latente: aparece cuando alguien los llama. La
paridad sólo compara lo que el legado produjo; lo que no corrió no deja efecto que comparar.

**Consecuencia.** Ni la radiografía (0 de 9) ni la paridad (0 de 3 en esta ronda) bastan solas. Lo que falta es saber
QUÉ objetos tienen consumidor y compararlos a todos: es la puerta de cobertura de salidas de la semana 3 (inventario
desde el código y desde lo que el servidor ejecuta de verdad, más la paridad de ESTADO de los procedimientos que
escriben, corridos sobre el respaldo en una transacción revertida). Estas tres trampas son parte de su prueba de
aceptación.
