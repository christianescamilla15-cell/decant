USE BFN_DIVISAS;
GO
-- Catálogo de monedas (ISO 4217).
CREATE TABLE dbo.moneda (
    codigo      char(3)       NOT NULL CONSTRAINT pk_moneda PRIMARY KEY,
    numerico    char(3)       NOT NULL,
    nombre      nvarchar(60)  NOT NULL,
    decimales   tinyint       NOT NULL,
    activa      bit           NOT NULL CONSTRAINT df_moneda_activa DEFAULT (1)
);
GO
-- Consumibles: siguiente folio de cada serie.
CREATE TABLE dbo.folio (
    serie       varchar(10)   NOT NULL CONSTRAINT pk_folio PRIMARY KEY,
    siguiente   int           NOT NULL,
    actualizado datetime      NOT NULL
);
GO
-- Operación de divisas (compra C / venta V de divisa al cliente).
CREATE TABLE dbo.operacion (
    id                      int IDENTITY(1, 1) NOT NULL CONSTRAINT pk_operacion PRIMARY KEY,
    folio                   varchar(20)    NOT NULL,
    fecha_operacion         smalldatetime  NOT NULL,
    sucursal                char(4)        NOT NULL,
    canal                   varchar(10)    NOT NULL,
    cliente                 nvarchar(120)  NOT NULL,
    cuenta_clabe            varchar(18)    NOT NULL,
    tipo                    char(1)        NOT NULL,
    moneda                  char(3)        NOT NULL CONSTRAINT fk_operacion_moneda REFERENCES dbo.moneda (codigo),
    monto_divisa            decimal(18, 2) NOT NULL,
    tipo_cambio             decimal(18, 6) NOT NULL,
    tipo_cambio_referencia  decimal(18, 6) NOT NULL,
    monto_mxn               decimal(18, 2) NOT NULL,
    estatus                 varchar(12)    NOT NULL
);
GO
CREATE INDEX ix_operacion_fecha ON dbo.operacion (fecha_operacion);
GO
-- Orden de pago internacional (MT103 / pacs.008).
CREATE TABLE dbo.orden_pago (
    id                   int IDENTITY(1, 1) NOT NULL CONSTRAINT pk_orden_pago PRIMARY KEY,
    operacion_id         int            NOT NULL CONSTRAINT fk_orden_operacion REFERENCES dbo.operacion (id),
    folio                varchar(20)    NOT NULL,
    uetr                 char(36)       NOT NULL,
    referencia_mt103     varchar(16)    NOT NULL,
    fecha_registro       datetime       NOT NULL,
    fecha_envio          datetime       NOT NULL,
    fecha_valor          date           NOT NULL,
    bic_corresponsal     char(11)       NOT NULL,
    bic_intermediario    char(11)       NOT NULL,
    beneficiario         nvarchar(120)  NOT NULL,
    cuenta_beneficiario  varchar(34)    NOT NULL,
    moneda               char(3)        NOT NULL CONSTRAINT fk_orden_moneda REFERENCES dbo.moneda (codigo),
    monto                decimal(18, 2) NOT NULL,
    gastos               char(3)        NOT NULL,
    codigo_proposito     char(4)        NULL,
    estatus              varchar(12)    NOT NULL,
    horas_liquidacion    decimal(9, 2)  NULL
);
GO
CREATE INDEX ix_orden_pago_uetr ON dbo.orden_pago (uetr);
CREATE INDEX ix_orden_pago_operacion ON dbo.orden_pago (operacion_id);
GO
-- Partidas de la orden.
CREATE TABLE dbo.partida_solicitada (
    id          int IDENTITY(1, 1) NOT NULL CONSTRAINT pk_partida_solicitada PRIMARY KEY,
    orden_id    int            NOT NULL CONSTRAINT fk_solicitada_orden REFERENCES dbo.orden_pago (id),
    renglon     smallint       NOT NULL,
    concepto    varchar(24)    NOT NULL,
    moneda      char(3)        NOT NULL,
    monto       decimal(18, 2) NOT NULL,
    fecha_hora  datetime       NOT NULL,
    referencia  varchar(35)    NOT NULL
);
GO
CREATE INDEX ix_partida_solicitada_orden ON dbo.partida_solicitada (orden_id);
GO
CREATE TABLE dbo.partida_liquidada (
    id          int IDENTITY(1, 1) NOT NULL CONSTRAINT pk_partida_liquidada PRIMARY KEY,
    orden_id    int            NOT NULL CONSTRAINT fk_liquidada_orden REFERENCES dbo.orden_pago (id),
    renglon     smallint       NOT NULL,
    concepto    varchar(24)    NOT NULL,
    moneda      char(3)        NOT NULL,
    monto       decimal(18, 2) NOT NULL,
    fecha_hora  datetime       NOT NULL,
    referencia  varchar(35)    NOT NULL
);
GO
CREATE INDEX ix_partida_liquidada_orden ON dbo.partida_liquidada (orden_id);
GO
-- Bitácora que llena el trigger de orden_pago.
CREATE TABLE dbo.bitacora (
    id                bigint IDENTITY(1, 1) NOT NULL CONSTRAINT pk_bitacora PRIMARY KEY,
    tabla             sysname        NOT NULL,
    llave             int            NOT NULL,
    accion            char(1)        NOT NULL,
    estatus_anterior  varchar(12)    NULL,
    estatus_nuevo     varchar(12)    NULL,
    usuario           sysname        NOT NULL,
    fecha             datetime       NOT NULL
);
GO
