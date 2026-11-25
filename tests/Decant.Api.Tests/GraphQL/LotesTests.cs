using Decant.Application;
using Decant.Application.Puertos;
using Decant.Domain.Conciliacion;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Tests;
using Xunit.Abstractions;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// N+1, CONTADO en PostgreSQL: una página de N operaciones con su orden, sus dos listas de partidas y la vuelta a la
/// operación cuesta las MISMAS consultas SQL con N = 1, 10 o 60 (una por lote), mientras el detalle REST uno por uno
/// crece con N. El contador es un interceptor de EF Core en la composición real de la API.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class LotesTests(BaseDePrueba baseDePrueba, ITestOutputHelper salida) : IAsyncLifetime
{
    private const int Operaciones = 60;
    private ApiDePrueba _api = null!;

    public async Task InitializeAsync()
    {
        await using (var contexto = baseDePrueba.Contexto())
        {
            await new AlmacenPostgres(contexto).GuardarAsync(Grande(Operaciones), default);
        }

        _api = new ApiDePrueba(baseDePrueba.Conexion);
    }

    public async Task DisposeAsync() => await _api.DisposeAsync();

    /// <summary>
    /// <paramref name="n"/> operaciones del 1-dic-2023, cada una con su documento; las pares, liquidadas con comisión
    /// del corresponsal y conciliadas; las impares, enviadas sin partidas del corresponsal (las dos formas reales).
    /// </summary>
    private static EstadoTobe Grande(int n)
    {
        var operaciones = new List<Operacion>();
        var ordenes = new List<OrdenDePago>();
        var valor = new DateOnly(2023, 12, 4);
        for (var i = 1; i <= n; i++)
        {
            var instante = Escenario.Mx(2023, 12, 1, 9, 0).AddMinutes(i);
            var operacion = Operacion.Concertar(i, Consecutivos.Formatear("FX", i), new DatosDeOperacion(instante,
                "0001", "VENTANILLA", "ARTESANÍAS DEL LAGO, S.C.", null, TipoOperacion.Venta, "USD", 1000.00m,
                19.859734m, null, "CONCERTADA")).Valor;
            operaciones.Add(operacion);
            var uetr = new Guid($"00000000-0000-4000-8000-{i:D12}");
            var referencia = $"BFN231201{i:D6}";
            var orden = OrdenDePago.Registrar(uetr, Consecutivos.Formatear("OP", i), i,
                new DatosDeOrden(referencia, instante.AddMinutes(1), valor, "FICTUS33XXX", null,
                    "Great Plains Seed Co.", "123456789012345678", "USD", 1000.00m, i % 3 == 0 ? Gastos.Our : Gastos.Sha,
                    "SUPP"),
                operacion.MontoMxn, instante.AddSeconds(30), 1000 + i);
            if (i % 2 == 0)
            {
                orden.RegistrarLiquidacion(new ConfirmacionDelCorresponsal(uetr, referencia, $"FICT{i:D12}",
                    new DateTime(2023, 12, 4, 9, 0, 0), TimeSpan.FromHours(-5), valor, "USD", 988.50m, 11.50m));
                orden.Conciliar(orden.EvaluarConciliacion()!);
            }

            ordenes.Add(orden);
        }

        return new EstadoTobe(
            new Corrida("lotes", VersionDeReglas.Actual, Escenario.Mx(2026, 11, 25, 12, 0), null, Banderas.Todas,
                "escenario"),
            [new Moneda("USD", "840", "Dólar estadounidense", 2, true)],
            new Dictionary<string, int> { ["FX"] = n + 1, ["OP"] = n + 1 },
            operaciones, ordenes, [], []);
    }

    private const string Pagina = """
        query ($n: Int!) {
          operaciones(fecha: "2023-12-01", first: $n) {
            nodes {
              folio
              orden {
                folio estatus
                operacion { folio }
                solicitadoPorElCliente { concepto monto }
                liquidadoPorElCorresponsal { concepto monto fechaHora }
              }
            }
          }
        }
        """;

    private async Task<(int Consultas, IReadOnlyList<string> Textos)> Medir(int n)
    {
        _api.Sql.Reiniciar();
        var r = (await _api.Graphql(Pagina, new { n })).SinErrores();
        var nodos = r.Datos.GetProperty("operaciones").GetProperty("nodes").EnumerateArray().ToList();
        Assert.Equal(n, nodos.Count);
        Assert.All(nodos, o => Assert.Equal(o.GetProperty("folio").GetString(),
            o.GetProperty("orden").GetProperty("operacion").GetProperty("folio").GetString()));
        return (_api.Sql.Comandos.Count, _api.Sql.Comandos);
    }

    [Fact]
    public async Task Una_pagina_con_su_grafo_cuesta_las_mismas_consultas_con_1_10_o_60_operaciones()
    {
        var medidas = new Dictionary<int, int>();
        foreach (var n in new[] { 1, 10, Operaciones })
        {
            var (consultas, textos) = await Medir(n);
            medidas[n] = consultas;
            salida.WriteLine($"GraphQL, página de {n}: {consultas} consultas SQL");
            foreach (var t in textos)
            {
                salida.WriteLine("  " + t.ReplaceLineEndings(" ")[..Math.Min(140, t.Length)]);
            }
        }

        // La página, las órdenes de sus operaciones, las dos listas de partidas y la vuelta a las operaciones: 5.
        Assert.All(medidas.Values, c => Assert.Equal(5, c));
    }

    /// <summary>
    /// El control: lo mismo por REST, operación por operación (lo que haría un cliente sin un grafo), sí crece con N:
    /// el detalle hace 4 consultas cada vez. El contador ve las dos APIs igual.
    /// </summary>
    [Fact]
    public async Task El_control_por_rest_uno_por_uno_crece_con_n()
    {
        foreach (var n in new[] { 1, 10 })
        {
            _api.Sql.Reiniciar();
            for (var id = 1; id <= n; id++)
            {
                await _api.Rest($"/api/operaciones/{id}");
            }

            salida.WriteLine($"REST, {n} detalles: {_api.Sql.Comandos.Count} consultas SQL");
            Assert.Equal(4 * n, _api.Sql.Comandos.Count);
        }
    }

    /// <summary>Cada lote es UNA consulta con todas las llaves (no N consultas con una): se ve en el SQL.</summary>
    [Fact]
    public async Task Cada_lote_lleva_todas_las_llaves_en_una_sola_consulta()
    {
        var (_, textos) = await Medir(Operaciones);
        var porLlaves = textos.Where(t => t.Contains("ANY (", StringComparison.Ordinal) ||
            t.Contains(" IN (", StringComparison.Ordinal)).ToList();
        Assert.Equal(4, porLlaves.Count); // órdenes, partidas del cliente, del corresponsal y operaciones por id
        Assert.Single(textos, t => t.Contains("LIMIT", StringComparison.Ordinal)); // la página
    }
}
