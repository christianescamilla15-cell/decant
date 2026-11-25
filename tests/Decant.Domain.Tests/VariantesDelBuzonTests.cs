using System.Globalization;
using Decant.Domain.Conciliacion;

namespace Decant.Domain.Tests;

/// <summary>
/// Una fila por cada variante de formato que EXISTE en el buzón real (moneda sin decimales o con ellos, con o sin
/// <c>:71F:</c>, horario de verano o de invierno en <c>:13D:</c>): 150,124 mensajes del universo, ocho variantes.
/// Lo esperado sale del DOCUMENTO del generador (UETR, referencias, instante de la liquidación al minuto, montos),
/// no del texto: la prueba no compara al lector consigo mismo. La hora repetida del cambio de horario no aparece en
/// el buzón (el corresponsal liquida de 08:00 a 18:00 en Nueva York), así que no tiene fila.
/// </summary>
public class VariantesDelBuzonTests
{
    [Theory]
    // JPY · con_71F · -0400: 2,081 mensajes de 150,124 (corresponsal/20220822.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100856220822FICTJPJTXXXX00000000002208220856N}{3:{121:47362b83-5c1e-47c1-82bd-f9ebe8a62ef1}}{4:\n:20:FICT419208863823\n:21:BFN220820000025\n:25:BFNJPYNOSTRO01\n:13D:2208220856-0400\n:32A:220822JPY212205,\n:52A:FICTJPJTXXX\n:71F:JPY3141,\n-}",
        "47362b83-5c1e-47c1-82bd-f9ebe8a62ef1", "BFN220820000025", "FICT419208863823", "2022-08-22T12:56:00Z", "2022-08-22",
        "JPY", "212205", "3141")]
    // JPY · con_71F · -0500: 1,102 mensajes de 150,124 (corresponsal/20221107.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100827221107FICTJPJTXXXX00000000002211070827N}{3:{121:fbc358fa-7afc-4ebf-812e-17c6efd92ce4}}{4:\n:20:FICT822788864666\n:21:BFN221106000020\n:25:BFNJPYNOSTRO01\n:13D:2211070827-0500\n:32A:221107JPY291326,\n:52A:FICTJPJTXXX\n:71F:JPY1870,\n-}",
        "fbc358fa-7afc-4ebf-812e-17c6efd92ce4", "BFN221106000020", "FICT822788864666", "2022-11-07T13:27:00Z", "2022-11-07",
        "JPY", "291326", "1870")]
    // JPY · sin_71F · -0400: 913 mensajes de 150,124 (corresponsal/20220819.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100827220819FICTJPJTXXXX00000000002208190827N}{3:{121:9d6c3641-d7fc-4644-825a-e7ae5aa6780e}}{4:\n:20:FICT486770886367\n:21:BFN220816000008\n:25:BFNJPYNOSTRO01\n:13D:2208190827-0400\n:32A:220816JPY385475,\n:52A:FICTJPJTXXX\n-}",
        "9d6c3641-d7fc-4644-825a-e7ae5aa6780e", "BFN220816000008", "FICT486770886367", "2022-08-19T12:27:00Z", "2022-08-16",
        "JPY", "385475", "0")]
    // JPY · sin_71F · -0500: 443 mensajes de 150,124 (corresponsal/20221111.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100859221111FICTJPJTXXXX00000000002211110859N}{3:{121:69d80ff7-b24b-4a49-a927-2dea595fe6dc}}{4:\n:20:FICT855652194549\n:21:BFN221110000106\n:25:BFNJPYNOSTRO01\n:13D:2211110859-0500\n:32A:221111JPY631487,\n:52A:FICTJPJTXXX\n-}",
        "69d80ff7-b24b-4a49-a927-2dea595fe6dc", "BFN221110000106", "FICT855652194549", "2022-11-11T13:59:00Z", "2022-11-11",
        "JPY", "631487", "0")]
    // con_decimales · con_71F · -0400: 66,380 mensajes de 150,124 (corresponsal/20220801.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9101456220801FICTGB2LXXXX00000000002208011456N}{3:{121:2590335e-f28f-4308-8bba-5e52d8f84be5}}{4:\n:20:FICT616277794414\n:21:BFN220801000023\n:25:BFNGBPNOSTRO01\n:13D:2208011456-0400\n:32A:220801GBP271,29\n:52A:FICTGB2LXXX\n:71F:GBP12,78\n-}",
        "2590335e-f28f-4308-8bba-5e52d8f84be5", "BFN220801000023", "FICT616277794414", "2022-08-01T18:56:00Z", "2022-08-01",
        "GBP", "271.29", "12.78")]
    // con_decimales · con_71F · -0500: 35,329 mensajes de 150,124 (corresponsal/20221114.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100846221114FICTCATTXXXX00000000002211140846N}{3:{121:3350d254-d8a2-4a9f-b80f-3e736ea1cdc5}}{4:\n:20:FICT696982657372\n:21:BFN221112000055\n:25:BFNCADNOSTRO01\n:13D:2211140846-0500\n:32A:221114CAD7080,45\n:52A:FICTCATTXXX\n:71F:CAD15,25\n-}",
        "3350d254-d8a2-4a9f-b80f-3e736ea1cdc5", "BFN221112000055", "FICT696982657372", "2022-11-14T13:46:00Z", "2022-11-14",
        "CAD", "7080.45", "15.25")]
    // con_decimales · sin_71F · -0400: 28,578 mensajes de 150,124 (corresponsal/20220808.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100817220808FICTUS33XXXX00000000002208080817N}{3:{121:ff29ea88-bd55-4105-a8b8-30af5a7fc2aa}}{4:\n:20:FICT234935886348\n:21:BFN220802000083\n:25:BFNUSDNOSTRO01\n:13D:2208080817-0400\n:32A:220802USD1411,34\n:52A:FICTUS33XXX\n-}",
        "ff29ea88-bd55-4105-a8b8-30af5a7fc2aa", "BFN220802000083", "FICT234935886348", "2022-08-08T12:17:00Z", "2022-08-02",
        "USD", "1411.34", "0")]
    // con_decimales · sin_71F · -0500: 15,298 mensajes de 150,124 (corresponsal/20221114.fin)
    [InlineData("{1:F01FICTMXMMXXX0000000000}{2:O9100944221114FICTUS33XXXX00000000002211140944N}{3:{121:ac77527f-19db-4ca6-8ad4-f882689a828d}}{4:\n:20:FICT151172611577\n:21:BFN221112000068\n:25:BFNUSDNOSTRO01\n:13D:2211140944-0500\n:32A:221114USD2484,01\n:52A:FICTUS33XXX\n-}",
        "ac77527f-19db-4ca6-8ad4-f882689a828d", "BFN221112000068", "FICT151172611577", "2022-11-14T14:44:00Z", "2022-11-14",
        "USD", "2484.01", "0")]
    public void Cada_variante_real_del_buzon_se_lee_completa(string mensaje, string uetr, string referencia21,
        string trn, string instanteUtc, string fechaValor, string moneda, string abono, string comision)
    {
        var leida = Mt910.Leer(mensaje);
        Assert.True(leida.EsExito, leida.Error?.Mensaje);
        var c = leida.Valor;
        Assert.Equal(Guid.Parse(uetr), c.Uetr);
        Assert.Equal(referencia21, c.ReferenciaMt103);
        Assert.Equal(trn, c.TrnCorresponsal);
        Assert.Equal(DateTimeOffset.Parse(instanteUtc, CultureInfo.InvariantCulture), c.Instante);
        Assert.Equal(DateOnly.Parse(fechaValor, CultureInfo.InvariantCulture), c.FechaValor);
        Assert.Equal(moneda, c.Moneda);
        Assert.Equal(decimal.Parse(abono, CultureInfo.InvariantCulture), c.Abono);
        Assert.Equal(decimal.Parse(comision, CultureInfo.InvariantCulture), c.Comision);
    }

    /// <summary>Un archivo del buzón como llega: el primer mensaje sin <c>$</c>, los demás tras <c>\n$</c>.</summary>
    [Fact]
    public void Un_archivo_real_se_separa_en_sus_mensajes_y_todos_se_leen()
    {
        var archivo = string.Join("\n$", Variantes.Select(v => v.Mensaje)) + "\n";
        var mensajes = Mt910.Separar(archivo).ToList();
        Assert.Equal(Variantes.Count, mensajes.Count);
        Assert.All(mensajes, m => Assert.True(Mt910.Leer(m).EsExito));
        Assert.Equal(Variantes.Select(v => v.Uetr), mensajes.Select(m => Mt910.Leer(m).Valor.Uetr.ToString()));
    }

    /// <summary>Los mismos mensajes de las filas de arriba (una sola fuente).</summary>
    private static readonly IReadOnlyList<(string Mensaje, string Uetr)> Variantes = Filas();

    private static List<(string Mensaje, string Uetr)> Filas()
    {
        var metodo = typeof(VariantesDelBuzonTests).GetMethod(nameof(Cada_variante_real_del_buzon_se_lee_completa))!;
        return metodo.GetCustomAttributes(typeof(InlineDataAttribute), false).Cast<InlineDataAttribute>()
            .Select(a => a.GetData(metodo).Single())
            .Select(f => ((string)f[0], (string)f[1])).ToList();
    }
}
