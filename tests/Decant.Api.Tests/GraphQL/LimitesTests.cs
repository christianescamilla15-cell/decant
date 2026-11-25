using System.Net;
using System.Text;
using System.Text.Json;
using Decant.Api.GraphQL;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Tests;
using Xunit.Abstractions;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// Límites contra consultas abusivas: profundidad (el esquema tiene un ciclo orden ↔ operación), costo (alias y
/// páginas que multiplican) y tamaño del documento. Una consulta abusiva se rechaza ANTES de ejecutarse: con su
/// código, sin datos y con CERO consultas SQL. La consulta legítima más honda y la más cara sí corren.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class LimitesTests(BaseDePrueba baseDePrueba, ITestOutputHelper salida) : IAsyncLifetime
{
    private ApiDePrueba _api = null!;

    public async Task InitializeAsync()
    {
        await using (var contexto = baseDePrueba.Contexto())
        {
            await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Estado(), default);
        }

        _api = new ApiDePrueba(baseDePrueba.Conexion);
    }

    public async Task DisposeAsync() => await _api.DisposeAsync();

    /// <summary>
    /// La consulta legítima más honda: la página, la orden de cada operación, la vuelta a la operación, su orden y lo
    /// abonado (operaciones › edges › node › orden › operacion › orden › liquidadoPorElCorresponsal › monto = 8).
    /// </summary>
    private const string LaMasHonda = """
        { operaciones(fecha: "2023-12-01", first: 2) { edges { node { orden { operacion { orden {
            liquidadoPorElCorresponsal { monto } } } } } } } }
        """;

    /// <summary>Una consulta de profundidad exacta <paramref name="profundidad"/> (la hoja cuenta) por el ciclo.</summary>
    private static string Honda(int profundidad)
    {
        // operaciones(1) › edges(2) › node(3) › orden(4) › operacion(5) › orden(6) › … › folio(profundidad)
        var texto = new StringBuilder("{ operaciones(fecha: \"2023-12-01\", first: 1) { edges { node { ");
        for (var nivel = 4; nivel < profundidad; nivel++)
        {
            texto.Append(nivel % 2 == 0 ? "orden { " : "operacion { ");
        }

        texto.Append("folio ");
        texto.Append('}', profundidad - 1);
        return texto.Append(" }").ToString();
    }

    /// <summary>Una página de 100 con todo su grafo: la consulta legítima más cara.</summary>
    private static string PaginaCompleta(string alias = "operaciones") => $$"""
        {{alias}}: operaciones(fecha: "2023-12-01", first: 100) {
          pageInfo { hasNextPage endCursor }
          edges {
            cursor
            node {
              id folio fechaOperacion montoMxn
              orden {
                folio estatus horasLiquidacion
                operacion { folio }
                solicitadoPorElCliente { renglon concepto monto fechaHora }
                liquidadoPorElCorresponsal { renglon concepto monto fechaHora }
              }
            }
          }
        }
        """;

    private async Task<(double Campos, double Tipos)> Costo(string consulta)
    {
        var r = await _api.Graphql(consulta, encabezados: new Dictionary<string, string> { ["GraphQL-Cost"] = "validate" });
        var costo = r.Cuerpo.GetProperty("extensions").GetProperty("operationCost");
        return (costo.GetProperty("fieldCost").GetDouble(), costo.GetProperty("typeCost").GetDouble());
    }

    private static void Rechazada(Respuesta r, string codigo)
    {
        Assert.Contains(codigo, r.Codigos);
        Assert.Equal(HttpStatusCode.BadRequest, r.Estado);
        Assert.Equal("application/graphql-response+json", r.TipoDeContenido);
        Assert.False(r.Cuerpo.TryGetProperty("data", out var datos) && datos.ValueKind != JsonValueKind.Null);
    }

    [Fact]
    public async Task La_consulta_legitima_mas_honda_corre_y_una_mas_se_rechaza_sin_tocar_la_base()
    {
        var permitida = (await _api.Graphql(LaMasHonda)).SinErrores();
        Assert.Equal(2, permitida.Datos.GetProperty("operaciones").GetProperty("edges").GetArrayLength());

        _api.Sql.Reiniciar();
        var r = await _api.Graphql(Honda(Composicion.ProfundidadMaxima + 1));
        Rechazada(r, CodigosDeError.ProfundidadExcedida);
        // La que rechaza es la regla de profundidad configurada (no sólo el tope de ciclos de la biblioteca).
        Assert.Contains(r.Errores, e => e.GetProperty("extensions").TryGetProperty("allowedExecutionDepth", out var p) &&
            p.GetInt32() == Composicion.ProfundidadMaxima);
        Assert.Empty(_api.Sql.Comandos);
    }

    /// <summary>La abusiva: 40 niveles por el ciclo, el tipo de consulta que sin tope recorre el grafo sin fondo.</summary>
    [Fact]
    public async Task Una_consulta_abusiva_por_el_ciclo_se_rechaza_sin_tocar_la_base()
    {
        _api.Sql.Reiniciar();
        var r = await _api.Graphql(Honda(40));
        Rechazada(r, CodigosDeError.ProfundidadExcedida);
        Assert.All(r.Codigos, c => Assert.NotNull(c));
        Assert.Empty(_api.Sql.Comandos);
    }

    [Fact]
    public async Task La_pagina_legitima_mas_cara_cabe_en_el_costo_y_corre()
    {
        var (campos, tipos) = await Costo($"{{ {PaginaCompleta()} }}");
        salida.WriteLine($"página de 100 con su grafo: costo de campos {campos}, de tipos {tipos} " +
            $"(topes {Composicion.CostoMaximoDeCampos} y {Composicion.CostoMaximoDeTipos})");
        Assert.InRange(campos, 1, Composicion.CostoMaximoDeCampos);
        Assert.InRange(tipos, 1, Composicion.CostoMaximoDeTipos);
        var r = (await _api.Graphql($"{{ {PaginaCompleta()} }}")).SinErrores();
        Assert.Equal(3, r.Datos.GetProperty("operaciones").GetProperty("edges").GetArrayLength());

        // El borde del tope: dos páginas completas en una petición caben; tres, no.
        var dos = await Costo($"{{ {PaginaCompleta("a")} {PaginaCompleta("b")} }}");
        var tres = await Costo($"{{ {PaginaCompleta("a")} {PaginaCompleta("b")} {PaginaCompleta("c")} }}");
        Assert.True(dos.Campos <= Composicion.CostoMaximoDeCampos && dos.Tipos <= Composicion.CostoMaximoDeTipos);
        Assert.True(tres.Campos > Composicion.CostoMaximoDeCampos);
    }

    /// <summary>
    /// La abusiva por costo: la misma página diez veces en alias. Cada una es legítima y de profundidad baja; juntas
    /// multiplican el trabajo, y el análisis estático las rechaza antes de ejecutar (cero SQL).
    /// </summary>
    [Fact]
    public async Task Diez_paginas_completas_en_alias_exceden_el_costo_y_se_rechazan_sin_tocar_la_base()
    {
        var consulta = "{ " + string.Join(' ', Enumerable.Range(1, 10).Select(i => PaginaCompleta($"p{i}"))) + " }";
        var (campos, tipos) = await Costo(consulta);
        salida.WriteLine($"diez páginas en alias: costo de campos {campos}, de tipos {tipos}");
        Assert.True(campos > Composicion.CostoMaximoDeCampos || tipos > Composicion.CostoMaximoDeTipos);

        _api.Sql.Reiniciar();
        var r = await _api.Graphql(consulta);
        Rechazada(r, CodigosDeError.CostoExcedido);
        Assert.Empty(_api.Sql.Comandos);
    }

    /// <summary>Un documento más grande que el tope (64 KiB) no llega al parser.</summary>
    [Fact]
    public async Task Un_documento_enorme_se_rechaza_sin_tocar_la_base()
    {
        _api.Sql.Reiniciar();
        var relleno = new string(' ', Composicion.TamanoMaximoDePeticion);
        var r = await _api.Graphql("{ __typename" + relleno + "}");
        Assert.NotEqual(HttpStatusCode.OK, r.Estado);
        Assert.All(r.Codigos, c => Assert.NotNull(c));
        Assert.Empty(_api.Sql.Comandos);
    }
}
