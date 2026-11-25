using System.Globalization;
using System.Text.Encodings.Web;
using System.Text.Json;
using Decant.Application;
using Decant.Application.Abstracciones;
using Decant.Application.Carga;
using Decant.Application.Consultas;
using Decant.Application.Motor;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Infrastructure;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Decant.Cli;

/// <summary>
/// Lotes del TO-BE (la misma composición que la API):
/// <code>
///   decant migrar      --base decant_migracion --universo U --oraculo O
///   decant reproducir  --base decant_motor --universo U [--hasta 2023-12-29T09:44:36Z] [--sin-vencer] [--sin-conciliar]
///   decant reporte-ordenes --base decant_sombra --desde 2023-12-01 --hasta 2023-12-29 --salida reporte.jsonl
///   decant configuracion [--ambiente Produccion]
/// </code>
/// La conexión base sale de la variable DECANT_PG (sin la base); nunca de la línea de órdenes.
/// </summary>
public static class Program
{
    private static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    private static readonly JsonSerializerOptions JsonEnLinea = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    };

    public static async Task<int> Main(string[] args)
    {
        if (args.Length == 0)
        {
            Console.Error.WriteLine("uso: decant migrar|reproducir|reporte-ordenes|configuracion …");
            return 2;
        }

        var opciones = Opciones(args[1..]);
        try
        {
            return args[0] switch
            {
                "configuracion" => Configuracion(opciones),
                "migrar" => await Migrar(opciones),
                "reproducir" => await Reproducir(opciones),
                "reporte-ordenes" => await Reporte(opciones),
                _ => throw new ArgumentException($"orden desconocida: {args[0]}"),
            };
        }
        catch (ArgumentException e)
        {
            Console.Error.WriteLine(e.Message);
            return 2;
        }
    }

    private static Dictionary<string, string?> Opciones(string[] args)
    {
        var resultado = new Dictionary<string, string?>(StringComparer.Ordinal);
        for (var i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException($"argumento inesperado: {args[i]}");
            }

            var nombre = args[i][2..];
            var valor = i + 1 < args.Length && !args[i + 1].StartsWith("--", StringComparison.Ordinal)
                ? args[++i]
                : null;
            resultado[nombre] = valor;
        }

        return resultado;
    }

    private static string Requerida(Dictionary<string, string?> o, string nombre) =>
        o.GetValueOrDefault(nombre) ?? throw new ArgumentException($"falta --{nombre}");

    private static ServiceProvider Componer(Dictionary<string, string?> o, string? universo = null,
        string? oraculo = null)
    {
        var baseDeDatos = Requerida(o, "base");
        var conexion = Servicios.ConexionDeLote(Environment.GetEnvironmentVariable("DECANT_PG")
            ?? throw new ArgumentException("falta la variable DECANT_PG (conexión a PostgreSQL sin la base)"),
            baseDeDatos);
        return new ServiceCollection().AgregarDecant(conexion, universo, oraculo).BuildServiceProvider();
    }

    /// <summary>Crea la base si no existe y aplica las migraciones: el esquema se compara después de cada carga.</summary>
    private static Task Esquema(IServiceProvider servicios) => servicios.AplicarMigracionesAsync();

    private static async Task<int> Migrar(Dictionary<string, string?> o)
    {
        await using var servicios = Componer(o, Requerida(o, "universo"), Requerida(o, "oraculo"));
        await Esquema(servicios);
        await using var alcance = servicios.CreateAsyncScope();
        var resumen = await alcance.ServiceProvider.GetRequiredService<IMediador>()
            .EnviarAsync(new MigrarHistorico(o.GetValueOrDefault("origen") ?? "universo+oraculo"));
        Console.WriteLine(JsonSerializer.Serialize(resumen, Json));
        return resumen.Errores.Count == 0 ? 0 : 1;
    }

    private static async Task<int> Reproducir(Dictionary<string, string?> o)
    {
        await using var servicios = Componer(o, Requerida(o, "universo"));
        await Esquema(servicios);
        var banderas = Banderas.Todas with
        {
            VencerAutomatico = !o.ContainsKey("sin-vencer"),
            ConciliarAutomatico = !o.ContainsKey("sin-conciliar"),
        };
        DateTimeOffset? hasta = o.GetValueOrDefault("hasta") is { } h
            ? DateTimeOffset.Parse(h, CultureInfo.InvariantCulture)
            : null;
        await using var alcance = servicios.CreateAsyncScope();
        var resumen = await alcance.ServiceProvider.GetRequiredService<IMediador>()
            .EnviarAsync(new ReproducirUniverso(new OpcionesDelMotor(banderas, hasta),
                o.GetValueOrDefault("origen") ?? "universo"));
        Console.WriteLine(JsonSerializer.Serialize(resumen, Json));
        return 0;
    }

    /// <summary>El reporte de órdenes del TO-BE en el formato de las salidas publicadas del legado (JSON Lines con
    /// encabezado), con cada hora en su zona y su desfase.</summary>
    private static async Task<int> Reporte(Dictionary<string, string?> o)
    {
        await using var servicios = Componer(o);
        var desde = DateOnly.Parse(Requerida(o, "desde"), CultureInfo.InvariantCulture);
        var hasta = DateOnly.Parse(Requerida(o, "hasta"), CultureInfo.InvariantCulture);
        await using var alcance = servicios.CreateAsyncScope();
        var renglones = await alcance.ServiceProvider.GetRequiredService<IMediador>()
            .EnviarAsync(new ConsultarReporteDeOrdenes(desde, hasta));
        var salida = Requerida(o, "salida");
        await using var escritor = new StreamWriter(salida);
        string[] columnas =
        [
            "folio", "uetr", "referencia_mt103", "fecha_envio", "fecha_valor", "bic_corresponsal", "beneficiario",
            "moneda", "monto", "gastos", "estatus", "concepto", "monto_partida", "fecha_partida",
        ];
        await escritor.WriteLineAsync(JsonSerializer.Serialize(columnas, JsonEnLinea));
        foreach (var fila in renglones.Select(Fila))
        {
            await escritor.WriteLineAsync(JsonSerializer.Serialize(fila, JsonEnLinea));
        }

        Console.WriteLine($"{renglones.Count} renglones → {salida}");
        return 0;
    }

    /// <summary>Un renglón del reporte en el orden de columnas del legado, con cada hora en su zona.</summary>
    private static string?[] Fila(RenglonDeReporte r) =>
    [
        r.Folio, r.Uetr.ToString(), r.ReferenciaMt103, Hora(r.FechaEnvio, Zonas.CiudadDeMexico),
        r.FechaValor.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), r.BicCorresponsal, r.Beneficiario,
        r.Moneda, r.Monto.ToString(CultureInfo.InvariantCulture), r.Gastos, r.Estatus, r.Concepto,
        r.MontoPartida.ToString(CultureInfo.InvariantCulture), Hora(r.FechaPartida, Zonas.NuevaYork),
    ];

    private static string Hora(DateTimeOffset instante, TimeZoneInfo zona) =>
        Zonas.EnZona(instante, zona).ToString("yyyy-MM-dd'T'HH:mm:sszzz", CultureInfo.InvariantCulture);

    /// <summary>Banderas y destinos de cada ambiente, sin secretos. Sale con 1 si alguno no valida.</summary>
    private static int Configuracion(Dictionary<string, string?> o)
    {
        var ambientes = o.GetValueOrDefault("ambiente") is { } a ? [a] : ConfiguracionPorAmbiente.Ambientes;
        var errores = 0;
        foreach (var ambiente in ambientes)
        {
            var configuracion = new ConfigurationBuilder()
                .SetBasePath(AppContext.BaseDirectory)
                .AddJsonFile("appsettings.json", optional: false)
                .AddJsonFile($"appsettings.{ambiente}.json", optional: false)
                .Build();
            var leida = ConfiguracionPorAmbiente.Leer(configuracion, ambiente);
            foreach (var linea in ConfiguracionPorAmbiente.Describir(leida))
            {
                Console.WriteLine(linea);
            }

            errores += leida.Validar().Count;
        }

        return errores == 0 ? 0 : 1;
    }
}
