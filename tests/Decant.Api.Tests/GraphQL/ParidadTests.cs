using System.Net;
using System.Reflection;
using System.Text.Json;
using Decant.Application.Puertos;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Tests;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// Paridad entre las dos APIs sobre los MISMOS datos en PostgreSQL: cada campo que publica REST existe en GraphQL con
/// el mismo valor (texto exacto de horas con su desfase, decimales con su escala, nulos donde REST pone nulos). Las
/// selecciones de GraphQL salen de los registros de REST por reflexión: un campo nuevo en REST sin su par en GraphQL
/// rompe esta prueba. Las listas se recorren por cursor, página por página, y deben dar lo mismo que REST de una vez.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class ParidadTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    private ApiDePrueba _api = null!;

    public async Task InitializeAsync()
    {
        await Cargar(Escenario.Estado());
        _api = new ApiDePrueba(baseDePrueba.Conexion);
    }

    public async Task DisposeAsync() => await _api.DisposeAsync();

    private async Task Cargar(EstadoTobe estado)
    {
        await using var contexto = baseDePrueba.Contexto();
        await new AlmacenPostgres(contexto).GuardarAsync(estado, default);
    }

    private static string Campos(Type registro) => string.Join(' ', registro
        .GetProperties(BindingFlags.Public | BindingFlags.Instance)
        .Select(p => JsonNamingPolicy.CamelCase.ConvertName(p.Name)));

    /// <summary>Lo que el detalle REST publica, pedido a GraphQL campo por campo.</summary>
    private static readonly string Detalle = $$"""
        query ($id: Long!) {
          operacion(id: $id) {
            {{Campos(typeof(Presentacion.Operacion))}}
            orden {
              {{Campos(typeof(Presentacion.Orden))}}
              solicitadoPorElCliente { {{Campos(typeof(Presentacion.Partida))}} }
              liquidadoPorElCorresponsal { {{Campos(typeof(Presentacion.Partida))}} }
            }
          }
        }
        """;

    /// <summary>Compara cada propiedad del JSON de REST con la del de GraphQL y junta las diferencias.</summary>
    private static void Igual(JsonElement rest, JsonElement graphql, string ruta, List<string> diferencias)
    {
        switch (rest.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (var propiedad in rest.EnumerateObject())
                {
                    if (!graphql.TryGetProperty(propiedad.Name, out var par))
                    {
                        diferencias.Add($"{ruta}.{propiedad.Name}: no está en GraphQL");
                        continue;
                    }

                    Igual(propiedad.Value, par, $"{ruta}.{propiedad.Name}", diferencias);
                }

                break;
            case JsonValueKind.Array:
                var a = rest.EnumerateArray().ToList();
                var b = graphql.EnumerateArray().ToList();
                if (a.Count != b.Count)
                {
                    diferencias.Add($"{ruta}: {a.Count} elementos en REST y {b.Count} en GraphQL");
                    break;
                }

                for (var i = 0; i < a.Count; i++)
                {
                    Igual(a[i], b[i], $"{ruta}[{i}]", diferencias);
                }

                break;
            case JsonValueKind.Number:
                // El valor y su escala: 988.50 no es 988.5 para quien lo imprime.
                if (graphql.ValueKind != JsonValueKind.Number || rest.GetRawText() != graphql.GetRawText())
                {
                    diferencias.Add($"{ruta}: {rest.GetRawText()} ≠ {graphql.GetRawText()}");
                }

                break;
            case JsonValueKind.String:
                // El texto exacto (las horas con su desfase, sin normalizar); el escape de JSON no cuenta: REST
                // escribe «Í» como \u00CD y GraphQL en UTF-8, y los dos son la misma cadena.
                if (graphql.ValueKind != JsonValueKind.String || rest.GetString() != graphql.GetString())
                {
                    diferencias.Add($"{ruta}: {rest.GetRawText()} ≠ {graphql.GetRawText()}");
                }

                break;
            default:
                if (rest.ValueKind != graphql.ValueKind || rest.GetRawText() != graphql.GetRawText())
                {
                    diferencias.Add($"{ruta}: {rest.GetRawText()} ≠ {graphql.GetRawText()}");
                }

                break;
        }
    }

    private static void SinDiferencias(JsonElement rest, JsonElement graphql)
    {
        var diferencias = new List<string>();
        Igual(rest, graphql, "$", diferencias);
        Assert.True(diferencias.Count == 0, string.Join('\n', diferencias));
    }

    /// <summary>
    /// Los cuatro casos del escenario: conciliada con re-registro y comisión del corresponsal, vencida sin partidas
    /// del corresponsal, liquidada sin comisión y una operación sin orden.
    /// </summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(3)]
    [InlineData(4)]
    public async Task El_detalle_es_el_mismo_por_rest_y_por_graphql(long id)
    {
        var rest = await _api.Rest($"/api/operaciones/{id}");
        var g = (await _api.Graphql(Detalle, new { id })).SinErrores().Datos.GetProperty("operacion");

        SinDiferencias(rest.GetProperty("operacion"), g);
        if (rest.GetProperty("orden").ValueKind == JsonValueKind.Null)
        {
            Assert.Equal(JsonValueKind.Null, g.GetProperty("orden").ValueKind);
            Assert.Equal(0, rest.GetProperty("solicitadoPorElCliente").GetArrayLength());
            Assert.Equal(0, rest.GetProperty("liquidadoPorElCorresponsal").GetArrayLength());
            return;
        }

        var orden = g.GetProperty("orden");
        SinDiferencias(rest.GetProperty("orden"), orden);
        // T4: las listas de REST van junto a la orden; en GraphQL, dentro de ella (es su documento).
        SinDiferencias(rest.GetProperty("solicitadoPorElCliente"), orden.GetProperty("solicitadoPorElCliente"));
        SinDiferencias(rest.GetProperty("liquidadoPorElCorresponsal"),
            orden.GetProperty("liquidadoPorElCorresponsal"));
    }

    [Fact]
    public async Task Lo_que_no_existe_es_404_en_rest_y_nulo_en_graphql()
    {
        Assert.Equal(HttpStatusCode.NotFound, (await _api.Cliente.GetAsync("/api/operaciones/999")).StatusCode);
        var g = (await _api.Graphql(Detalle, new { id = 999 })).SinErrores();
        Assert.Equal(JsonValueKind.Null, g.Datos.GetProperty("operacion").ValueKind);
    }

    /// <summary>Recorre una conexión por cursor con páginas de <paramref name="tamano"/> y devuelve sus nodos.</summary>
    private async Task<List<JsonElement>> Recorrer(string campo, string argumentos, string seleccion, int tamano)
    {
        var nodos = new List<JsonElement>();
        string? cursor = null;
        for (var vuelta = 0; vuelta < 1000; vuelta++)
        {
            var consulta = $$"""
                query ($n: Int!, $despues: String) {
                  {{campo}}({{argumentos}}, first: $n, after: $despues) {
                    pageInfo { hasNextPage hasPreviousPage endCursor }
                    edges { cursor node { {{seleccion}} } }
                  }
                }
                """;
            var conexion = (await _api.Graphql(consulta, new { n = tamano, despues = cursor })).SinErrores()
                .Datos.GetProperty(campo);
            var aristas = conexion.GetProperty("edges").EnumerateArray().ToList();
            var info = conexion.GetProperty("pageInfo");
            Assert.Equal(cursor is not null, info.GetProperty("hasPreviousPage").GetBoolean());
            Assert.True(aristas.Count <= tamano);
            nodos.AddRange(aristas.Select(a => a.GetProperty("node")));
            if (!info.GetProperty("hasNextPage").GetBoolean())
            {
                return nodos;
            }

            Assert.Equal(tamano, aristas.Count); // hay más: la página va llena
            cursor = info.GetProperty("endCursor").GetString();
            Assert.Equal(aristas[^1].GetProperty("cursor").GetString(), cursor);
        }

        throw new InvalidOperationException("la paginación no termina");
    }

    private async Task ListaIgual(string fecha, int tamano)
    {
        var rest = await _api.Rest($"/api/operaciones?fecha={fecha}&maximo=1000");
        var nodos = await Recorrer("operaciones", $"fecha: \"{fecha}\"", Campos(typeof(OperacionDeLista)), tamano);
        SinDiferencias(rest, JsonSerializer.SerializeToElement(nodos));
    }

    private async Task ReporteIgual(string desde, string hasta, int tamano)
    {
        var rest = await _api.Rest($"/api/reportes/ordenes?desde={desde}&hasta={hasta}");
        var nodos = await Recorrer("reporteDeOrdenes", $"desde: \"{desde}\", hasta: \"{hasta}\"",
            Campos(typeof(Decant.Application.Puertos.RenglonDeReporte)), tamano);
        SinDiferencias(rest, JsonSerializer.SerializeToElement(nodos));
    }

    /// <summary>T1 por páginas: el 1-dic tiene dos operaciones en el mismo minuto (desempata el id) y una a las 23:30.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(100)]
    public async Task La_lista_del_dia_es_la_misma_recorrida_por_cursor(int tamano)
    {
        await ListaIgual("2023-12-01", tamano);
        await ListaIgual("2023-12-02", tamano);
        await ListaIgual("2023-11-30", tamano); // un día sin operaciones
    }

    /// <summary>T2 por páginas: dos renglones del mismo folio que la página parte en medio.</summary>
    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    [InlineData(100)]
    public async Task El_reporte_es_el_mismo_recorrido_por_cursor(int tamano)
    {
        await ReporteIgual("2023-12-01", "2023-12-31", tamano);
        await ReporteIgual("2023-11-01", "2023-11-30", tamano);
    }

    /// <summary>
    /// Los bordes de fecha: el último segundo y la medianoche de cada día local, el de 25 horas (30-oct-2022) y el de
    /// 23 (3-abr-2022), y los rangos de fecha valor inclusivos. Con páginas de 1: cada cursor cae en un borde.
    /// </summary>
    [Fact]
    public async Task En_los_bordes_de_fecha_las_dos_apis_coinciden()
    {
        await Cargar(Escenario.Bordes());
        foreach (var dia in new[] { "2022-10-29", "2022-10-30", "2022-10-31", "2022-04-03", "2022-04-04" })
        {
            await ListaIgual(dia, 1);
        }

        foreach (var (desde, hasta) in new[]
        {
            ("2022-10-31", "2022-10-31"), ("2022-10-28", "2022-10-31"), ("2022-10-29", "2022-11-02"),
            ("2022-10-28", "2022-11-03"),
        })
        {
            await ReporteIgual(desde, hasta, 1);
        }
    }
}
