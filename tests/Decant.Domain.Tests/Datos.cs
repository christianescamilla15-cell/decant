using Decant.Domain.Comun;
using Decant.Domain.Pagos;

namespace Decant.Domain.Tests;

/// <summary>Constructores de datos de prueba (los valores de negocio de cada prueba van en la prueba).</summary>
internal static class Datos
{
    public static readonly DateTimeOffset Instante = new(2023, 12, 1, 16, 0, 0, TimeSpan.Zero);

    public static DatosDeOrden Orden(Gastos gastos = Gastos.Sha, decimal monto = 1000.00m, string moneda = "USD",
        DateTimeOffset? envio = null) =>
        new("BFN231201000001", envio ?? Instante, new DateOnly(2023, 12, 1), "FICTUS33XXX", null, "Great Plains Seed Co.",
            "123456789012345678", moneda, monto, gastos, "SUPP");

    public static DateTimeOffset Mx(int anio, int mes, int dia, int h, int m, int s = 0) =>
        Zonas.AInstante(new DateTime(anio, mes, dia, h, m, s), Zonas.CiudadDeMexico);

    public static DateTimeOffset Ny(int anio, int mes, int dia, int h, int m, int s = 0) =>
        Zonas.AInstante(new DateTime(anio, mes, dia, h, m, s), Zonas.NuevaYork);
}
