# Reglas del TO-BE: regla → prueba → origen

Cada regla del TO-BE dice de dónde sale (la LÍNEA del legado, un defecto del catálogo o el formato real de una
interfaz) y qué la prueba. Las líneas son de `legado/sql/05_procedimientos.sql` salvo que se diga otra cosa. La
columna «Paridad» es el % de coincidencia que publica `python -m paridad` con los 3 años de datos
([informe](../paridad/informe/paridad.md)).

Pruebas: `D` = `tests/Decant.Domain.Tests` (casos reales del respaldo) · `A` = `tests/Decant.Application.Tests`
(dobles a mano) · `I` = `tests/Decant.Infrastructure.Tests` (PostgreSQL real) · `W` = `tests/Decant.Api.Tests` ·
`R` = `tests/Decant.Architecture.Tests` · `P` = `tests/test_paridad.py` · `PI` = `tests/integracion/test_paridad.py`.

## Flujo: operación → orden de pago → conciliación

| Id | Regla | Prueba(s) | Origen | Paridad |
|---|---|---|---|---:|
| R01 | Folio FX: consumible por operación, en orden de llegada | D `ReglasDeCambioTests.Los_consecutivos_se_consumen_en_orden_y_con_nueve_digitos` · A `ReproducirUniversoTests.El_folio_fx_es_el_consumible_en_orden_de_llegada` | línea 21 | 100 % |
| R02 | Tipo de cambio: el tecleado manda; si no, referencia × 1.0035 (venta) o × 0.9965 (compra), a 6 decimales | D `Sin_tipo_de_cambio_tecleado_aplica_el_margen_a_la_referencia` (4 operaciones reales) · `El_tipo_de_cambio_tecleado_manda_aunque_haya_referencia` · `Sin_tecleado_ni_referencia_es_un_error_visible_no_un_cero` | líneas 23–25 | 100 % |
| R03 | Pesos = ROUND(monto × tc, 2), mitad lejos del cero | D `Monto_en_pesos_redondea_a_centavos_como_el_legado` (5 operaciones reales) | línea 31 | 100 % |
| R04 | Folio OP: uno por documento (UETR); el re-registro lo conserva | D `OrdenDePagoTests.El_re_registro_conserva_el_folio_y_gana_el_mas_reciente` · `ZonasTests.En_la_hora_repetida_decide_el_orden_de_llegada` (regresión: 5 folios del 31-oct-2021) | líneas 58–63 | 100 % |
| R05 | Cargos del cliente: principal; comisión 0.25 % que TRUNCA (D1) con mínimo 150; IVA 16 %; 25 USD si gastos OUR | D `ReglasDeCargosTests` (comisiones e IVA reales) · P hipótesis en el informe (truncar 100 % · redondear 81.72 %) | líneas 77–89 · D1 | 100 % |
| R06 | Partidas del corresponsal desde el buzón: abono (`:32A:`) y comisión (`:71F:` si > 0) en la moneda de la ORDEN; instante de `:13D:` con su desfase y los segundos de la entrada del respaldo | D `ConciliacionTests.La_confirmacion_se_lee_por_sus_llaves_reales` · `Los_yenes_enteros…` · `Un_mensaje_incompleto_es_un_error_con_nombre` · `Los_segundos_del_respaldo_solo_valen_en_el_mismo_minuto_del_mensaje` · `OrdenDePagoTests.La_liquidacion_registra…` | líneas 104–115 · formato del buzón (ADR 0004) | 100 % |
| R07 | Conciliación: CONCILIADA si abono + comisión = principal; si no, DIFERENCIA (D2: sin decimales ISO 4217) | D `El_veredicto_compara_lo_abonado_contra_el_principal` · `Conciliar_cuadra_lo_abonado_con_el_principal_y_calcula_las_horas` · `Un_abono_incompleto_sale_en_diferencia` | línea 129 · D2 | 100 % |
| R08 | Horas de liquidación con los INSTANTES (T5: el legado resta 1 h fija) | D `Las_horas_de_liquidacion_se_calculan_con_los_instantes` (3 documentos reales, uno por ventana) · P `test_la_auditoria_de_t5…` | línea 128 · T5 · ADR 0008 | 71.28 % (41,414 discrepancias auditadas) |
| R09 | Re-registro: el mismo documento con otra llave interna cada mañana; gana el más reciente; re-registrar algo no enviado es error visible | D `El_re_registro_conserva…` · `Re_registrar_un_documento_que_ya_no_esta_enviado_es_un_error_no_un_folio_nuevo` · A `Un_re_registro_no_cambia_la_vuelta_de_la_hora_del_envio_original` | líneas 58–75 · T9 | 100 % |
| R10 | Vencimiento: ENVIADA hace más de 3 días del calendario de la Ciudad de México, con el reloj de la noche del job | D `Vence_con_la_noche_del_job_y_el_calendario_local` (caso real) · `BordesTests.Lo_enviado_exactamente_tres_dias_antes_de_la_noche_no_vence` (el «menor que» es estricto) · `Con_el_reloj_de_hoy_vence_todo_lo_enviado_por_eso_el_reloj_entra` · R `Nadie_usa_el_reloj_del_sistema_salvo_SystemClock` | línea 139 · T8 | 100 % (sólo marca) |
| R11 | Consecutivos al final de la corrida | paridad R11 | `dbo.folio` | 100 % |
| R12 | D3: la confirmación de un documento vencido se descarta (como el legado) y queda registrada con su motivo | D `La_liquidacion_de_un_documento_vencido_se_descarta_con_error_visible` · A `Reproduce_re_registro_liquidacion_d3_y_vencimiento…` | línea 104 (IF EXISTS sin ELSE) · D3 | 100 % (5,776) |
| — | Transiciones inválidas (conciliar algo no liquidado, vencer algo no enviado) | D `Transiciones_invalidas_no_se_permiten` · `Rehidratar_exige_al_menos_un_registro` | máquina de estados | — |
| — | Confirmación sin documento (huérfana) y `:21:` que no cruza: visibles | A `Una_confirmacion_sin_documento_queda_visible_como_huerfana` · `La_referencia_21_que_no_cruza_se_cuenta_como_error` | llaves del formato (ADR 0009) | — |

## Trampas y defectos del legado

| Id | Decisión del TO-BE | Prueba(s) | Origen |
|---|---|---|---|
| T1 | La lista del día tiene orden explícito (fecha y id) en el calendario de la Ciudad de México | I `La_lista_del_dia_usa_el_calendario_local_y_desempata_por_id` · W `La_lista_del_dia_tiene_orden_explicito` | línea 156 (TOP sin ORDER BY) |
| T2 | El reporte replica «un renglón por partida abonada» (ADR 0006) con orden explícito | I `El_reporte_solo_trae_partidas_abonadas_en_orden_explicito` · W `El_reporte_respeta_su_contrato_de_orden…` · PI `test_la_paridad_de_reporte…` | `03_vista.sql` línea 10 · línea 200 |
| T3 | Centinelas a NULL, contados como parche | D `Los_centinelas_se_vuelven_nulos…` · I `El_detalle_devuelve…` · P `test_parches_t3_centinelas` · PI `test_la_migracion_cuadra_byte_a_byte…` | líneas 30, 31, 70 · ADR 0007 |
| T4 | Las listas se llaman por lo que PINTA la pantalla, no por el nombre de la tabla | PI `test_t4_el_detalle_del_tobe_muestra_lo_que_pinta_cada_rejilla_no_lo_que_dice_la_tabla` · P `test_el_binding_se_lee_del_codigo_de_la_pantalla` · `test_el_tobe_nombra_sus_listas…` · W `El_detalle_publica_las_listas_por_lo_que_son…` | `legado/pantalla/app.py` línea 20 (`REJILLAS`) |
| T5 | Instantes en UTC; hora repetida por orden de llegada; el envío anclado al primer registro | D `ZonasTests` · `BordesTests` (hora que no existe, mismo instante en la hora repetida, desfase positivo en `:13D:`) · P `test_en_la_hora_repetida_decide_el_orden_de_llegada_caso_real_de_r04` · `test_el_envio_se_ancla_al_primer_registro_del_documento_caso_real` | ADR 0008 |
| T6 | `codigo_proposito` se migra; perderla FALLA la comparación de esquema | I `Las_migraciones_crean_la_columna_que_ningun_reporte_imprime…` · P `test_control_negativo_t6…` · PI `test_el_esquema_se_compara_despues_de_cada_carga_y_caza_t6` | `INSERT` de `sp_registrar_orden` |
| T7 | Se conserva el nombre del legado (pregunta cerrada, ADR 0006) | PI byte a byte (`cliente` sin parche) | archivo de sucursales |
| T8 | Reloj inyectado; sólo `SystemClock` lee el del sistema | R `Nadie_usa_el_reloj_del_sistema_salvo_SystemClock` · D `Con_el_reloj_de_hoy…` | línea 139 |
| T9 | Un documento por UETR, historia en `registro_orden`; las partidas de filas reemplazadas se reconstruyen | PI `test_la_migracion_cuadra…` (395,618 reconstruibles) · D `El_re_registro…` | líneas 58–75 |
| D1, D2, D3, H1 | Se replican mientras negocio no decida; la diferencia se mide | ver R05, R07, R12; H1 sin regla (no hay fecha de baja) | ADR 0006 |
| Ronda 1 · T3 | La referencia del corresponsal sin relleno, contada | P `test_parche_ciega1_t3_recorta_solo_espacios_finales` · PI `test_la_migracion_cuadra…` (48,013) | `legado/TRAMPAS_CIEGAS.md` · ADR 0007 |
| Ronda 2 · T2 | El detalle elige el documento EXPLÍCITAMENTE | I `Si_una_operacion_tuviera_dos_documentos_el_detalle_elige_el_mas_reciente` | `legado/TRAMPAS_CIEGAS_2.md` |

## Invariantes y arquitectura

| Regla | Prueba(s) | Origen |
|---|---|---|
| Reprocesar con reglas nuevas nunca quita lo resuelto | D `ReprocesoTests` (incluye 200 combinaciones con semilla fija) · A `Reprocesar_conserva_lo_resuelto_y_lo_reporta` · I `El_reproceso_persistido_conserva_lo_resuelto` | ADR 0010 |
| El replay no puede leer resultados del legado | R `El_replay_no_tiene_acceso_al_oraculo` · I `Un_universo_con_una_columna_de_resultado_no_se_lee` · P `test_el_universo_pide_exactamente…` | ADR 0009 |
| Capas: dominio sólo BCL y sin I/O; aplicación sin infraestructura | R `CapasTests` | ADR 0005 |
| Banderas sólo para efectos laterales; fuera de producción el corresponsal es el emulador | A `La_configuracion_de_cada_ambiente_se_valida` · W `Cada_ambiente_publica_sus_banderas_y_destinos` · CI `decant configuracion` | ADR 0010 |
| Cuadre interno por lado (Σ partes = total del encabezado) y su control con los lados cruzados | P `test_el_cuadre_por_lado_caza_una_lista_cruzada_y_un_desglose_en_cero` · PI `test_el_cuadre_por_lado_pasa_y_su_control_cruzado_falla` | plan S2 |
| Arbitraje: sin árbitro o con auditoría fallida es defecto nuestro | P `test_cada_diferencia_cae_en_una_categoria…` · `test_un_arbitro_que_no_pasa_su_auditoria_no_absuelve` | ADR 0011 |
