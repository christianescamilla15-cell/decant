-- Paridad de estado (S3 paso 5, ADR 0015): el EFECTO que el TO-BE tiene que dejar, sobre la base de referencia del
-- corte (el esquema `legado` de la base cerrada, con los valores CRUDOS). Lo crea `corte/estado_ci.py` DENTRO de la
-- transacción de cada escenario, que se REVIERTE; las secuencias se regresan a mano (setval no es transaccional).
--
-- Son las reglas del dominio .NET (R01–R12: folio por consumible, tipo de cambio y pesos, comisión que trunca, IVA,
-- gastos OUR, re-registro que conserva el folio, liquidación sólo de lo ENVIADO, conciliación, horas con la hora fija
-- y vencimiento con el reloj que ENTRA) expresadas sobre las tablas del legado, para medir el efecto POR LLAMADA sobre
-- el mismo estado inicial. Los defectos del legado se replican mientras negocio no decida (ADR 0006), salvo los que
-- el TO-BE ya corrige por diseño, que son los PARCHES de este archivo:
--   · el reloj ENTRA (`decant.reloj`), nunca el del servidor;
--   · la mesa refleja el estatus de la orden VIGENTE (r3-T1: el legado toma una cualquiera de un JOIN 1:N);
--   · la contingencia devuelve la identidad de SU inserción, `RETURNING id` (r3-T3: el legado, `@@IDENTITY`);
--   · las selecciones «la primera que encuentre» (TOP sin ORDER BY) eligen por id: hoy son únicas (0 casos).
-- La bitácora del disparador se emula con dos disparadores de sentencia (las mismas filas: una por fila escrita).
-- `decant.usuario` es el login de la sesión (en el arnés, el mismo que usa el legado).

CREATE SCHEMA tobe_estado;

CREATE FUNCTION tobe_estado.reloj() RETURNS timestamp LANGUAGE sql STABLE AS
$$ SELECT current_setting('decant.reloj')::timestamp $$;

-- smalldatetime: al minuto más cercano (29.998 s o menos baja; 29.999 o más sube).
CREATE FUNCTION tobe_estado.a_minuto(t timestamp) RETURNS timestamp LANGUAGE sql IMMUTABLE AS
$$ SELECT date_trunc('minute', t + interval '30.001 seconds') $$;

-- DATEDIFF(minute, a, b): fronteras de minuto que cruza (no minutos transcurridos).
CREATE FUNCTION tobe_estado.minutos(a timestamp, b timestamp) RETURNS bigint LANGUAGE sql IMMUTABLE AS
$$ SELECT (extract(epoch FROM date_trunc('minute', b) - date_trunc('minute', a)) / 60)::bigint $$;

-- ── la bitácora (reemplaza a dbo.tr_orden_pago_bitacora) ─────────────────────────────────────────────────────────
CREATE FUNCTION tobe_estado.bitacora_alta() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO legado.bitacora (tabla, llave, accion, estatus_anterior, estatus_nuevo, usuario, fecha)
    SELECT 'orden_pago', i.id, 'I', NULL, i.estatus, current_setting('decant.usuario'), tobe_estado.reloj()
    FROM nuevas i;
    RETURN NULL;
END $$;

CREATE FUNCTION tobe_estado.bitacora_cambio() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO legado.bitacora (tabla, llave, accion, estatus_anterior, estatus_nuevo, usuario, fecha)
    SELECT 'orden_pago', i.id, 'U', d.estatus, i.estatus, current_setting('decant.usuario'), tobe_estado.reloj()
    FROM nuevas i LEFT JOIN viejas d ON d.id = i.id;
    RETURN NULL;
END $$;

CREATE TRIGGER tobe_estado_bitacora_alta AFTER INSERT ON legado.orden_pago
    REFERENCING NEW TABLE AS nuevas FOR EACH STATEMENT EXECUTE FUNCTION tobe_estado.bitacora_alta();
CREATE TRIGGER tobe_estado_bitacora_cambio AFTER UPDATE ON legado.orden_pago
    REFERENCING OLD TABLE AS viejas NEW TABLE AS nuevas FOR EACH STATEMENT EXECUTE FUNCTION tobe_estado.bitacora_cambio();

-- ── R01–R03: alta de la operación ───────────────────────────────────────────────────────────────────────────────
CREATE FUNCTION tobe_estado.registrar_operacion(
    p_fecha_operacion timestamp, p_sucursal text, p_canal text, p_cliente text, p_cuenta_clabe text, p_tipo text,
    p_moneda text, p_monto_divisa numeric, p_tc_referencia numeric, p_tc numeric) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    n integer;
    v_id integer;
    v_monto numeric(18, 2) := p_monto_divisa;
    v_referencia numeric(18, 6) := p_tc_referencia;
    v_tc numeric(18, 6) := p_tc;
BEGIN
    UPDATE legado.folio SET siguiente = siguiente + 1, actualizado = tobe_estado.reloj() WHERE serie = 'FX'
    RETURNING siguiente - 1 INTO n;
    IF v_tc IS NULL THEN
        -- la asignación a numeric(18,6) redondea lejos del cero, como la conversión de SQL Server
        v_tc := CASE p_tipo WHEN 'V' THEN v_referencia * 1.0035 ELSE v_referencia * 0.9965 END;
    END IF;
    INSERT INTO legado.operacion (folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda,
                                  monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus)
    VALUES ('FX-' || right('000000000' || n::text, 9), tobe_estado.a_minuto(p_fecha_operacion),
            p_sucursal::char(4), p_canal::varchar(10), p_cliente::varchar(120),
            coalesce(p_cuenta_clabe::varchar(18), 'NA'), p_tipo::char(1), p_moneda::char(3), v_monto, v_tc,
            coalesce(v_referencia, 0), round(v_monto * v_tc, 2), 'CONCERTADA')
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;

-- ── R04, R05 y R09: alta y re-registro de la orden con las partidas del cliente ────────────────────────────────
CREATE FUNCTION tobe_estado.registrar_orden(
    p_operacion_id integer, p_uetr text, p_referencia_mt103 text, p_fecha_registro timestamp,
    p_fecha_envio timestamp, p_fecha_valor date, p_bic_corresponsal text, p_bic_intermediario text,
    p_beneficiario text, p_cuenta_beneficiario text, p_moneda text, p_monto numeric, p_gastos text,
    p_codigo_proposito text) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    v_anterior integer;
    v_folio varchar(20);
    n integer;
    v_id integer;
    v_mxn numeric(18, 2);
    v_comision numeric(18, 2);
    v_monto numeric(18, 2) := p_monto;
    v_moneda char(3) := p_moneda;
BEGIN
    SELECT id, folio INTO v_anterior, v_folio FROM legado.orden_pago
    WHERE uetr = p_uetr::char(36) AND estatus = 'ENVIADA' ORDER BY id DESC LIMIT 1;
    IF v_folio IS NULL THEN
        UPDATE legado.folio SET siguiente = siguiente + 1, actualizado = tobe_estado.reloj() WHERE serie = 'OP'
        RETURNING siguiente - 1 INTO n;
        v_folio := 'OP-' || right('000000000' || n::text, 9);
    END IF;
    INSERT INTO legado.orden_pago (operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio,
                                   fecha_valor, bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario,
                                   moneda, monto, gastos, codigo_proposito, estatus)
    VALUES (p_operacion_id, v_folio, p_uetr::char(36), p_referencia_mt103::varchar(16), p_fecha_registro,
            p_fecha_envio, p_fecha_valor, p_bic_corresponsal::char(11),
            coalesce(p_bic_intermediario::char(11), 'NA'), p_beneficiario::varchar(120),
            p_cuenta_beneficiario::varchar(34), v_moneda, v_monto, p_gastos::char(3), p_codigo_proposito::char(4),
            'ENVIADA')
    RETURNING id INTO v_id;
    IF v_anterior IS NOT NULL THEN
        UPDATE legado.orden_pago SET estatus = 'REEMPLAZADA' WHERE id = v_anterior;
    END IF;
    SELECT monto_mxn INTO v_mxn FROM legado.operacion WHERE id = p_operacion_id;
    v_comision := trunc(v_mxn * 0.0025, 2);                       -- ROUND(…, 2, 1): trunca (D1)
    IF v_comision < 150 THEN
        v_comision := 150;
    END IF;
    INSERT INTO legado.partida_liquidada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
    VALUES (v_id, 1, 'PRINCIPAL', v_moneda, v_monto, p_fecha_registro, v_folio),
           (v_id, 2, 'COMISION', 'MXN', v_comision, p_fecha_registro, v_folio),
           (v_id, 3, 'IVA', 'MXN', round(v_comision * 0.16, 2), p_fecha_registro, v_folio);
    IF p_gastos::char(3) = 'OUR' THEN
        INSERT INTO legado.partida_liquidada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
        VALUES (v_id, 4, 'GASTOS_OUR', 'USD', 25.00, p_fecha_registro, v_folio);
    END IF;
    RETURN v_id;
END $$;

-- ── R06/R07: la confirmación del corresponsal (sólo si sigue ENVIADA; si no, se descarta como el legado, D3) ──────
CREATE FUNCTION tobe_estado.registrar_liquidacion(
    p_uetr text, p_referencia text, p_fecha_hora timestamp, p_abono numeric, p_comision numeric) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    v_id integer;
    v_moneda char(3);
    v_comision numeric(18, 2) := p_comision;
BEGIN
    SELECT id, moneda INTO v_id, v_moneda FROM legado.orden_pago
    WHERE uetr = p_uetr::char(36) AND estatus = 'ENVIADA' ORDER BY id DESC LIMIT 1;
    IF v_id IS NULL THEN
        RETURN;
    END IF;
    INSERT INTO legado.partida_solicitada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
    VALUES (v_id, 1, 'ABONO', v_moneda, p_abono::numeric(18, 2), p_fecha_hora, p_referencia::varchar(35));
    IF coalesce(v_comision, 0) > 0 THEN
        INSERT INTO legado.partida_solicitada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
        VALUES (v_id, 2, 'COMISION_CORRESPONSAL', v_moneda, v_comision, p_fecha_hora, p_referencia::varchar(35));
    END IF;
    UPDATE legado.orden_pago SET estatus = 'LIQUIDADA' WHERE id = v_id;
END $$;

-- ── R07, R08 y R10: el proceso nocturno con la noche que ENTRA ──────────────────────────────────────────────────
CREATE FUNCTION tobe_estado.conciliar() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    CREATE TEMP TABLE tobe_lote ON COMMIT DROP AS
        SELECT id FROM legado.orden_pago WHERE estatus = 'LIQUIDADA' ORDER BY id LIMIT 5000;
    UPDATE legado.orden_pago o
    SET horas_liquidacion = round(tobe_estado.minutos(o.fecha_envio, l.ultima - interval '1 hour') / 60.0, 2),
        estatus = CASE WHEN l.abonado = p.principal THEN 'CONCILIADA' ELSE 'DIFERENCIA' END
    FROM tobe_lote x,
         (SELECT orden_id, sum(monto) AS abonado, max(fecha_hora) AS ultima
          FROM legado.partida_solicitada GROUP BY orden_id) l,
         (SELECT orden_id, monto AS principal FROM legado.partida_liquidada WHERE concepto = 'PRINCIPAL') p
    WHERE x.id = o.id AND l.orden_id = o.id AND p.orden_id = o.id;
    UPDATE legado.orden_pago SET estatus = 'VENCIDA'
    WHERE estatus = 'ENVIADA' AND fecha_envio < tobe_estado.reloj() - interval '3 days';
END $$;

-- ── la mesa: el estatus de la orden VIGENTE en su operación (parche de r3-T1) ───────────────────────────────────
CREATE FUNCTION tobe_estado.reflejar_estatus_operacion() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    UPDATE legado.operacion o
    SET estatus = CASE v.estatus WHEN 'CONCILIADA' THEN 'PAGADA'
                                 WHEN 'DIFERENCIA' THEN 'PAGADA'
                                 WHEN 'VENCIDA' THEN 'RECHAZADA'
                                 ELSE 'EN_PROCESO' END
    FROM (SELECT DISTINCT ON (operacion_id) operacion_id, estatus FROM legado.orden_pago
          WHERE estatus <> 'REEMPLAZADA' ORDER BY operacion_id, id DESC) v
    WHERE o.id = v.operacion_id;
END $$;

-- ── la contingencia: alta manual que devuelve SU fila (parche de r3-T3). Lo demás se replica tal cual: folio nuevo,
-- fecha de registro del reloj, sin partidas del cliente y sin re-registro (decisión pendiente, como todo ADR 0006). ──
CREATE FUNCTION tobe_estado.alta_manual_orden(
    p_operacion_id integer, p_uetr text, p_referencia_mt103 text, p_fecha_envio timestamp, p_fecha_valor date,
    p_bic_corresponsal text, p_beneficiario text, p_cuenta_beneficiario text, p_moneda text, p_monto numeric,
    p_gastos text) RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    n integer;
    v_folio varchar(20);
    v_id integer;
BEGIN
    UPDATE legado.folio SET siguiente = siguiente + 1, actualizado = tobe_estado.reloj() WHERE serie = 'OP'
    RETURNING siguiente - 1 INTO n;
    v_folio := 'OP-' || right('000000000' || n::text, 9);
    INSERT INTO legado.orden_pago (operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio,
                                   fecha_valor, bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario,
                                   moneda, monto, gastos, estatus)
    VALUES (p_operacion_id, v_folio, p_uetr::char(36), p_referencia_mt103::varchar(16), tobe_estado.reloj(),
            p_fecha_envio, p_fecha_valor, p_bic_corresponsal::char(11), 'NA', p_beneficiario::varchar(120),
            p_cuenta_beneficiario::varchar(34), p_moneda::char(3), p_monto::numeric(18, 2), p_gastos::char(3),
            'ENVIADA')
    RETURNING id INTO v_id;
    RETURN v_id;
END $$;
