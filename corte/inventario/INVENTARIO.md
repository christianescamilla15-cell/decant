# Inventario de salidas y consumidores del legado

> Generado con `python -m corte.escribir` a partir de `objetos.json` (el código), `observado.json` (lo que el CI vio durante el ciclo) y `renglones.yml`. No se edita a mano: `tests/test_corte_puerta.py` lo regenera y lo compara.

## Resumen

- **Objetos desde el código:** 22 · procedimiento 15 · vista 2 · trigger 1 · funcion 0 · job 1 · interfaz 2 · pantalla 1.
- **Escritores** (procedimientos, triggers y pasos de job; paridad de estado, ADR 0015): 8.
- **Observación del ciclo:** corrida `45844672532` (sha `942dfdd`), 144.8 s, 490 muestras de sesiones y 25 de estadísticas; Query Store `READ_WRITE` con captura `AUTO`.
- **Ejecución:** observada 7 · por quien la usa 1 · sin ejecución observada 14 (clasifica; no recorta).
- **Renglones:** comparado 3 · reemplazado_con_paridad 6 · retirado 0 · pendiente 17.
- **Puerta:** roja (17 pendientes: interfaz 1, login 4, pantalla 1, procedimiento 9, trigger 1, vista 1).

## Objetos

| Objeto | Tipo | Acceso | Lee (total) | Escribe (total, con triggers) | Fuera de la base | Reloj | SQL dinámico | En el ciclo | Destino |
|---|---|---|---|---|---|---|---|---|---|
| `dbo.sp_alta_manual_orden` | procedimiento | escribe | – | `dbo.bitacora` (INSERT), `dbo.folio` (UPDATE), `dbo.orden_pago` (INSERT) | – | sí | – | **sin ejecución observada** | pendiente |
| `dbo.sp_antiguedad_ordenes` | procedimiento | lee | `dbo.orden_pago` | – | – | sí | sí (`dbo.orden_pago`) | **sin ejecución observada** | pendiente |
| `dbo.sp_conciliar` | procedimiento | escribe | `dbo.orden_pago`, `dbo.partida_liquidada`, `dbo.partida_solicitada` | `dbo.bitacora` (INSERT), `dbo.orden_pago` (UPDATE) | – | sí | – | **sin ejecución observada** | reemplazado_con_paridad |
| `dbo.sp_constancia_operacion` | procedimiento | lee | `dbo.operacion`, `dbo.orden_pago` | – | – | – | – | **sin ejecución observada** | pendiente |
| `dbo.sp_detalle_operacion` | procedimiento | lee | `dbo.moneda`, `dbo.operacion`, `dbo.orden_pago`, `dbo.partida_liquidada`, `dbo.partida_solicitada` | – | – | – | – | observada | comparado |
| `dbo.sp_liquidaciones_recientes` | procedimiento | lee | `dbo.vw_liquidaciones_recientes` | – | – | – | – | **sin ejecución observada** | pendiente |
| `dbo.sp_lista_operaciones` | procedimiento | lee | `dbo.operacion`, `dbo.orden_pago` | – | – | – | – | observada | pendiente |
| `dbo.sp_ordenes_por_vencer` | procedimiento | lee | `dbo.orden_pago` | – | – | sí | – | **sin ejecución observada** | pendiente |
| `dbo.sp_reflejar_estatus_operacion` | procedimiento | escribe | `dbo.operacion`, `dbo.orden_pago` | `dbo.operacion` (UPDATE) | – | – | – | **sin ejecución observada** | pendiente |
| `dbo.sp_registrar_liquidacion` | procedimiento | escribe | `dbo.orden_pago` | `dbo.bitacora` (INSERT), `dbo.orden_pago` (UPDATE), `dbo.partida_solicitada` (INSERT) | – | sí | – | observada | reemplazado_con_paridad |
| `dbo.sp_registrar_operacion` | procedimiento | escribe | – | `dbo.folio` (UPDATE), `dbo.operacion` (INSERT) | – | sí | – | observada | reemplazado_con_paridad |
| `dbo.sp_registrar_orden` | procedimiento | escribe | `dbo.operacion`, `dbo.orden_pago` | `dbo.bitacora` (INSERT), `dbo.folio` (UPDATE), `dbo.orden_pago` (INSERT/UPDATE), `dbo.partida_liquidada` (INSERT) | – | sí | – | observada | reemplazado_con_paridad |
| `dbo.sp_reporte_ordenes` | procedimiento | lee | `dbo.vw_reporte_ordenes` | – | – | – | – | observada | comparado |
| `dbo.sp_reporte_posicion` | procedimiento | lee | `dbo.moneda`, `dbo.operacion` | – | – | – | – | **sin ejecución observada** | pendiente |
| `dbo.sp_tablero_corresponsales` | procedimiento | lee | `dbo.operacion`, `dbo.orden_pago` | – | – | – | – | **sin ejecución observada** | pendiente |
| `dbo.vw_liquidaciones_recientes` | vista | lee | `dbo.orden_pago`, `dbo.partida_solicitada` | – | – | – | – | **sin ejecución observada** | pendiente |
| `dbo.vw_reporte_ordenes` | vista | lee | `dbo.orden_pago`, `dbo.partida_solicitada` | – | – | – | – | por quien la usa (`dbo.sp_reporte_ordenes`) | comparado |
| `dbo.tr_orden_pago_bitacora` | trigger | escribe | – | `dbo.bitacora` (INSERT) | – | sí | – | observada | pendiente |
| `job:BFN - conciliacion nocturna` | job | escribe | `dbo.orden_pago`, `dbo.partida_liquidada`, `dbo.partida_solicitada` | `dbo.bitacora` (INSERT), `dbo.orden_pago` (UPDATE) | – | sí | – | **sin ejecución observada** | reemplazado_con_paridad |
| `interfaz:archivo_sucursales` | interfaz | entrada | – | – | `archivos: sucursales/{dia:%Y%m%d}.csv`, `archivos: sucursales/{dia:%Y%m%d}_{op.sucursal}_reenvio.csv` | – | – | **sin ejecución observada** | pendiente |
| `interfaz:buzon_corresponsal` | interfaz | entrada | – | – | `archivos: corresponsal/{dia:%Y%m%d}.fin` | – | – | **sin ejecución observada** | reemplazado_con_paridad |
| `pantalla:legado/pantalla` | pantalla | lee | `dbo.moneda`, `dbo.operacion`, `dbo.orden_pago`, `dbo.partida_liquidada`, `dbo.partida_solicitada` | – | – | – | – | **sin ejecución observada** | pendiente |

## Escritores

| Escritor | Escribe (total) | Dispara | Reloj | Identidad / transacción |
|---|---|---|---|---|
| `dbo.sp_alta_manual_orden` | `dbo.bitacora` (INSERT), `dbo.folio` (UPDATE), `dbo.orden_pago` (INSERT) | `dbo.tr_orden_pago_bitacora` | `GETDATE`, `GETDATE (dbo.tr_orden_pago_bitacora)` | `@@IDENTITY` |
| `dbo.sp_conciliar` | `dbo.bitacora` (INSERT), `dbo.orden_pago` (UPDATE) | `dbo.tr_orden_pago_bitacora` | `GETDATE`, `GETDATE (dbo.tr_orden_pago_bitacora)` | – |
| `dbo.sp_reflejar_estatus_operacion` | `dbo.operacion` (UPDATE) | – | – | – |
| `dbo.sp_registrar_liquidacion` | `dbo.bitacora` (INSERT), `dbo.orden_pago` (UPDATE), `dbo.partida_solicitada` (INSERT) | `dbo.tr_orden_pago_bitacora` | `GETDATE (dbo.tr_orden_pago_bitacora)` | – |
| `dbo.sp_registrar_operacion` | `dbo.folio` (UPDATE), `dbo.operacion` (INSERT) | – | `GETDATE` | `SCOPE_IDENTITY` |
| `dbo.sp_registrar_orden` | `dbo.bitacora` (INSERT), `dbo.folio` (UPDATE), `dbo.orden_pago` (INSERT/UPDATE), `dbo.partida_liquidada` (INSERT) | `dbo.tr_orden_pago_bitacora` | `GETDATE`, `GETDATE (dbo.tr_orden_pago_bitacora)` | `SCOPE_IDENTITY` |
| `dbo.tr_orden_pago_bitacora` | `dbo.bitacora` (INSERT) | – | `GETDATE` | – |
| `job:BFN - conciliacion nocturna/paso:conciliar` | `dbo.bitacora` (INSERT), `dbo.orden_pago` (UPDATE) | `dbo.tr_orden_pago_bitacora` | `GETDATE (dbo.sp_conciliar)`, `GETDATE (dbo.tr_orden_pago_bitacora)` | – |

## Consumidores (logins)

| Login | Aplicaciones observadas | Origen | Sesiones | Filas en la bitácora | Destino |
|---|---|---|---|---|---|
| `sa` | `SQLCMD`, `bcp`, `pymssql=2.4.6` | bitácora (SUSER_SNAME del trigger), sesiones (dm_exec_sessions) | 10 | 575 | pendiente |
| `svc_agente` | – | bitácora (SUSER_SNAME del trigger) | 0 | 150,580 | pendiente |
| `svc_interfaz` | – | bitácora (SUSER_SNAME del trigger) | 0 | 390,513 | pendiente |
| `svc_swift` | – | bitácora (SUSER_SNAME del trigger) | 0 | 144,183 | pendiente |

## Acceso fuera de los módulos (lotes ad hoc observados)

Lo que los clientes mandan como texto (no `EXEC` de un procedimiento por RPC): qué tocan, agrupado. No es un objeto del legado; muestra quién lee o escribe tablas directo.

| Lee | Escribe | Llama | Fuera de la base | Lotes | Ejecuciones |
|---|---|---|---|---|---|
| `dbo.operacion` | – | – | – | 13 | 57 |
| `dbo.orden_pago` | – | – | – | 12 | 56 |
| `dbo.bitacora` | – | – | – | 7 | 51 |
| `dbo.partida_solicitada` | – | – | – | 7 | 51 |
| `dbo.partida_liquidada` | – | – | – | 7 | 50 |
| `dbo.folio` | – | – | – | 6 | 14 |
| `dbo.partida_solicitada` | `dbo.partida_solicitada` (UPDATE) | – | – | 1 | 10 |
| `dbo.moneda` | – | – | – | 5 | 9 |
| – | `dbo.moneda` (INSERT) | – | – | 1 | 1 |
| – | `dbo.moneda` (UPDATE) | – | – | 1 | 1 |

## Fuera del código

Nada: todo lo que el servidor tiene o ejecutó del legado está en el código.
