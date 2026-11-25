using System.Reflection;
using System.Text.Json;
using Decant.Application;
using Decant.Infrastructure;
using Microsoft.Extensions.Configuration;

namespace Decant.Api.Tests;

/// <summary>
/// La configuración por ambiente: CADA propiedad de las opciones se lee de su clave (con un banco
/// de configuración de prueba armado por reflexión, así que una propiedad nueva sin leer hace fallar la prueba),
/// ninguna clave de los appsettings sobra (una clave mal escrita se ignoraría en silencio) y lo que imprime el CI por
/// ambiente trae todas las banderas y destinos, sin secretos.
/// </summary>
public class ConfiguracionTests
{
    private static readonly string[] Banderas_ = Parametros(typeof(Banderas));
    private static readonly string[] Destinos_ = Parametros(typeof(Destinos));

    private static string[] Parametros(Type tipo) =>
        tipo.GetConstructors().Single(c => c.GetParameters().Length > 0 && c.GetParameters()[0].ParameterType != tipo)
            .GetParameters().Select(p => p.Name!).ToArray();

    private static ConfiguracionDeAmbiente Leer(Dictionary<string, string?> banco) =>
        ConfiguracionPorAmbiente.Leer(new ConfigurationBuilder().AddInMemoryCollection(banco).Build(), "Pruebas");

    private static object? Valor(object registro, string propiedad) =>
        registro.GetType().GetProperty(propiedad, BindingFlags.Public | BindingFlags.Instance)!.GetValue(registro);

    public static TheoryData<string> CadaBandera() => [.. Banderas_];

    public static TheoryData<string> CadaDestino() => [.. Destinos_];

    [Theory]
    [MemberData(nameof(CadaBandera))]
    public void Cada_bandera_se_lee_de_su_clave_y_solo_de_ella(string bandera)
    {
        var banco = Banderas_.ToDictionary(b => $"Decant:Banderas:{b}", b => (string?)(b == bandera ? "true" : "false"));
        var leida = Leer(banco).Banderas;
        foreach (var b in Banderas_)
        {
            Assert.Equal(b == bandera, (bool)Valor(leida, b)!);
        }
    }

    [Theory]
    [MemberData(nameof(CadaDestino))]
    public void Cada_destino_se_lee_de_su_clave(string destino)
    {
        var banco = Destinos_.ToDictionary(d => $"Decant:Destinos:{d}", d => (string?)$"valor-de-{d}");
        Assert.Equal($"valor-de-{destino}", Valor(Leer(banco).Destinos, destino));
    }

    [Fact]
    public void Una_bandera_ausente_queda_apagada_y_una_que_no_es_booleana_detiene_el_arranque()
    {
        Assert.Equal(new Banderas(false, false, false), Leer([]).Banderas);
        var error = Assert.Throws<InvalidOperationException>(() =>
            Leer(new() { ["Decant:Banderas:VencerAutomatico"] = "ture" }));
        Assert.Contains("Decant:Banderas:VencerAutomatico", error.Message, StringComparison.Ordinal);
    }

    public static TheoryData<string> CadaAppsettings() =>
        [.. Directory.GetFiles(CarpetaDeLaApi(), "appsettings*.json").Select(Path.GetFileName).OfType<string>()];

    /// <summary>Toda clave bajo «Decant» en los appsettings de la API es una propiedad de las opciones.</summary>
    [Theory]
    [MemberData(nameof(CadaAppsettings))]
    public void Ninguna_clave_de_los_appsettings_sobra(string archivo)
    {
        using var json = JsonDocument.Parse(File.ReadAllText(Path.Combine(CarpetaDeLaApi(), archivo)));
        var conocidas = new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            ["Banderas"] = Banderas_,
            ["Destinos"] = Destinos_,
        };
        foreach (var seccion in json.RootElement.GetProperty(ConfiguracionPorAmbiente.Seccion).EnumerateObject())
        {
            Assert.True(conocidas.ContainsKey(seccion.Name), $"{archivo}: sección desconocida {seccion.Name}");
            foreach (var clave in seccion.Value.EnumerateObject())
            {
                Assert.Contains(clave.Name, conocidas[seccion.Name]);
            }
        }
    }

    /// <summary>Lo que imprime el CI (orden <c>decant configuracion</c>) por cada ambiente con sus appsettings reales.</summary>
    [Fact]
    public void Lo_impreso_por_ambiente_trae_todas_las_banderas_y_destinos_sin_secretos()
    {
        foreach (var ambiente in ConfiguracionPorAmbiente.Ambientes)
        {
            var configuracion = new ConfigurationBuilder()
                .AddJsonFile(Path.Combine(CarpetaDeLaApi(), "appsettings.json"))
                .AddJsonFile(Path.Combine(CarpetaDeLaApi(), $"appsettings.{ambiente}.json"))
                .Build();
            var leida = ConfiguracionPorAmbiente.Leer(configuracion, ambiente);
            var texto = string.Join('\n', ConfiguracionPorAmbiente.Describir(leida));
            Assert.Contains($"[{ambiente}]", texto, StringComparison.Ordinal);
            foreach (var etiqueta in new[] { "vencer automático=", "conciliar automático=", "avisar al corresponsal=" })
            {
                Assert.Contains(etiqueta, texto, StringComparison.Ordinal);
            }

            Assert.Contains(leida.Destinos.Corresponsal, texto, StringComparison.Ordinal);
            Assert.Contains(leida.Destinos.CorreoDeOperaciones, texto, StringComparison.Ordinal);
            Assert.DoesNotContain("ERROR", texto, StringComparison.Ordinal);
            Assert.DoesNotContain("Password", texto, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("ConnectionStrings", texto, StringComparison.OrdinalIgnoreCase);
        }
    }

    private static string CarpetaDeLaApi()
    {
        var carpeta = new DirectoryInfo(AppContext.BaseDirectory);
        while (carpeta is not null && !File.Exists(Path.Combine(carpeta.FullName, "Decant.slnx")))
        {
            carpeta = carpeta.Parent;
        }

        return Path.Combine(carpeta?.FullName ?? throw new DirectoryNotFoundException("Decant.slnx"), "src",
            "Decant.Api");
    }
}
