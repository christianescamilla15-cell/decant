using Decant.Application;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Conciliacion;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;

namespace Decant.Infrastructure.Tests;

/// <summary>Un estado pequeño del TO-BE con las formas que importan: centinelas en NULL, re-registro, liquidación
/// con comisión del corresponsal, una vencida sin partidas del corresponsal y una operación sin orden.</summary>
public static class Escenario
{
    public static readonly Guid Conciliada = Guid.Parse("3edcbeae-c21e-40f1-b309-430eca67e133");
    public static readonly Guid Vencida = Guid.Parse("8a235e0d-82f7-4b1c-beff-439ed3620b32");
    public static readonly Guid MismaFecha = Guid.Parse("b34b9ba7-b64f-4480-9fb1-2bc85e070f8d");

    public static DateTimeOffset Mx(int a, int m, int d, int h, int mi, int s = 0) =>
        Zonas.AInstante(new DateTime(a, m, d, h, mi, s), Zonas.CiudadDeMexico);

    private static Operacion Operacion(long id, DateTimeOffset fecha, string? clabe, decimal? referencia,
        decimal? tecleado) =>
        Decant.Domain.Divisas.Operacion.Concertar(id, Consecutivos.Formatear("FX", (int)id), new DatosDeOperacion(fecha,
            "0001", "VENTANILLA", "ARTESANÍAS DEL LAGO, S.C.", clabe, TipoOperacion.Venta, "USD", 1000.00m, referencia,
            tecleado, "CONCERTADA")).Valor;

    private static DatosDeOrden Orden(string referencia, DateTimeOffset envio, DateOnly valor, Gastos gastos) =>
        new(referencia, envio, valor, "FICTUS33XXX", null, "Great Plains Seed Co.", "123456789012345678", "USD",
            1000.00m, gastos, "SUPP");

    public static EstadoTobe Estado()
    {
        var operaciones = new List<Operacion>
        {
            Operacion(1, Mx(2023, 12, 1, 10, 0), null, null, 19.9392m),          // efectivo y tc tecleado (T3)
            Operacion(2, Mx(2023, 12, 1, 23, 30), "987320396284801163", 19.859734m, null), // 23:30 local = 05:30Z del 2
            Operacion(3, Mx(2023, 12, 1, 10, 0), "987580227423300363", 19.859734m, null),  // mismo minuto que la 1
            Operacion(4, Mx(2023, 12, 2, 9, 0), null, 19.859734m, null),          // sin orden
        };
        var valor = new DateOnly(2023, 12, 4);
        var conciliada = OrdenDePago.Registrar(Conciliada, "OP-000000002", 1,
            Orden("BFN231201000001", Mx(2023, 12, 1, 10, 5, 30), valor, Gastos.Our), operaciones[0].MontoMxn,
            Mx(2023, 12, 1, 10, 5), 10);
        conciliada.ReRegistrar(Orden("BFN231201000001", Mx(2023, 12, 1, 10, 5, 30), valor, Gastos.Our),
            operaciones[0].MontoMxn, Mx(2023, 12, 4, 7, 0), 12);
        conciliada.RegistrarLiquidacion(new ConfirmacionDelCorresponsal(Conciliada, "BFN231201000001",
            "FICT000000000001", new DateTime(2023, 12, 4, 9, 15, 42), TimeSpan.FromHours(-5), valor, "USD", 988.50m,
            11.50m));
        conciliada.Conciliar(conciliada.EvaluarConciliacion()!);
        var vencida = OrdenDePago.Registrar(Vencida, "OP-000000001", 2,
            Orden("BFN231201000002", Mx(2023, 12, 1, 23, 35, 30), valor, Gastos.Sha), operaciones[1].MontoMxn,
            Mx(2023, 12, 1, 23, 35), 11);
        vencida.Vencer();
        var mismaFecha = OrdenDePago.Registrar(MismaFecha, "OP-000000003", 3,
            Orden("BFN231201000003", Mx(2023, 12, 1, 10, 6), valor, Gastos.Ben), operaciones[2].MontoMxn,
            Mx(2023, 12, 1, 10, 5, 40), 13);
        mismaFecha.RegistrarLiquidacion(new ConfirmacionDelCorresponsal(MismaFecha, "BFN231201000003",
            "FICT000000000003", new DateTime(2023, 12, 4, 9, 20, 0), TimeSpan.FromHours(-5), valor, "USD", 1000.00m, 0m));
        return new EstadoTobe(
            new Corrida("prueba", VersionDeReglas.Actual, Mx(2026, 11, 24, 12, 0), null, Banderas.Todas, "escenario"),
            [new Moneda("USD", "840", "Dólar estadounidense", 2, true)],
            new Dictionary<string, int> { ["FX"] = 5, ["OP"] = 4 },
            operaciones,
            [conciliada, vencida, mismaFecha],
            [new LiquidacionDescartada(Vencida, "BFN231201000002", "FICT000000000002", Mx(2023, 12, 6, 8, 0), 1000m, 0m,
                "documento VENCIDA")],
            [new Marca("R10-vencimiento", Vencida.ToString(), Mx(2023, 12, 4, 23, 30), true, "prueba")]);
    }

    /// <summary>
    /// Bordes de fecha: el último segundo y el primer instante de cada día LOCAL, el día de 25 horas (fin del horario
    /// de verano, 30-oct-2022) y el de 23 (inicio, 3-abr-2022); y tres fechas valor seguidas para los rangos.
    /// </summary>
    public static EstadoTobe Bordes()
    {
        var operaciones = new List<Operacion>
        {
            Operacion(21, Mx(2022, 10, 29, 23, 59, 59), null, null, 19.9m), // 04:59:59Z del 30 (desfase -5)
            Operacion(22, Mx(2022, 10, 30, 0, 0, 0), null, null, 19.9m),    // 05:00:00Z del 30
            Operacion(23, Mx(2022, 10, 30, 23, 59, 59), null, null, 19.9m), // 05:59:59Z del 31 (ya con -6)
            Operacion(24, Mx(2022, 10, 31, 0, 0, 0), null, null, 19.9m),    // 06:00:00Z del 31
            Operacion(25, Mx(2022, 4, 3, 23, 59, 59), null, null, 19.9m),   // el día de 23 horas
            Operacion(26, Mx(2022, 4, 4, 0, 0, 0), null, null, 19.9m),
        };
        var ordenes = new List<OrdenDePago>();
        var uetrs = new[] { Guid.Parse("0c6f3f3e-5a52-4f11-9d0e-2f9b1d1a0001"),
            Guid.Parse("0c6f3f3e-5a52-4f11-9d0e-2f9b1d1a0002"), Guid.Parse("0c6f3f3e-5a52-4f11-9d0e-2f9b1d1a0003") };
        for (var i = 0; i < 3; i++)
        {
            var valor = new DateOnly(2022, 10, 28).AddDays(i * 3); // 28-oct, 31-oct y 3-nov
            var referencia = $"BFN22102800000{i + 1}";
            var orden = OrdenDePago.Registrar(uetrs[i], $"OP-00000001{i}", 21 + i,
                Orden(referencia, Mx(2022, 10, 27, 10, i), valor, Gastos.Sha), operaciones[i].MontoMxn,
                Mx(2022, 10, 27, 10, i), 100 + i);
            orden.RegistrarLiquidacion(new ConfirmacionDelCorresponsal(uetrs[i], referencia, $"FICT00000000010{i}",
                new DateTime(2022, 10, 28 + i, 9, 0, 0), TimeSpan.FromHours(-4), valor, "USD", 1000.00m, 0m));
            ordenes.Add(orden);
        }

        return new EstadoTobe(
            new Corrida("bordes", VersionDeReglas.Actual, Mx(2026, 11, 25, 12, 0), null, Banderas.Todas, "escenario"),
            [new Moneda("USD", "840", "Dólar estadounidense", 2, true)],
            new Dictionary<string, int> { ["FX"] = 27, ["OP"] = 13 },
            operaciones, ordenes, [], []);
    }
}
