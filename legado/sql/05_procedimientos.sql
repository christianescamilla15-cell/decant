USE BFN_DIVISAS;
GO
-- Alta de una operación de divisas. La hora la manda el sistema de la sucursal (hora local).
CREATE OR ALTER PROCEDURE dbo.sp_registrar_operacion
    @fecha_operacion         smalldatetime,
    @sucursal                char(4),
    @canal                   varchar(10),
    @cliente                 nvarchar(120),
    @cuenta_clabe            varchar(18) = NULL,
    @tipo                    char(1),
    @moneda                  char(3),
    @monto_divisa            decimal(18, 2),
    @tipo_cambio_referencia  decimal(18, 6) = NULL,
    @tipo_cambio             decimal(18, 6) = NULL,
    @id                      int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @n int;

    UPDATE dbo.folio SET @n = siguiente, siguiente = siguiente + 1, actualizado = GETDATE() WHERE serie = 'FX';

    IF @tipo_cambio IS NULL
        SET @tipo_cambio = CASE @tipo WHEN 'V' THEN @tipo_cambio_referencia * 1.0035
                                      ELSE @tipo_cambio_referencia * 0.9965 END;

    INSERT INTO dbo.operacion (folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda,
                               monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus)
    VALUES ('FX-' + RIGHT('000000000' + CAST(@n AS varchar(9)), 9), @fecha_operacion, @sucursal, @canal, @cliente,
            ISNULL(@cuenta_clabe, 'NA'), @tipo, @moneda, @monto_divisa, @tipo_cambio,
            ISNULL(@tipo_cambio_referencia, 0), ROUND(@monto_divisa * @tipo_cambio, 2), 'CONCERTADA');

    SET @id = SCOPE_IDENTITY();
END
GO
-- Alta de la orden de pago. La interfaz la vuelve a mandar cada mañana mientras el corresponsal no la liquide.
CREATE OR ALTER PROCEDURE dbo.sp_registrar_orden
    @operacion_id         int,
    @uetr                 char(36),
    @referencia_mt103     varchar(16),
    @fecha_registro       datetime,
    @fecha_envio          datetime,
    @fecha_valor          date,
    @bic_corresponsal     char(11),
    @bic_intermediario    char(11) = NULL,
    @beneficiario         nvarchar(120),
    @cuenta_beneficiario  varchar(34),
    @moneda               char(3),
    @monto                decimal(18, 2),
    @gastos               char(3),
    @codigo_proposito     char(4) = NULL,
    @id                   int OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @anterior int, @folio varchar(20), @n int, @monto_mxn decimal(18, 2), @comision decimal(18, 2);

    SELECT TOP 1 @anterior = id, @folio = folio FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA';

    IF @folio IS NULL
    BEGIN
        UPDATE dbo.folio SET @n = siguiente, siguiente = siguiente + 1, actualizado = GETDATE() WHERE serie = 'OP';
        SET @folio = 'OP-' + RIGHT('000000000' + CAST(@n AS varchar(9)), 9);
    END

    INSERT INTO dbo.orden_pago (operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio, fecha_valor,
                                bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto,
                                gastos, codigo_proposito, estatus)
    VALUES (@operacion_id, @folio, @uetr, @referencia_mt103, @fecha_registro, @fecha_envio, @fecha_valor,
            @bic_corresponsal, ISNULL(@bic_intermediario, 'NA'), @beneficiario, @cuenta_beneficiario, @moneda, @monto,
            @gastos, @codigo_proposito, 'ENVIADA');
    SET @id = SCOPE_IDENTITY();

    IF @anterior IS NOT NULL
        UPDATE dbo.orden_pago SET estatus = 'REEMPLAZADA' WHERE id = @anterior;

    SELECT @monto_mxn = monto_mxn FROM dbo.operacion WHERE id = @operacion_id;
    SET @comision = ROUND(@monto_mxn * 0.0025, 2, 1);
    IF @comision < 150
        SET @comision = 150;

    INSERT INTO dbo.partida_liquidada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
    VALUES (@id, 1, 'PRINCIPAL', @moneda, @monto, @fecha_registro, @folio),
           (@id, 2, 'COMISION', 'MXN', @comision, @fecha_registro, @folio),
           (@id, 3, 'IVA', 'MXN', ROUND(@comision * 0.16, 2), @fecha_registro, @folio);

    IF @gastos = 'OUR'
        INSERT INTO dbo.partida_liquidada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
        VALUES (@id, 4, 'GASTOS_OUR', 'USD', 25.00, @fecha_registro, @folio);
END
GO
-- Confirmación del corresponsal (llega con su hora local).
CREATE OR ALTER PROCEDURE dbo.sp_registrar_liquidacion
    @uetr        char(36),
    @referencia  varchar(35),
    @fecha_hora  datetime,
    @abono       decimal(18, 2),
    @comision    decimal(18, 2) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @id int, @moneda char(3);

    IF EXISTS (SELECT 1 FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA')
    BEGIN
        SELECT TOP 1 @id = id, @moneda = moneda FROM dbo.orden_pago WHERE uetr = @uetr AND estatus = 'ENVIADA';

        INSERT INTO dbo.partida_solicitada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
        VALUES (@id, 1, 'ABONO', @moneda, @abono, @fecha_hora, @referencia);

        IF ISNULL(@comision, 0) > 0
            INSERT INTO dbo.partida_solicitada (orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia)
            VALUES (@id, 2, 'COMISION_CORRESPONSAL', @moneda, @comision, @fecha_hora, @referencia);

        UPDATE dbo.orden_pago SET estatus = 'LIQUIDADA' WHERE id = @id;
    END
END
GO
-- Proceso nocturno (job): concilia lo liquidado y vence lo que no llegó.
CREATE OR ALTER PROCEDURE dbo.sp_conciliar
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (5000) id INTO #lote FROM dbo.orden_pago WHERE estatus = 'LIQUIDADA';

    UPDATE o
    SET horas_liquidacion = DATEDIFF(minute, o.fecha_envio, DATEADD(hour, -1, l.ultima)) / 60.0,
        estatus = CASE WHEN l.abonado = p.principal THEN 'CONCILIADA' ELSE 'DIFERENCIA' END
    FROM dbo.orden_pago o
    JOIN #lote x ON x.id = o.id
    JOIN (SELECT orden_id, SUM(monto) AS abonado, MAX(fecha_hora) AS ultima
          FROM dbo.partida_solicitada GROUP BY orden_id) l ON l.orden_id = o.id
    JOIN (SELECT orden_id, monto AS principal
          FROM dbo.partida_liquidada WHERE concepto = 'PRINCIPAL') p ON p.orden_id = o.id;

    UPDATE dbo.orden_pago
    SET estatus = 'VENCIDA'
    WHERE estatus = 'ENVIADA' AND fecha_envio < DATEADD(day, -3, GETDATE());
END
GO
-- Pantalla: lista de operaciones del día y totales del encabezado (operaciones y órdenes de pago).
CREATE OR ALTER PROCEDURE dbo.sp_lista_operaciones
    @fecha   date = NULL,
    @maximo  int = 200
AS
BEGIN
    SET NOCOUNT ON;
    IF @fecha IS NULL
        SELECT @fecha = CAST(MAX(fecha_operacion) AS date) FROM dbo.operacion;

    SELECT COUNT(*) AS total_operaciones,
           (SELECT COUNT(DISTINCT uetr) FROM dbo.orden_pago) AS total_ordenes
    FROM dbo.operacion;

    SELECT TOP (@maximo) o.id, o.folio, o.fecha_operacion, o.sucursal, o.canal, o.cliente, o.tipo, o.moneda,
           o.monto_divisa, o.tipo_cambio, o.monto_mxn, o.estatus
    FROM dbo.operacion o
    WHERE o.fecha_operacion >= @fecha AND o.fecha_operacion < DATEADD(day, 1, @fecha);
END
GO
-- Pantalla: detalle de una operación con su orden vigente y sus partidas.
CREATE OR ALTER PROCEDURE dbo.sp_detalle_operacion
    @operacion_id int
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @orden int;
    SELECT TOP 1 @orden = id FROM dbo.orden_pago WHERE operacion_id = @operacion_id AND estatus <> 'REEMPLAZADA';

    SELECT o.id, o.folio, o.fecha_operacion, o.sucursal, o.canal, o.cliente, o.cuenta_clabe, o.tipo, o.moneda,
           m.nombre AS nombre_moneda, m.decimales, o.monto_divisa, o.tipo_cambio, o.tipo_cambio_referencia,
           o.monto_mxn, o.estatus,
           p.id AS orden_id, p.folio AS folio_orden, p.uetr, p.referencia_mt103, p.fecha_registro, p.fecha_envio,
           p.fecha_valor, p.bic_corresponsal, p.bic_intermediario, p.beneficiario, p.cuenta_beneficiario,
           p.monto AS monto_orden, p.gastos, p.estatus AS estatus_orden, p.horas_liquidacion
    FROM dbo.operacion o
    LEFT JOIN dbo.moneda m ON m.codigo = o.moneda
    LEFT JOIN dbo.orden_pago p ON p.id = @orden
    WHERE o.id = @operacion_id;

    SELECT renglon, concepto, moneda, monto, fecha_hora, referencia
    FROM dbo.partida_solicitada WHERE orden_id = @orden ORDER BY renglon;

    SELECT renglon, concepto, moneda, monto, fecha_hora, referencia
    FROM dbo.partida_liquidada WHERE orden_id = @orden ORDER BY renglon;
END
GO
-- Reporte de lo abonado por el corresponsal, por fecha valor (un renglón por partida).
CREATE OR ALTER PROCEDURE dbo.sp_reporte_ordenes
    @desde date,
    @hasta date
AS
BEGIN
    SET NOCOUNT ON;
    SELECT folio, uetr, referencia_mt103, fecha_envio, fecha_valor, bic_corresponsal, beneficiario, moneda, monto,
           gastos, estatus, concepto, monto_partida, fecha_partida
    FROM dbo.vw_reporte_ordenes
    WHERE fecha_valor BETWEEN @desde AND @hasta
    ORDER BY fecha_valor;
END
GO
