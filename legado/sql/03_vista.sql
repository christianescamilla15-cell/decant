USE BFN_DIVISAS;
GO
-- Órdenes con lo que abonó el corresponsal (base del reporte de órdenes).
CREATE OR ALTER VIEW dbo.vw_reporte_ordenes
AS
SELECT o.id, o.folio, o.uetr, o.referencia_mt103, o.fecha_envio, o.fecha_valor, o.bic_corresponsal,
       o.beneficiario, o.moneda, o.monto, o.gastos, o.estatus,
       p.concepto, p.monto AS monto_partida, p.fecha_hora AS fecha_partida
FROM dbo.orden_pago o
INNER JOIN dbo.partida_solicitada p ON p.orden_id = o.id
WHERE o.estatus <> 'REEMPLAZADA';
GO
-- Liquidaciones del corresponsal, las más recientes primero (base de la consulta de tesorería).
CREATE OR ALTER VIEW dbo.vw_liquidaciones_recientes
AS
SELECT TOP 100 PERCENT p.folio, p.uetr, p.bic_corresponsal, p.moneda, s.monto, s.fecha_hora, s.referencia
FROM dbo.partida_solicitada s
INNER JOIN dbo.orden_pago p ON p.id = s.orden_id
WHERE s.concepto = 'ABONO'
ORDER BY s.fecha_hora DESC;
GO
