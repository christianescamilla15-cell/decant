using Decant.Domain.Comun;

namespace Decant.Domain.Pagos;

/// <summary>Estatus de un DOCUMENTO (llave natural: UETR). «REEMPLAZADA» del legado no es un estatus del documento:
/// es la huella del re-registro (T9) y en el TO-BE vive en <see cref="RegistroDeOrden"/>.</summary>
public enum EstatusOrden
{
    Enviada,
    Liquidada,
    Conciliada,
    Diferencia,
    Vencida,
}

public static class EstatusDeOrden
{
    public static string Codigo(EstatusOrden estatus) => estatus switch
    {
        EstatusOrden.Enviada => "ENVIADA",
        EstatusOrden.Liquidada => "LIQUIDADA",
        EstatusOrden.Conciliada => "CONCILIADA",
        EstatusOrden.Diferencia => "DIFERENCIA",
        EstatusOrden.Vencida => "VENCIDA",
        _ => throw new ArgumentOutOfRangeException(nameof(estatus)),
    };

    public static Resultado<EstatusOrden> DesdeCodigo(string codigo) => codigo switch
    {
        "ENVIADA" => EstatusOrden.Enviada,
        "LIQUIDADA" => EstatusOrden.Liquidada,
        "CONCILIADA" => EstatusOrden.Conciliada,
        "DIFERENCIA" => EstatusOrden.Diferencia,
        "VENCIDA" => EstatusOrden.Vencida,
        _ => new Error("estatus_desconocido", $"estatus de documento desconocido: «{codigo}»"),
    };
}

/// <summary>Quién paga los gastos (MT103 :71A:).</summary>
public enum Gastos
{
    Our,
    Sha,
    Ben,
}

public static class CodigosDeGastos
{
    public static Resultado<Gastos> DesdeCodigo(string codigo) => codigo.TrimEnd(' ') switch
    {
        "OUR" => Gastos.Our,
        "SHA" => Gastos.Sha,
        "BEN" => Gastos.Ben,
        _ => new Error("gastos_desconocidos", $"código de gastos desconocido: «{codigo}»"),
    };

    public static string Codigo(Gastos gastos) => gastos.ToString().ToUpperInvariant();
}

/// <summary>Conceptos de las dos listas hermanas del detalle (T4: el NOMBRE de la tabla del legado está cruzado).</summary>
public static class Conceptos
{
    public const string Principal = "PRINCIPAL";
    public const string Comision = "COMISION";
    public const string Iva = "IVA";
    public const string GastosOur = "GASTOS_OUR";
    public const string Abono = "ABONO";
    public const string ComisionCorresponsal = "COMISION_CORRESPONSAL";
}

/// <summary>Renglón de una de las dos listas: lo solicitado por el cliente o lo liquidado por el corresponsal.</summary>
public sealed record Partida(
    short Renglon,
    string Concepto,
    string Moneda,
    decimal Monto,
    DateTimeOffset FechaHora,
    string Referencia);

/// <summary>Lo que entra con cada alta o re-registro de la orden (interfaz de órdenes), ya sin centinelas.</summary>
public sealed record DatosDeOrden(
    string ReferenciaMt103,
    DateTimeOffset FechaEnvio,
    DateOnly FechaValor,
    string BicCorresponsal,
    string? BicIntermediario,
    string Beneficiario,
    string CuentaBeneficiario,
    string Moneda,
    decimal Monto,
    Gastos Gastos,
    string? CodigoProposito);

/// <summary>Cada vez que la interfaz dio de alta el documento (T9). <see cref="IdLegado"/> es la llave interna que
/// el legado le asignó a esa fila; sólo sirve de rastro.</summary>
public sealed record RegistroDeOrden(int Numero, DateTimeOffset Instante, long? IdLegado);
