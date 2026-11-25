using Decant.Infrastructure.Persistencia;

namespace Decant.Infrastructure.Tests;

/// <summary>
/// Comparaciones de fecha que EF traduce a SQL, contra PostgreSQL real y en sus bordes: el día local (medianoche
/// exacta y el último segundo, días de 23 y 25 horas) y los rangos de fecha valor (<c>date</c>, inclusivos).
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class ConsultasEnBordesTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    public async Task InitializeAsync()
    {
        await using var contexto = baseDePrueba.Contexto();
        await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Bordes(), default);
    }

    public Task DisposeAsync() => Task.CompletedTask;

    private async Task<long[]> Dia(int a, int m, int d)
    {
        await using var contexto = baseDePrueba.Contexto();
        return (await new ConsultasEf(contexto).ListaAsync(new DateOnly(a, m, d), 100, default))
            .Select(o => o.Id).ToArray();
    }

    [Fact]
    public async Task El_dia_local_incluye_su_medianoche_y_su_ultimo_segundo()
    {
        Assert.Equal(new long[] { 21L }, await Dia(2022, 10, 29));
        Assert.Equal(new long[] { 22L, 23L }, await Dia(2022, 10, 30)); // 25 horas: de 05:00Z del 30 a 06:00Z del 31
        Assert.Equal(new long[] { 24L }, await Dia(2022, 10, 31));
        Assert.Equal(new long[] { 25L }, await Dia(2022, 4, 3));        // 23 horas
        Assert.Equal(new long[] { 26L }, await Dia(2022, 4, 4));
    }

    [Theory]
    [InlineData("2022-10-31", "2022-10-31", new[] { "OP-000000011" })]                 // desde = hasta
    [InlineData("2022-10-28", "2022-10-31", new[] { "OP-000000010", "OP-000000011" })] // ambos bordes entran
    [InlineData("2022-10-29", "2022-11-02", new[] { "OP-000000011" })]
    [InlineData("2022-10-29", "2022-10-30", new string[0])]                            // entre dos fechas valor
    [InlineData("2022-11-03", "2022-10-28", new string[0])]                            // rango invertido: vacío
    public async Task El_rango_de_fecha_valor_es_inclusivo_y_compara_fechas_sin_hora(string desde, string hasta,
        string[] folios)
    {
        await using var contexto = baseDePrueba.Contexto();
        var reporte = await new ConsultasEf(contexto).ReporteDeOrdenesAsync(DateOnly.Parse(desde,
            System.Globalization.CultureInfo.InvariantCulture), DateOnly.Parse(hasta,
            System.Globalization.CultureInfo.InvariantCulture), default);
        Assert.Equal(folios, reporte.Select(r => r.Folio).Distinct());
    }
}
