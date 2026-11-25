using System.Net;
using System.Text.Json;
using Decant.Api.GraphQL;
using HotChocolate.Execution;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// El contrato publicado: el SDL versionado en el repo es EXACTAMENTE el que sirve la API (una prueba de instantánea
/// que, al fallar, dice qué cambio rompe a los clientes), no hay mutaciones y la introspección depende del ambiente.
/// Nada de esto toca la base: la conexión apunta a un puerto cerrado.
/// </summary>
public class EsquemaTests
{
    private const string SinBase = "Host=127.0.0.1;Port=1;Database=sin_base;Username=nadie;Password=nada;Timeout=1";

    public static readonly string ArchivoSdl = Repositorio.Ruta("src", "Decant.Api", "GraphQL", "esquema.graphql");

    private static async Task<string> SdlPublicado(ApiDePrueba api)
    {
        var ejecutor = await api.Fabrica.Services.GetRequiredService<IRequestExecutorProvider>().GetExecutorAsync();
        return ejecutor.Schema.ToString().ReplaceLineEndings("\n").TrimEnd() + "\n";
    }

    /// <summary>
    /// Instantánea: cualquier diferencia falla y se clasifica (ROMPE / no rompe). Para aceptar un cambio deliberado:
    /// <c>DECANT_ACTUALIZAR_SDL=1 dotnet test --filter El_sdl_versionado</c> reescribe el archivo y falla una vez
    /// para que el cambio se revise en el diff (y, si rompe, se versione según el ADR 0017).
    /// </summary>
    [Fact]
    public async Task El_sdl_versionado_es_el_que_publica_la_api()
    {
        await using var api = new ApiDePrueba(SinBase);
        var publicado = await SdlPublicado(api);
        if (Environment.GetEnvironmentVariable("DECANT_ACTUALIZAR_SDL") == "1")
        {
            await File.WriteAllTextAsync(ArchivoSdl, publicado);
            Assert.Fail($"SDL reescrito en {ArchivoSdl}: revisa el diff y vuelve a correr sin DECANT_ACTUALIZAR_SDL.");
        }

        var versionado = (await File.ReadAllTextAsync(ArchivoSdl)).ReplaceLineEndings("\n");
        var cambios = CambiosDeEsquema.Comparar(versionado, publicado);
        Assert.True(cambios.Count == 0 && versionado == publicado,
            "El esquema cambió respecto a esquema.graphql:\n" + string.Join('\n', cambios));
    }

    public static TheoryData<string, string, bool> Mutaciones() => new()
    {
        // (lo que se busca en el SDL versionado, por qué se reemplaza, ¿rompe?)
        { "  monto: Decimal!\n", "", true },                                         // se quita un campo
        { "  folio: String!\n", "  folio: String\n", true },                       // una salida se vuelve anulable
        { "  id: Long!\n", "  id: String!\n", true },                              // cambia el tipo
        { "operacion(id: Long!)", "operacion(id: Long! moneda: String!)", true },  // argumento nuevo obligatorio
        { "operacion(id: Long!)", "operacion(id: Long! moneda: String)", false },  // argumento nuevo opcional
        { "  folio: String!\n", "  folio: String!\n  nuevo: String\n", false },    // campo nuevo
        { "  cuentaClabe: String\n", "  cuentaClabe: String!\n", false },          // una salida más estricta
    };

    /// <summary>Controles del clasificador: sobre el SDL REAL, cada cambio que rompe se reporta como tal.</summary>
    [Theory]
    [MemberData(nameof(Mutaciones))]
    public async Task Cada_cambio_al_sdl_se_clasifica_por_si_rompe_a_los_clientes(string busca, string pon,
        bool rompe)
    {
        var versionado = (await File.ReadAllTextAsync(ArchivoSdl)).ReplaceLineEndings("\n");
        var indice = versionado.IndexOf(busca, StringComparison.Ordinal);
        Assert.True(indice >= 0, $"el SDL ya no tiene «{busca.Trim()}»: ajusta el control");
        var mutado = string.Concat(versionado.AsSpan(0, indice), pon, versionado.AsSpan(indice + busca.Length));
        var cambios = CambiosDeEsquema.Comparar(versionado, mutado);
        Assert.NotEmpty(cambios);
        Assert.Equal(rompe, cambios.Any(c => c.Rompe));
    }

    [Fact]
    public async Task Es_de_solo_lectura_sin_mutaciones_ni_suscripciones()
    {
        await using var api = new ApiDePrueba(SinBase);
        var ejecutor = await api.Fabrica.Services.GetRequiredService<IRequestExecutorProvider>().GetExecutorAsync();
        Assert.Null(ejecutor.Schema.MutationType);
        Assert.Null(ejecutor.Schema.SubscriptionType);
        var r = await api.Graphql("mutation { operacion(id: 1) { id } }");
        Assert.NotEmpty(r.Errores);
        Assert.Empty(api.Sql.Comandos);
    }

    private const string Introspeccion = "{ __schema { queryType { name } types { name } } }";

    /// <summary>
    /// Introspección según el ambiente (appsettings.{ambiente}.json, sección GraphQL): encendida en Desarrollo y
    /// Pruebas, apagada en Producción, donde el contrato es el SDL versionado. __typename no es introspección.
    /// </summary>
    [Theory]
    [InlineData("Desarrollo", true)]
    [InlineData("Pruebas", true)]
    [InlineData("Produccion", false)]
    public async Task La_introspeccion_depende_del_ambiente(string ambiente, bool permitida)
    {
        await using var api = new ApiDePrueba(SinBase, ambiente);
        Assert.Equal(permitida, api.Fabrica.Services.GetRequiredService<OpcionesGraphQL>().Introspeccion);
        var r = await api.Graphql(Introspeccion);
        if (permitida)
        {
            Assert.Equal("Query", r.SinErrores().Datos.GetProperty("__schema").GetProperty("queryType")
                .GetProperty("name").GetString());
        }
        else
        {
            Assert.Equal([CodigosDeError.IntrospeccionDeshabilitada], r.Codigos);
            Assert.False(r.Cuerpo.TryGetProperty("data", out var datos) && datos.ValueKind == JsonValueKind.Object);
        }

        var tipo = await api.Graphql("{ __type(name: \"Orden\") { name } }");
        Assert.Equal(permitida, tipo.Errores.Count == 0);

        Assert.Equal("Query", (await api.Graphql("{ __typename }")).SinErrores().Datos.GetProperty("__typename")
            .GetString());
        Assert.Empty(api.Sql.Comandos);
    }

    /// <summary>
    /// El SDL no se descarga por HTTP en NINGÚN ambiente (sería la vía de atrás de la introspección en producción):
    /// el contrato es el archivo versionado.
    /// </summary>
    [Theory]
    [InlineData("Desarrollo")]
    [InlineData("Produccion")]
    public async Task El_sdl_no_se_descarga_por_http(string ambiente)
    {
        await using var api = new ApiDePrueba(SinBase, ambiente);
        foreach (var ruta in new[] { "/graphql?sdl", "/graphql/schema.graphql" })
        {
            var respuesta = await api.Cliente.GetAsync(ruta);
            var texto = await respuesta.Content.ReadAsStringAsync();
            Assert.NotEqual(HttpStatusCode.OK, respuesta.StatusCode);
            Assert.DoesNotContain("type Query", texto, StringComparison.Ordinal);
        }
    }

    /// <summary>La sección GraphQL de los appsettings: sólo claves conocidas y un valor que no es booleano no arranca.</summary>
    [Fact]
    public void La_configuracion_de_graphql_se_lee_estricta()
    {
        foreach (var archivo in Directory.GetFiles(Repositorio.Ruta("src", "Decant.Api"), "appsettings*.json"))
        {
            using var json = JsonDocument.Parse(File.ReadAllText(archivo));
            if (json.RootElement.TryGetProperty(OpcionesGraphQL.Seccion, out var seccion))
            {
                Assert.All(seccion.EnumerateObject(), c => Assert.Equal(nameof(OpcionesGraphQL.Introspeccion), c.Name));
            }
        }

        var configuracion = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["GraphQL:Introspeccion"] = "si" }).Build();
        var error = Assert.Throws<InvalidOperationException>(() => OpcionesGraphQL.Leer(configuracion));
        Assert.Contains("GraphQL:Introspeccion", error.Message, StringComparison.Ordinal);
        Assert.False(OpcionesGraphQL.Leer(new ConfigurationBuilder().Build())
            .Introspeccion);
    }
}
