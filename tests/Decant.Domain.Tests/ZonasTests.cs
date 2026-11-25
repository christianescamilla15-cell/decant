using Decant.Domain.Comun;

namespace Decant.Domain.Tests;

/// <summary>T5: la base de zonas del sistema debe conocer los cambios de horario que cruzan los datos.</summary>
public class ZonasTests
{
    [Theory]
    [InlineData(2022, 7, 1, -5)]   // México todavía con horario de verano
    [InlineData(2022, 11, 15, -6)] // México lo quitó el 30-oct-2022
    [InlineData(2023, 7, 1, -6)]   // sin horario de verano desde entonces
    public void La_ciudad_de_mexico_dejo_el_horario_de_verano_en_octubre_de_2022(int a, int m, int d, int horas) =>
        Assert.Equal(TimeSpan.FromHours(horas), Zonas.CiudadDeMexico.GetUtcOffset(new DateTime(a, m, d, 12, 0, 0)));

    [Fact]
    public void Nueva_york_sigue_con_horario_de_verano_en_2023() =>
        Assert.Equal(TimeSpan.FromHours(-4), Zonas.NuevaYork.GetUtcOffset(new DateTime(2023, 7, 1, 12, 0, 0)));

    [Fact]
    public void En_la_hora_repetida_sin_mas_datos_toma_la_primera_ocurrencia()
    {
        // 31-oct-2021, 01:41:59 en la Ciudad de México ocurrió dos veces (UTC-5 y luego UTC-6)
        var instante = Zonas.AInstante(new DateTime(2021, 10, 31, 1, 41, 59), Zonas.CiudadDeMexico);
        Assert.Equal(new DateTimeOffset(2021, 10, 31, 6, 41, 59, TimeSpan.Zero), instante);
        Assert.True(Zonas.EsAmbigua(new DateTime(2021, 10, 31, 1, 41, 59), Zonas.CiudadDeMexico));
    }

    /// <summary>
    /// Defecto encontrado por la paridad (R04, 5 folios OP): orden_pago.id 68199 se registró a las 01:41:59 y el 68200,
    /// que llegó DESPUÉS, a las 01:19:50. Con la primera ocurrencia para los dos, el 68200 quedaba antes y tomaba otro
    /// folio. El orden de llegada dice que fue la segunda vuelta de la hora.
    /// </summary>
    [Fact]
    public void En_la_hora_repetida_decide_el_orden_de_llegada()
    {
        var anterior = new DateTimeOffset(2021, 10, 31, 6, 41, 59, TimeSpan.Zero);
        var siguiente = Zonas.AInstanteNoAntesDe(new DateTime(2021, 10, 31, 1, 19, 50), Zonas.CiudadDeMexico, anterior);
        Assert.Equal(new DateTimeOffset(2021, 10, 31, 7, 19, 50, TimeSpan.Zero), siguiente);
        var primero = Zonas.AInstanteNoAntesDe(new DateTime(2021, 10, 31, 1, 41, 59), Zonas.CiudadDeMexico,
            new DateTimeOffset(2021, 10, 31, 6, 30, 0, TimeSpan.Zero));
        Assert.Equal(anterior, primero);
    }

    [Fact]
    public void Fuera_de_la_hora_repetida_el_orden_de_llegada_no_cambia_nada() =>
        Assert.Equal(Datos.Mx(2023, 12, 1, 10, 0),
            Zonas.AInstanteNoAntesDe(new DateTime(2023, 12, 1, 10, 0, 0), Zonas.CiudadDeMexico, Datos.Mx(2023, 12, 1, 11, 0)));

    [Fact]
    public void Ida_y_vuelta_a_la_hora_local_conserva_la_hora_del_legado()
    {
        var local = new DateTime(2022, 3, 20, 5, 55, 9);
        Assert.Equal(local, Zonas.ALocal(Zonas.AInstante(local, Zonas.CiudadDeMexico), Zonas.CiudadDeMexico));
    }
}
