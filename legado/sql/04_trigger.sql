USE BFN_DIVISAS;
GO
CREATE OR ALTER TRIGGER dbo.tr_orden_pago_bitacora ON dbo.orden_pago
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.bitacora (tabla, llave, accion, estatus_anterior, estatus_nuevo, usuario, fecha)
    SELECT 'orden_pago', i.id, CASE WHEN d.id IS NULL THEN 'I' ELSE 'U' END, d.estatus, i.estatus,
           SUSER_SNAME(), GETDATE()
    FROM inserted i
    LEFT JOIN deleted d ON d.id = i.id;
END
GO
