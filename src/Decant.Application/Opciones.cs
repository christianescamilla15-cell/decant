namespace Decant.Application;

/// <summary>
/// Banderas SÓLO para lo que tiene efecto lateral: las acciones automáticas del job (vencer y conciliar cambian el
/// estatus de los documentos) y el aviso al vecino (el corresponsal). No hay una bandera por regla. Con una bandera
/// APAGADA el motor no actúa: evalúa y deja la marca ✔/✘ por caso («sólo marca»).
/// </summary>
public sealed record Banderas(bool VencerAutomatico, bool ConciliarAutomatico, bool NotificarCorresponsal)
{
    public static Banderas Todas { get; } = new(true, true, false);
}

/// <summary>A dónde sale cada efecto lateral en un ambiente.</summary>
public sealed record Destinos(string Corresponsal, string CorreoDeOperaciones);

/// <summary>Configuración de un ambiente (la imprime el CI, sin secretos).</summary>
public sealed record ConfiguracionDeAmbiente(string Ambiente, Banderas Banderas, Destinos Destinos)
{
    public const string EmuladorDelCorresponsal = "emulador";

    /// <summary>
    /// Errores de la configuración: fuera de producción ningún aviso puede salir al corresponsal real, y en
    /// producción el aviso no se enciende antes de tener su contrato y su humo (S4).
    /// </summary>
    public IReadOnlyList<string> Validar()
    {
        var errores = new List<string>();
        var esProduccion = Ambiente == "Produccion";
        if (!esProduccion && !Destinos.Corresponsal.StartsWith(EmuladorDelCorresponsal, StringComparison.Ordinal))
        {
            errores.Add($"{Ambiente}: el corresponsal debe ser el emulador, no «{Destinos.Corresponsal}»");
        }

        if (esProduccion && Banderas.NotificarCorresponsal)
        {
            errores.Add("Produccion: el aviso al corresponsal no se enciende sin contrato ni humo (S4)");
        }

        if (string.IsNullOrWhiteSpace(Destinos.CorreoDeOperaciones))
        {
            errores.Add($"{Ambiente}: falta el correo de operaciones");
        }

        return errores;
    }
}

/// <summary>Opciones del replay: banderas y hasta qué instante (inclusive) se procesa el universo.</summary>
public sealed record OpcionesDelMotor(Banderas Banderas, DateTimeOffset? Hasta);
