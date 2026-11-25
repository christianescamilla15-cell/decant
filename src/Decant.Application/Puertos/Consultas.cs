namespace Decant.Application.Puertos;

public sealed record OperacionVista(
    long Id, string Folio, DateTimeOffset FechaOperacion, string Sucursal, string Canal, string Cliente,
    string? CuentaClabe, string Tipo, string Moneda, string? NombreMoneda, int? Decimales, decimal MontoDivisa,
    decimal TipoCambio, decimal? TipoCambioReferencia, decimal MontoMxn, string Estatus);

public sealed record OrdenVista(
    Guid Uetr, string Folio, string ReferenciaMt103, DateTimeOffset FechaRegistro, int Registros,
    DateTimeOffset FechaEnvio, DateOnly FechaValor, string BicCorresponsal, string? BicIntermediario,
    string Beneficiario, string CuentaBeneficiario, string Moneda, decimal Monto, string Gastos,
    string? CodigoProposito, string Estatus, decimal? HorasLiquidacion);

public sealed record PartidaVista(
    short Renglon, string Concepto, string Moneda, decimal Monto, DateTimeOffset FechaHora, string Referencia);

/// <summary>El detalle de una operación: las dos listas con el nombre de lo que SON (lo que ve el usuario), no el de
/// la tabla del legado (T4).</summary>
public sealed record DetalleDeOperacion(
    OperacionVista Operacion,
    OrdenVista? Orden,
    IReadOnlyList<PartidaVista> SolicitadoPorElCliente,
    IReadOnlyList<PartidaVista> LiquidadoPorElCorresponsal);

public sealed record RenglonDeReporte(
    string Folio, Guid Uetr, string ReferenciaMt103, DateTimeOffset FechaEnvio, DateOnly FechaValor,
    string BicCorresponsal, string Beneficiario, string Moneda, decimal Monto, string Gastos, string Estatus,
    string Concepto, decimal MontoPartida, DateTimeOffset FechaPartida);

public sealed record OperacionDeLista(
    long Id, string Folio, DateTimeOffset FechaOperacion, string Sucursal, string Canal, string Cliente, string Tipo,
    string Moneda, decimal MontoDivisa, decimal TipoCambio, decimal MontoMxn, string Estatus);

public interface IConsultasTobe
{
    Task<DetalleDeOperacion?> DetalleAsync(long operacionId, CancellationToken ct);

    Task<IReadOnlyList<RenglonDeReporte>> ReporteDeOrdenesAsync(DateOnly desde, DateOnly hasta, CancellationToken ct);

    Task<IReadOnlyList<OperacionDeLista>> ListaAsync(DateOnly fecha, int maximo, CancellationToken ct);
}
