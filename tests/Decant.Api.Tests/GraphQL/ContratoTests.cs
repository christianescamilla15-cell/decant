using System.Net;
using System.Text;
using System.Text.Json;
using Decant.Api.GraphQL;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Tests;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// El contrato de errores de GraphQL, el par del problem+json de REST: TODO error lleva <c>extensions.code</c>, los
/// de argumentos dicen qué campo falló, y ninguno filtra nada interno (ni la excepción, ni la pila, ni el SQL, ni la
/// conexión). Sólo POST con JSON: GET, lotes de operaciones y lotes de variables se rechazan.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class ContratoTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
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

    private static readonly string[] Fugas =
        ["Npgsql", "Exception", "StackTrace", "stackTrace", " at ", "Decant.", "SELECT", "decant_", "Password"];

    /// <summary>Cada error con su código y sin rastro de lo interno.</summary>
    private static void Contrato(Respuesta r)
    {
        Assert.NotEmpty(r.Errores);
        Assert.All(r.Codigos, c => Assert.False(string.IsNullOrWhiteSpace(c), r.Texto));
        foreach (var fuga in Fugas)
        {
            Assert.DoesNotContain(fuga, r.Texto, StringComparison.Ordinal);
        }
    }

    private const string Lista = """
        query ($fecha: LocalDate!, $n: Int, $despues: String) {
          operaciones(fecha: $fecha, first: $n, after: $despues) { edges { cursor node { id } } }
        }
        """;

    private const string Reporte = """
        query ($desde: LocalDate!, $hasta: LocalDate!, $despues: String) {
          reporteDeOrdenes(desde: $desde, hasta: $hasta, after: $despues) { edges { cursor } }
        }
        """;

    public static TheoryData<string, string, string> ArgumentosInvalidos() => new()
    {
        // (consulta, variables en JSON, campo que falló) — los mismos casos que el 400 de REST
        { Reporte, """{"desde":"2023-12-31","hasta":"2023-12-01"}""", "hasta" },
        { Lista, """{"fecha":"2023-12-01","n":0}""", "first" },
        { Lista, """{"fecha":"2023-12-01","n":101}""", "first" },
        { Lista, """{"fecha":"2023-12-01","despues":"no-es-un-cursor"}""", "after" },
        { Lista, """{"fecha":"2023-12-01","despues":"WyJ2MSIsIm9wZXJhY2lvbmVzIl0"}""", "after" }, // le faltan partes
        { Reporte, """{"desde":"2023-12-01","hasta":"2023-12-31","despues":"%%%"}""", "after" },
    };

    [Theory]
    [MemberData(nameof(ArgumentosInvalidos))]
    public async Task Un_argumento_invalido_lleva_su_codigo_y_el_campo_que_fallo(string consulta, string variables,
        string campo)
    {
        _api.Sql.Reiniciar();
        var r = await _api.Graphql(consulta, JsonSerializer.Deserialize<JsonElement>(variables));
        Contrato(r);
        var error = Assert.Single(r.Errores);
        var extensiones = error.GetProperty("extensions");
        Assert.Equal(CodigosDeError.ArgumentoInvalido, extensiones.GetProperty("code").GetString());
        Assert.Equal(campo, extensiones.GetProperty("campo").GetString());
        Assert.Empty(_api.Sql.Comandos); // se rechaza antes de consultar
    }

    /// <summary>
    /// Un cursor sólo vale para la consulta que lo dio: el de otro día, el de otro rango o el de otra lista se
    /// rechaza (no se reinterpreta como una posición en otra consulta).
    /// </summary>
    [Fact]
    public async Task Un_cursor_de_otra_consulta_se_rechaza()
    {
        var dia1 = (await _api.Graphql(Lista, new { fecha = "2023-12-01", n = 1 })).SinErrores();
        var cursor = dia1.Datos.GetProperty("operaciones").GetProperty("edges")[0].GetProperty("cursor").GetString();
        var reporte = (await _api.Graphql(Reporte, new { desde = "2023-12-01", hasta = "2023-12-31" })).SinErrores();
        var cursorDelReporte = reporte.Datos.GetProperty("reporteDeOrdenes").GetProperty("edges")[0]
            .GetProperty("cursor").GetString();

        foreach (var r in new[]
        {
            await _api.Graphql(Lista, new { fecha = "2023-12-02", despues = cursor }),
            await _api.Graphql(Lista, new { fecha = "2023-12-01", despues = cursorDelReporte }),
            await _api.Graphql(Reporte, new { desde = "2023-12-01", hasta = "2023-12-30", despues = cursorDelReporte }),
            await _api.Graphql(Reporte, new { desde = "2023-12-01", hasta = "2023-12-31", despues = cursor }),
        })
        {
            Contrato(r);
            Assert.Equal([CodigosDeError.ArgumentoInvalido], r.Codigos);
        }
    }

    public static TheoryData<string, string> DocumentosInvalidos() => new()
    {
        { "{ operacion(id: 1) { folio ", "sintaxis" },
        { "{ operacion(id: 1) { noExiste } }", "campo inexistente" },
        { "{ operacion(id: \"uno\") { folio } }", "tipo de argumento" },
        { "{ operaciones { nodes { id } } }", "falta un argumento obligatorio" },
        { "{ operacion(id: 1) }", "objeto sin selección" },
        { "subscription { operacion(id: 1) { id } }", "sin suscripciones" },
    };

    [Theory]
    [MemberData(nameof(DocumentosInvalidos))]
    public async Task Un_documento_invalido_se_rechaza_con_codigo_sin_tocar_la_base(string consulta, string caso)
    {
        _api.Sql.Reiniciar();
        var r = await _api.Graphql(consulta);
        Contrato(r);
        Assert.True(r.Estado == HttpStatusCode.BadRequest, $"{caso}: {r.Estado}");
        Assert.Empty(_api.Sql.Comandos);
    }

    /// <summary>La base no responde: el error sale con su código y la ruta, SIN la excepción, la pila ni la conexión.</summary>
    [Fact]
    public async Task Un_error_tecnico_no_filtra_nada_interno()
    {
        const string caida =
            "Host=127.0.0.1;Port=1;Database=decant_caida;Username=decant;Password=Secreto-de-prueba-1;Timeout=2";
        await using var api = new ApiDePrueba(caida);
        var r = await api.Graphql("{ operacion(id: 1) { folio orden { folio } } }");
        Contrato(r);
        foreach (var fuga in new[] { "Secreto-de-prueba-1", "127.0.0.1", "caida", "Host=" })
        {
            Assert.DoesNotContain(fuga, r.Texto, StringComparison.OrdinalIgnoreCase);
        }

        var error = Assert.Single(r.Errores);
        Assert.Equal(CodigosDeError.ErrorInterno, r.Codigos[0]);
        Assert.Equal("Error interno.", error.GetProperty("message").GetString());
        Assert.Equal(["operacion"], error.GetProperty("path").EnumerateArray().Select(p => p.GetString()));
        Assert.Equal(["code"], error.GetProperty("extensions").EnumerateObject().Select(p => p.Name));
    }

    /// <summary>Sólo POST con JSON: ni consultas en la URL (GET), ni la herramienta del navegador.</summary>
    [Theory]
    [InlineData("/graphql?query=%7B__typename%7D")]
    [InlineData("/graphql")]
    public async Task Get_no_ejecuta_consultas_ni_sirve_la_herramienta(string ruta)
    {
        _api.Sql.Reiniciar();
        using var peticion = new HttpRequestMessage(HttpMethod.Get, ruta);
        peticion.Headers.Accept.ParseAdd("text/html,application/json");
        var respuesta = await _api.Cliente.SendAsync(peticion);
        var texto = await respuesta.Content.ReadAsStringAsync();
        Assert.NotEqual(HttpStatusCode.OK, respuesta.StatusCode);
        Assert.DoesNotContain("__typename\":", texto, StringComparison.Ordinal);
        Assert.DoesNotContain("<html", texto, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>Lotes apagados: varias operaciones en un arreglo o varias variables para una operación.</summary>
    [Theory]
    [InlineData("""[{"query":"{ __typename }"},{"query":"{ __typename }"}]""")]
    [InlineData("""{"query":"query ($id: Long!) { operacion(id: $id) { id } }","variables":[{"id":1},{"id":2}]}""")]
    public async Task Los_lotes_de_operaciones_y_de_variables_se_rechazan(string cuerpo)
    {
        _api.Sql.Reiniciar();
        using var contenido = new StringContent(cuerpo, Encoding.UTF8, "application/json");
        var r = await Respuesta.De(await _api.Cliente.PostAsync("/graphql", contenido));
        Assert.NotEqual(HttpStatusCode.OK, r.Estado);
        Assert.DoesNotContain("\"data\"", r.Texto, StringComparison.Ordinal);
        Assert.Empty(_api.Sql.Comandos);
    }
}
