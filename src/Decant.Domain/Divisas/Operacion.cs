using Decant.Domain.Comun;

namespace Decant.Domain.Divisas;

/// <summary>Lo que entra al alta de una operación (front o archivo de sucursales), ya sin centinelas.</summary>
public sealed record DatosDeOperacion(
    DateTimeOffset FechaOperacion,
    string Sucursal,
    string Canal,
    string Cliente,
    string? CuentaClabe,
    TipoOperacion Tipo,
    string Moneda,
    decimal MontoDivisa,
    decimal? TipoDeCambioReferencia,
    decimal? TipoDeCambioTecleado,
    string Estatus);

/// <summary>Operación de divisas concertada. <see cref="Id"/> es la identidad del legado (orden de llegada).</summary>
public sealed record Operacion(
    long Id,
    string Folio,
    DatosDeOperacion Datos,
    decimal TipoDeCambio,
    decimal MontoMxn)
{
    /// <summary>Alta de la operación: aplica R02 y R03 (folio ya tomado del consumible).</summary>
    public static Resultado<Operacion> Concertar(long id, string folio, DatosDeOperacion datos)
    {
        var tipoDeCambio = ReglasDeCambio.TipoDeCambioAplicado(
            datos.Tipo, datos.TipoDeCambioReferencia, datos.TipoDeCambioTecleado);
        if (!tipoDeCambio.EsExito)
        {
            return tipoDeCambio.Error!;
        }

        var pesos = ReglasDeCambio.MontoEnPesos(datos.MontoDivisa, tipoDeCambio.Valor);
        return new Operacion(id, folio, datos, tipoDeCambio.Valor, pesos);
    }
}
