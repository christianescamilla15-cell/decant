using System.Collections.Concurrent;
using System.Data.Common;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Decant.Infrastructure.Persistencia;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.DependencyInjection;

namespace Decant.Api.Tests.GraphQL;

/// <summary>
/// Cuenta los comandos SQL que de verdad llegan a PostgreSQL (un interceptor de EF Core en la composición REAL de la
/// API, la de la fábrica de contextos incluida), con su texto, para medir el N+1 y que lo rechazado no toca la base.
/// </summary>
public sealed class ContadorDeSql : DbCommandInterceptor
{
    private readonly ConcurrentQueue<string> _comandos = new();

    public IReadOnlyList<string> Comandos => [.. _comandos];

    public void Reiniciar() => _comandos.Clear();

    public override ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command,
        CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
    {
        _comandos.Enqueue(command.CommandText);
        return base.ReaderExecutingAsync(command, eventData, result, cancellationToken);
    }

    public override InterceptionResult<DbDataReader> ReaderExecuting(DbCommand command, CommandEventData eventData,
        InterceptionResult<DbDataReader> result)
    {
        _comandos.Enqueue(command.CommandText);
        return base.ReaderExecuting(command, eventData, result);
    }
}

/// <summary>La API completa (WebApplicationFactory) en un ambiente, con una conexión y el contador de SQL.</summary>
public sealed class ApiDePrueba : IAsyncDisposable
{
    private readonly WebApplicationFactory<Program> _base = new();

    public ApiDePrueba(string conexion, string ambiente = "Pruebas")
    {
        Fabrica = _base.WithWebHostBuilder(b => b
            .UseEnvironment(ambiente)
            .UseSetting("ConnectionStrings:Decant", conexion)
            .ConfigureTestServices(s => s.ConfigureDbContext<DecantDbContext>(o => o.AddInterceptors(Sql))));
        Cliente = Fabrica.CreateClient();
    }

    public ContadorDeSql Sql { get; } = new();

    public WebApplicationFactory<Program> Fabrica { get; }

    public HttpClient Cliente { get; }

    /// <summary>POST /graphql con JSON, como lo pide la especificación de GraphQL sobre HTTP.</summary>
    public async Task<Respuesta> Graphql(string consulta, object? variables = null,
        IReadOnlyDictionary<string, string>? encabezados = null)
    {
        using var peticion = new HttpRequestMessage(HttpMethod.Post, "/graphql")
        {
            Content = new StringContent(JsonSerializer.Serialize(new { query = consulta, variables }), Encoding.UTF8,
                "application/json"),
        };
        peticion.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/graphql-response+json"));
        foreach (var (nombre, valor) in encabezados ?? new Dictionary<string, string>())
        {
            peticion.Headers.Add(nombre, valor);
        }

        return await Respuesta.De(await Cliente.SendAsync(peticion));
    }

    public async Task<JsonElement> Rest(string ruta)
    {
        var respuesta = await Cliente.GetAsync(ruta);
        Assert.Equal(HttpStatusCode.OK, respuesta.StatusCode);
        return JsonDocument.Parse(await respuesta.Content.ReadAsStringAsync()).RootElement;
    }

    public async ValueTask DisposeAsync()
    {
        Cliente.Dispose();
        await Fabrica.DisposeAsync();
        await _base.DisposeAsync();
    }
}

public sealed record Respuesta(HttpStatusCode Estado, string? TipoDeContenido, string Texto, JsonElement Cuerpo)
{
    public static async Task<Respuesta> De(HttpResponseMessage http)
    {
        var texto = await http.Content.ReadAsStringAsync();
        var cuerpo = texto.Length == 0 ? default : JsonDocument.Parse(texto).RootElement;
        return new Respuesta(http.StatusCode, http.Content.Headers.ContentType?.MediaType, texto, cuerpo);
    }

    public JsonElement Datos => Cuerpo.GetProperty("data");

    public IReadOnlyList<JsonElement> Errores =>
        Cuerpo.ValueKind == JsonValueKind.Object && Cuerpo.TryGetProperty("errors", out var e)
            ? [.. e.EnumerateArray()]
            : [];

    public IReadOnlyList<string?> Codigos =>
        [.. Errores.Select(e => e.TryGetProperty("extensions", out var x) && x.TryGetProperty("code", out var c)
            ? c.GetString() : null)];

    /// <summary>Que no haya errores (si los hay, el mensaje los muestra).</summary>
    public Respuesta SinErrores()
    {
        Assert.True(Errores.Count == 0, Texto);
        return this;
    }
}

public static class Repositorio
{
    /// <summary>Una ruta dentro del repositorio (se sube desde la carpeta de salida hasta Decant.slnx).</summary>
    public static string Ruta(params string[] partes)
    {
        var carpeta = new DirectoryInfo(AppContext.BaseDirectory);
        while (carpeta is not null && !File.Exists(Path.Join(carpeta.FullName, "Decant.slnx")))
        {
            carpeta = carpeta.Parent;
        }

        return Path.Join([carpeta?.FullName ?? throw new DirectoryNotFoundException("Decant.slnx"), .. partes]);
    }
}
