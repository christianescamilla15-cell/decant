using Decant.Application;
using Microsoft.Extensions.Configuration;

namespace Decant.Infrastructure;

/// <summary>
/// Lee banderas y destinos de un ambiente (appsettings + appsettings.{ambiente} + variables). Las claves son los
/// nombres de las propiedades (<c>nameof</c>) y una prueba exige que CADA propiedad se lea de su clave. Una bandera
/// ausente queda apagada («sólo marca»); una con valor que no es booleano detiene el arranque.
/// </summary>
public static class ConfiguracionPorAmbiente
{
    public const string Seccion = "Decant";

    public static readonly string[] Ambientes = ["Desarrollo", "Pruebas", "Produccion"];

    public static ConfiguracionDeAmbiente Leer(IConfiguration configuracion, string ambiente)
    {
        bool Bandera(string nombre)
        {
            var clave = $"{Seccion}:{nameof(Banderas)}:{nombre}";
            var texto = configuracion[clave];
            if (texto is null)
            {
                return false;
            }

            return bool.TryParse(texto, out var valor)
                ? valor
                : throw new InvalidOperationException($"{clave} no es booleano: «{texto}»");
        }

        string Destino(string nombre) => configuracion[$"{Seccion}:{nameof(Destinos)}:{nombre}"] ?? string.Empty;

        return new ConfiguracionDeAmbiente(
            ambiente,
            new Banderas(Bandera(nameof(Banderas.VencerAutomatico)), Bandera(nameof(Banderas.ConciliarAutomatico)),
                Bandera(nameof(Banderas.NotificarCorresponsal))),
            new Destinos(Destino(nameof(Destinos.Corresponsal)), Destino(nameof(Destinos.CorreoDeOperaciones))));
    }

    /// <summary>Lo que imprime el CI por ambiente: banderas, lo que queda en «sólo marca» y destinos. Sin secretos.</summary>
    public static IReadOnlyList<string> Describir(ConfiguracionDeAmbiente configuracion)
    {
        var b = configuracion.Banderas;
        var soloMarca = new[]
        {
            b.VencerAutomatico ? null : "vencimiento",
            b.ConciliarAutomatico ? null : "conciliación",
        }.OfType<string>().ToList();
        var lineas = new List<string>
        {
            $"[{configuracion.Ambiente}]",
            $"  banderas: vencer automático={Si(b.VencerAutomatico)} · conciliar automático=" +
            $"{Si(b.ConciliarAutomatico)} · avisar al corresponsal={Si(b.NotificarCorresponsal)}",
            $"  sólo marca: {(soloMarca.Count == 0 ? "ninguna acción" : string.Join(", ", soloMarca))}",
            $"  destinos: corresponsal={configuracion.Destinos.Corresponsal} · correo de operaciones=" +
            configuracion.Destinos.CorreoDeOperaciones,
        };
        lineas.AddRange(configuracion.Validar().Select(e => $"  ERROR: {e}"));
        return lineas;
    }

    private static string Si(bool valor) => valor ? "sí" : "no";
}
