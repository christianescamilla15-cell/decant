using Decant.Domain.Comun;

namespace Decant.Domain.Divisas;

/// <summary>Reglas del alta de una operación (origen: <c>dbo.sp_registrar_operacion</c>).</summary>
public static class ReglasDeCambio
{
    /// <summary>Margen sobre la referencia cuando el cajero no teclea el tipo de cambio: venta.</summary>
    public const decimal MargenVenta = 1.0035m;

    /// <summary>Margen sobre la referencia cuando el cajero no teclea el tipo de cambio: compra.</summary>
    public const decimal MargenCompra = 0.9965m;

    /// <summary>
    /// R02. Si el cajero tecleó el tipo de cambio, ése es; si no, la referencia por el margen, redondeado a 6
    /// decimales lejos del cero (la conversión implícita a <c>decimal(18,6)</c> de SQL Server).
    /// </summary>
    public static Resultado<decimal> TipoDeCambioAplicado(TipoOperacion tipo, decimal? referencia, decimal? tecleado)
    {
        if (tecleado is { } directo)
        {
            return directo;
        }

        if (referencia is not { } valor)
        {
            return new Error("sin_tipo_de_cambio", "ni tipo de cambio tecleado ni referencia");
        }

        var margen = tipo == TipoOperacion.Venta ? MargenVenta : MargenCompra;
        return Math.Round(valor * margen, 6, MidpointRounding.AwayFromZero);
    }

    /// <summary>R03. <c>ROUND(monto_divisa × tipo_cambio, 2)</c>: mitad lejos del cero.</summary>
    public static decimal MontoEnPesos(decimal montoDivisa, decimal tipoDeCambio) =>
        Math.Round(montoDivisa * tipoDeCambio, 2, MidpointRounding.AwayFromZero);
}
