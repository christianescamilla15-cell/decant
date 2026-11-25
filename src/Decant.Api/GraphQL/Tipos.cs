using Decant.Application.Puertos;
using Decant.Domain.Comun;
using HotChocolate;
using HotChocolate.CostAnalysis.Types;

namespace Decant.Api.GraphQL;

// Los tipos del esquema de lectura. Son registros PROPIOS de la API (no los de la aplicación): la forma del esquema
// se decide aquí y el SDL versionado (esquema.graphql) la fija. Cada hora sale en SU zona, igual que en REST.

[GraphQLDescription("Una operación de divisas. Equivale al objeto «operacion» de GET /api/operaciones/{id}.")]
public sealed record Operacion(
    long Id,
    string Folio,
    [property: GraphQLDescription("Instante de la operación con el desfase de la Ciudad de México.")]
    DateTimeOffset FechaOperacion,
    string Sucursal,
    string Canal,
    string Cliente,
    [property: GraphQLDescription("CLABE del cliente; nula donde el legado guardaba el centinela «NA» (T3).")]
    string? CuentaClabe,
    string Tipo,
    string Moneda,
    string? NombreMoneda,
    int? Decimales,
    decimal MontoDivisa,
    decimal TipoCambio,
    [property: GraphQLDescription("Tipo de cambio de referencia; nulo donde el legado guardaba 0 (T3).")]
    decimal? TipoCambioReferencia,
    decimal MontoMxn,
    string Estatus)
{
    [GraphQLDescription("El documento de pago de la operación (el registro más reciente) o nulo si no tiene.")]
    public Task<Orden?> GetOrdenAsync(OrdenesPorOperacion cargador, CancellationToken ct) =>
        cargador.LoadAsync(Id, ct);

    internal static Operacion De(OperacionVista o) => new(o.Id, o.Folio, Presentacion.Mx(o.FechaOperacion),
        o.Sucursal, o.Canal, o.Cliente, o.CuentaClabe, o.Tipo, o.Moneda, o.NombreMoneda, o.Decimales, o.MontoDivisa,
        o.TipoCambio, o.TipoCambioReferencia, o.MontoMxn, o.Estatus);
}

[GraphQLDescription("Una orden de pago: un DOCUMENTO por UETR (sus re-registros no son órdenes nuevas, T9).")]
public sealed record Orden(
    Guid Uetr,
    string Folio,
    string ReferenciaMt103,
    DateTimeOffset FechaRegistro,
    int Registros,
    DateTimeOffset FechaEnvio,
    DateOnly FechaValor,
    string BicCorresponsal,
    string? BicIntermediario,
    string Beneficiario,
    string CuentaBeneficiario,
    string Moneda,
    decimal Monto,
    string Gastos,
    string? CodigoProposito,
    [property: GraphQLDescription("ENVIADA, CONCILIADA, DIFERENCIA o VENCIDA.")]
    string Estatus,
    [property: GraphQLDescription("Horas de liquidación (R08: réplica del cálculo del legado, ADR 0006).")]
    decimal? HorasLiquidacion,
    [property: GraphQLIgnore] long OperacionId)
{
    /// <summary>
    /// A lo más 4 por lado (R05: principal, comisión, IVA y gastos OUR; R06: abono y comisión del corresponsal):
    /// es el tamaño que supone el análisis de costo para estas listas.
    /// </summary>
    internal const int PartidasPorLado = 4;

    [GraphQLDescription("La operación de la que nace el documento.")]
    public Task<Operacion> GetOperacionAsync(OperacionesPorId cargador, CancellationToken ct) =>
        cargador.LoadRequiredAsync(OperacionId, ct);

    [GraphQLDescription("Lo que pidió el cliente (en el legado, la tabla mal llamada partida_liquidada, T4).")]
    [ListSize(AssumedSize = PartidasPorLado, RequireOneSlicingArgument = false)]
    public async Task<IReadOnlyList<Partida>> GetSolicitadoPorElClienteAsync(SolicitadoPorElCliente cargador,
        CancellationToken ct) => await cargador.LoadAsync(Uetr, ct) ?? [];

    [GraphQLDescription("Lo que abonó el corresponsal (en el legado, la tabla mal llamada partida_solicitada, T4).")]
    [ListSize(AssumedSize = PartidasPorLado, RequireOneSlicingArgument = false)]
    public async Task<IReadOnlyList<Partida>> GetLiquidadoPorElCorresponsalAsync(LiquidadoPorElCorresponsal cargador,
        CancellationToken ct) => await cargador.LoadAsync(Uetr, ct) ?? [];

    internal static Orden De(long operacionId, OrdenVista o) => new(o.Uetr, o.Folio, o.ReferenciaMt103,
        Presentacion.Mx(o.FechaRegistro), o.Registros, Presentacion.Mx(o.FechaEnvio), o.FechaValor, o.BicCorresponsal,
        o.BicIntermediario, o.Beneficiario, o.CuentaBeneficiario, o.Moneda, o.Monto, o.Gastos, o.CodigoProposito,
        o.Estatus, o.HorasLiquidacion, operacionId);
}

[GraphQLDescription("Una partida de la orden; su hora va en la zona de quien la registró.")]
public sealed record Partida(
    short Renglon,
    string Concepto,
    string Moneda,
    decimal Monto,
    [property: GraphQLDescription("Ciudad de México si la pidió el cliente; Nueva York si la abonó el corresponsal.")]
    DateTimeOffset FechaHora,
    string Referencia)
{
    internal static Partida De(PartidaVista p, TimeZoneInfo zona) =>
        new(p.Renglon, p.Concepto, p.Moneda, p.Monto, Zonas.EnZona(p.FechaHora, zona), p.Referencia);
}

[GraphQLDescription("Un renglón del reporte de lo abonado: uno por partida del corresponsal (T2, ADR 0006).")]
public sealed record RenglonDeReporte(
    string Folio,
    Guid Uetr,
    string ReferenciaMt103,
    DateTimeOffset FechaEnvio,
    DateOnly FechaValor,
    string BicCorresponsal,
    string Beneficiario,
    string Moneda,
    decimal Monto,
    string Gastos,
    string Estatus,
    string Concepto,
    decimal MontoPartida,
    [property: GraphQLDescription("Hora de la partida en Nueva York, la zona del corresponsal.")]
    DateTimeOffset FechaPartida)
{
    internal static RenglonDeReporte De(Decant.Application.Puertos.RenglonDeReporte r) => new(r.Folio, r.Uetr,
        r.ReferenciaMt103, Presentacion.Mx(r.FechaEnvio), r.FechaValor, r.BicCorresponsal, r.Beneficiario, r.Moneda,
        r.Monto, r.Gastos, r.Estatus, r.Concepto, r.MontoPartida, Presentacion.Ny(r.FechaPartida));
}
