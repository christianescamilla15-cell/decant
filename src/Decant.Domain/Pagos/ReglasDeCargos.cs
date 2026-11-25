namespace Decant.Domain.Pagos;

/// <summary>Lo que se le cobra al cliente por una orden (origen: <c>dbo.sp_registrar_orden</c>).</summary>
public static class ReglasDeCargos
{
    public const decimal TasaComision = 0.0025m;
    public const decimal ComisionMinima = 150.00m;
    public const decimal TasaIva = 0.16m;
    public const decimal GastosOurUsd = 25.00m;

    /// <summary>
    /// R05 / D1. <c>ROUND(@monto_mxn * 0.0025, 2, 1)</c>: el tercer argumento TRUNCA. Se replica mientras negocio no
    /// decida (ADR 0006, pregunta cerrada D1); con un mínimo de 150.
    /// </summary>
    public static decimal Comision(decimal montoMxnOperacion)
    {
        var truncada = Math.Truncate(montoMxnOperacion * TasaComision * 100m) / 100m;
        return truncada < ComisionMinima ? ComisionMinima : truncada;
    }

    /// <summary><c>ROUND(@comision * 0.16, 2)</c>: mitad lejos del cero.</summary>
    public static decimal Iva(decimal comision) => Math.Round(comision * TasaIva, 2, MidpointRounding.AwayFromZero);

    /// <summary>Las partidas «solicitado por el cliente» de un registro de la orden.</summary>
    public static IReadOnlyList<Partida> SolicitadoPorElCliente(
        DatosDeOrden datos, decimal montoMxnOperacion, DateTimeOffset fechaRegistro, string folio)
    {
        var comision = Comision(montoMxnOperacion);
        var partidas = new List<Partida>(4)
        {
            new(1, Conceptos.Principal, datos.Moneda, datos.Monto, fechaRegistro, folio),
            new(2, Conceptos.Comision, "MXN", comision, fechaRegistro, folio),
            new(3, Conceptos.Iva, "MXN", Iva(comision), fechaRegistro, folio),
        };
        if (datos.Gastos == Gastos.Our)
        {
            partidas.Add(new Partida(4, Conceptos.GastosOur, "USD", GastosOurUsd, fechaRegistro, folio));
        }

        return partidas;
    }
}
