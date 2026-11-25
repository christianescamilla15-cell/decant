using System.Net;
using System.Text.Json;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Tests;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.DependencyInjection;

namespace Decant.Api.Tests;

/// <summary>
/// Contrato de errores de la API: 400, 404, 405 y 500 salen como <c>application/problem+json</c>
/// con su código y un título, y un 500 no filtra nada interno. Sin autenticación en el alcance (ADR 0012): no hay
/// 401/403 que probar, así que se fija la superficie para que una ruta nueva obligue a decidir su autorización.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class ContratoDeErroresTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    private WebApplicationFactory<Program> _fabrica = null!;
    private HttpClient _cliente = null!;

    public async Task InitializeAsync()
    {
        await using (var contexto = baseDePrueba.Contexto())
        {
            await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Estado(), default);
        }

        _fabrica = Fabrica(baseDePrueba.Conexion);
        _cliente = _fabrica.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _cliente.Dispose();
        await _fabrica.DisposeAsync();
    }

    private static WebApplicationFactory<Program> Fabrica(string conexion) =>
        new WebApplicationFactory<Program>().WithWebHostBuilder(b => b
            .UseEnvironment("Pruebas")
            .UseSetting("ConnectionStrings:Decant", conexion));

    private static async Task<JsonElement> Problema(HttpResponseMessage respuesta, HttpStatusCode esperado)
    {
        Assert.Equal(esperado, respuesta.StatusCode);
        Assert.Equal("application/problem+json", respuesta.Content.Headers.ContentType?.MediaType);
        var cuerpo = JsonDocument.Parse(await respuesta.Content.ReadAsStringAsync()).RootElement;
        Assert.Equal((int)esperado, cuerpo.GetProperty("status").GetInt32());
        Assert.False(string.IsNullOrWhiteSpace(cuerpo.GetProperty("title").GetString()));
        return cuerpo;
    }

    [Theory]
    [InlineData("/api/reportes/ordenes?desde=2023-12-31&hasta=2023-12-01", "hasta")]
    [InlineData("/api/operaciones?fecha=2023-12-01&maximo=0", "maximo")]
    [InlineData("/api/operaciones?fecha=2023-12-01&maximo=1001", "maximo")]
    public async Task Una_validacion_es_400_con_el_campo_que_fallo(string ruta, string campo)
    {
        var cuerpo = await Problema(await _cliente.GetAsync(ruta), HttpStatusCode.BadRequest);
        Assert.True(cuerpo.GetProperty("errors").TryGetProperty(campo, out _));
    }

    [Theory]
    [InlineData("/api/operaciones?fecha=no-es-fecha")]
    [InlineData("/api/operaciones")]                        // falta un parámetro obligatorio
    [InlineData("/api/reportes/ordenes?desde=2023-12-01")]
    public async Task Un_parametro_que_no_se_puede_leer_es_400(string ruta) =>
        await Problema(await _cliente.GetAsync(ruta), HttpStatusCode.BadRequest);

    [Theory]
    [InlineData("/api/operaciones/999")]   // la operación no existe
    [InlineData("/api/no-existe")]         // la ruta no existe
    [InlineData("/api/operaciones/abc")]   // la restricción {id:long} no casa
    public async Task Lo_que_no_existe_es_404(string ruta) =>
        await Problema(await _cliente.GetAsync(ruta), HttpStatusCode.NotFound);

    [Fact]
    public async Task Un_metodo_no_permitido_es_405() =>
        await Problema(await _cliente.DeleteAsync("/api/operaciones/1"), HttpStatusCode.MethodNotAllowed);

    /// <summary>La base no responde: 500 con el contrato y SIN la excepción, la pila ni la cadena de conexión.</summary>
    [Fact]
    public async Task Un_error_tecnico_es_500_sin_filtrar_nada_interno()
    {
        const string caida = "Host=127.0.0.1;Port=1;Database=decant_caida;Username=decant;Password=Secreto-de-prueba-1;Timeout=2";
        await using var fabrica = Fabrica(caida);
        var respuesta = await fabrica.CreateClient().GetAsync("/api/operaciones/1");
        var cuerpo = await Problema(respuesta, HttpStatusCode.InternalServerError);
        var texto = cuerpo.GetRawText();
        foreach (var fuga in new[] { "Npgsql", "Exception", "Secreto-de-prueba-1", "127.0.0.1", "decant_caida", " at " })
        {
            Assert.DoesNotContain(fuga, texto, StringComparison.OrdinalIgnoreCase);
        }

        Assert.False(cuerpo.TryGetProperty("detail", out _));
    }

    /// <summary>
    /// ADR 0012: la API es de SÓLO LECTURA y sin autenticación en el alcance de la demo. Si aparece una ruta o un
    /// verbo nuevo, esta prueba falla hasta que se decida su autorización (401/403 por ruta) y se actualice el ADR.
    /// </summary>
    [Fact]
    public void La_superficie_es_la_del_adr_de_solo_lectura()
    {
        var rutas = _fabrica.Services.GetRequiredService<EndpointDataSource>().Endpoints.OfType<RouteEndpoint>()
            .Select(e => $"{string.Join(',', e.Metadata.GetMetadata<Microsoft.AspNetCore.Routing.HttpMethodMetadata>()
                ?.HttpMethods ?? [])} {e.RoutePattern.RawText}")
            .Order(StringComparer.Ordinal).ToList();
        Assert.Equal(
        [
            "GET /api/configuracion",
            "GET /api/operaciones",
            "GET /api/operaciones/{id:long}",
            "GET /api/reportes/ordenes",
            "GET /salud",
        ], rutas);
    }
}
