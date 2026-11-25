using Decant.Application;
using Microsoft.Extensions.Configuration;

namespace Decant.Infrastructure;

/// <summary>Lee banderas y destinos de un ambiente (appsettings + appsettings.{ambiente} + variables).</summary>
public static class ConfiguracionPorAmbiente
{
    public static readonly string[] Ambientes = ["Desarrollo", "Pruebas", "Produccion"];

    public static ConfiguracionDeAmbiente Leer(IConfiguration configuracion, string ambiente)
    {
        bool Bandera(string nombre) =>
            bool.TryParse(configuracion[$"Decant:Banderas:{nombre}"], out var valor) && valor;

        return new ConfiguracionDeAmbiente(
            ambiente,
            new Banderas(Bandera("VencerAutomatico"), Bandera("ConciliarAutomatico"), Bandera("NotificarCorresponsal")),
            new Destinos(configuracion["Decant:Destinos:Corresponsal"] ?? string.Empty,
                configuracion["Decant:Destinos:CorreoDeOperaciones"] ?? string.Empty));
    }
}
