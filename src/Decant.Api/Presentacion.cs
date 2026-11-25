using Decant.Application.Puertos;
using Decant.Domain.Comun;

namespace Decant.Api;

/// <summary>
/// Cómo publica la API: cada hora en SU zona y con su desfase (la nuestra en la Ciudad de México; la del corresponsal
/// en Nueva York), sin ambigüedad. Las dos listas del detalle llevan el nombre de lo que SON (T4).
/// </summary>
public static class Presentacion
{
    public sealed record Operacion(
        long Id, string Folio, DateTimeOffset FechaOperacion, string Sucursal, string Canal, string Cliente,
        string? CuentaClabe, string Tipo, string Moneda, string? NombreMoneda, int? Decimales, decimal MontoDivisa,
        decimal TipoCambio, decimal? TipoCambioReferencia, decimal MontoMxn, string Estatus);

    public sealed record Orden(
        Guid Uetr, string Folio, string ReferenciaMt103, DateTimeOffset FechaRegistro, int Registros,
        DateTimeOffset FechaEnvio, DateOnly FechaValor, string BicCorresponsal, string? BicIntermediario,
        string Beneficiario, string CuentaBeneficiario, string Moneda, decimal Monto, string Gastos,
        string? CodigoProposito, string Estatus, decimal? HorasLiquidacion);

    public sealed record Partida(short Renglon, string Concepto, string Moneda, decimal Monto,
        DateTimeOffset FechaHora, string Referencia);

    public sealed record Detalle(
        Operacion Operacion, Orden? Orden, IReadOnlyList<Partida> SolicitadoPorElCliente,
        IReadOnlyList<Partida> LiquidadoPorElCorresponsal);

    public static Detalle DeDetalle(DetalleDeOperacion d)
    {
        var o = d.Operacion;
        var operacion = new Operacion(o.Id, o.Folio, Mx(o.FechaOperacion), o.Sucursal, o.Canal, o.Cliente,
            o.CuentaClabe, o.Tipo, o.Moneda, o.NombreMoneda, o.Decimales, o.MontoDivisa, o.TipoCambio,
            o.TipoCambioReferencia, o.MontoMxn, o.Estatus);
        Orden? orden = d.Orden is { } p
            ? new Orden(p.Uetr, p.Folio, p.ReferenciaMt103, Mx(p.FechaRegistro), p.Registros, Mx(p.FechaEnvio),
                p.FechaValor, p.BicCorresponsal, p.BicIntermediario, p.Beneficiario, p.CuentaBeneficiario, p.Moneda,
                p.Monto, p.Gastos, p.CodigoProposito, p.Estatus, p.HorasLiquidacion)
            : null;
        return new Detalle(operacion, orden,
            d.SolicitadoPorElCliente.Select(x => Partida_(x, Zonas.CiudadDeMexico)).ToList(),
            d.LiquidadoPorElCorresponsal.Select(x => Partida_(x, Zonas.NuevaYork)).ToList());
    }

    public static DateTimeOffset Mx(DateTimeOffset instante) => Zonas.EnZona(instante, Zonas.CiudadDeMexico);

    public static DateTimeOffset Ny(DateTimeOffset instante) => Zonas.EnZona(instante, Zonas.NuevaYork);

    private static Partida Partida_(PartidaVista p, TimeZoneInfo zona) =>
        new(p.Renglon, p.Concepto, p.Moneda, p.Monto, Zonas.EnZona(p.FechaHora, zona), p.Referencia);
}
