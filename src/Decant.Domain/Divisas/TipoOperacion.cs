using Decant.Domain.Comun;

namespace Decant.Domain.Divisas;

/// <summary>Compra (C) o venta (V) de divisa al cliente, con el código de una letra del legado.</summary>
public enum TipoOperacion
{
    Compra,
    Venta,
}

public static class TiposDeOperacion
{
    public static Resultado<TipoOperacion> DesdeCodigo(string codigo) => codigo.TrimEnd(' ') switch
    {
        "C" => TipoOperacion.Compra,
        "V" => TipoOperacion.Venta,
        _ => new Error("tipo_operacion_desconocido", $"tipo de operación desconocido: «{codigo}»"),
    };

    public static string Codigo(TipoOperacion tipo) => tipo == TipoOperacion.Venta ? "V" : "C";
}
