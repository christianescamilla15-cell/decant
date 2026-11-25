namespace Decant.Infrastructure.Persistencia;

// Filas de PostgreSQL. El dominio no las conoce: el almacén las arma desde los agregados y las consultas las
// proyectan a los modelos de lectura de la aplicación.
#pragma warning disable CA1819

public sealed class MonedaFila
{
    public required string Codigo { get; set; }
    public required string Numerico { get; set; }
    public required string Nombre { get; set; }
    public short Decimales { get; set; }
    public bool Activa { get; set; }
}

/// <summary>Consumibles de folio (en el legado, <c>dbo.folio</c>).</summary>
public sealed class ConsecutivoFila
{
    public required string Serie { get; set; }
    public int Siguiente { get; set; }
}

public sealed class OperacionFila
{
    public long Id { get; set; }
    public required string Folio { get; set; }
    public DateTimeOffset FechaOperacion { get; set; }
    public required string Sucursal { get; set; }
    public required string Canal { get; set; }
    public required string Cliente { get; set; }
    public string? CuentaClabe { get; set; }
    public required string Tipo { get; set; }
    public required string Moneda { get; set; }
    public decimal MontoDivisa { get; set; }
    public decimal TipoCambio { get; set; }
    public decimal? TipoCambioReferencia { get; set; }
    public decimal MontoMxn { get; set; }
    public required string Estatus { get; set; }
}

/// <summary>Una orden de pago = un DOCUMENTO (llave natural UETR). Sus altas viven en <see cref="RegistroFila"/>.</summary>
public sealed class OrdenFila
{
    public Guid Uetr { get; set; }
    public required string Folio { get; set; }
    public long OperacionId { get; set; }
    public required string ReferenciaMt103 { get; set; }
    public DateTimeOffset FechaRegistro { get; set; }
    public int Registros { get; set; }
    public DateTimeOffset FechaEnvio { get; set; }
    public DateOnly FechaValor { get; set; }
    public required string BicCorresponsal { get; set; }
    public string? BicIntermediario { get; set; }
    public required string Beneficiario { get; set; }
    public required string CuentaBeneficiario { get; set; }
    public required string Moneda { get; set; }
    public decimal Monto { get; set; }
    public required string Gastos { get; set; }
    public string? CodigoProposito { get; set; }
    public required string Estatus { get; set; }
    public decimal? HorasLiquidacion { get; set; }
    public required string VersionDeReglas { get; set; }
}

public sealed class RegistroFila
{
    public Guid Uetr { get; set; }
    public int Numero { get; set; }
    public DateTimeOffset Instante { get; set; }
    public long? IdLegado { get; set; }
}

/// <summary>«Solicitado por el cliente» (en el legado, <c>dbo.partida_liquidada</c>: el nombre está cruzado, T4).</summary>
public sealed class PartidaClienteFila
{
    public Guid Uetr { get; set; }
    public short Renglon { get; set; }
    public required string Concepto { get; set; }
    public required string Moneda { get; set; }
    public decimal Monto { get; set; }
    public DateTimeOffset FechaHora { get; set; }
    public required string Referencia { get; set; }
}

/// <summary>«Liquidado por el corresponsal» (en el legado, <c>dbo.partida_solicitada</c>, T4).</summary>
public sealed class PartidaCorresponsalFila
{
    public Guid Uetr { get; set; }
    public short Renglon { get; set; }
    public required string Concepto { get; set; }
    public required string Moneda { get; set; }
    public decimal Monto { get; set; }
    public DateTimeOffset FechaHora { get; set; }
    public required string Referencia { get; set; }
}

public sealed class LiquidacionDescartadaFila
{
    public long Id { get; set; }
    public Guid Uetr { get; set; }
    public required string ReferenciaMt103 { get; set; }
    public required string TrnCorresponsal { get; set; }
    public DateTimeOffset Instante { get; set; }
    public decimal Abono { get; set; }
    public decimal Comision { get; set; }
    public required string Motivo { get; set; }
}

public sealed class MarcaFila
{
    public long Id { get; set; }
    public required string Regla { get; set; }
    public required string Caso { get; set; }
    public DateTimeOffset Instante { get; set; }
    public bool Cumple { get; set; }
    public required string Detalle { get; set; }
}

public sealed class CorridaFila
{
    public int Id { get; set; }
    public required string Tipo { get; set; }
    public required string VersionDeReglas { get; set; }
    public DateTimeOffset Inicio { get; set; }
    public DateTimeOffset? Hasta { get; set; }
    public string? Banderas { get; set; }
    public required string Origen { get; set; }
}
