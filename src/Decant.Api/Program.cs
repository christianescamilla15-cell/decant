using Decant.Api;
using Decant.Application.Abstracciones;
using Decant.Application.Consultas;
using Decant.Infrastructure;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AgregarDecant(builder.Configuration.GetConnectionString("Decant") ?? string.Empty);
builder.Services.AddSingleton(ConfiguracionPorAmbiente.Leer(builder.Configuration, builder.Environment.EnvironmentName));
builder.Services.AddProblemDetails();

var app = builder.Build();
app.UseExceptionHandler();

app.MapGet("/salud", () => Results.Text("ok"));

app.MapGet("/api/operaciones/{id:long}", async (long id, IMediador mediador, CancellationToken ct) =>
    await mediador.EnviarAsync(new ConsultarDetalle(id), ct) is { } detalle
        ? Results.Ok(Presentacion.DeDetalle(detalle))
        : Results.NotFound());

app.MapGet("/api/operaciones", async (DateOnly fecha, int? maximo, IMediador mediador, CancellationToken ct) =>
{
    if (maximo is < 1 or > 1000)
    {
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["maximo"] = ["va de 1 a 1000"],
        });
    }

    var lista = await mediador.EnviarAsync(new ConsultarLista(fecha, maximo ?? 200), ct);
    return Results.Ok(lista.Select(o => o with { FechaOperacion = Presentacion.Mx(o.FechaOperacion) }));
});

app.MapGet("/api/reportes/ordenes", async (DateOnly desde, DateOnly hasta, IMediador mediador,
    CancellationToken ct) =>
{
    if (hasta < desde)
    {
        return Results.ValidationProblem(new Dictionary<string, string[]>
        {
            ["hasta"] = ["es anterior a «desde»"],
        });
    }

    var renglones = await mediador.EnviarAsync(new ConsultarReporteDeOrdenes(desde, hasta), ct);
    return Results.Ok(renglones.Select(r => r with
    {
        FechaEnvio = Presentacion.Mx(r.FechaEnvio),
        FechaPartida = Presentacion.Ny(r.FechaPartida),
    }));
});

// Banderas y destinos del ambiente (sin secretos): lo mismo que imprime el CI.
app.MapGet("/api/configuracion", (Decant.Application.ConfiguracionDeAmbiente configuracion) =>
    Results.Ok(new { configuracion.Ambiente, configuracion.Banderas, configuracion.Destinos,
        Errores = configuracion.Validar() }));

app.Run();

/// <summary>Punto de entrada visible para WebApplicationFactory en las pruebas.</summary>
public partial class Program;
