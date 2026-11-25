using Decant.Application.Abstracciones;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Reproceso;

namespace Decant.Application.Reproceso;

/// <summary>
/// Aplica el resultado de una corrida con reglas nuevas sobre lo guardado, con la invariante «nunca quitar lo ya
/// resuelto»: lo que se conservaría como estaba se devuelve para que quede visible.
/// </summary>
public sealed record AplicarReproceso(IReadOnlyDictionary<Guid, EstadoDeDocumento> Nuevo, string Origen)
    : ISolicitud<ResultadoDeReproceso>;

public sealed class AplicarReprocesoManejador(IAlmacenTobe almacen, IClock reloj)
    : IManejador<AplicarReproceso, ResultadoDeReproceso>
{
    public async Task<ResultadoDeReproceso> ManejarAsync(AplicarReproceso solicitud, CancellationToken ct)
    {
        var previo = await almacen.EstadosAsync(ct);
        var resultado = Reprocesamiento.Combinar(previo, solicitud.Nuevo);
        var corrida = new Corrida("reproceso", VersionDeReglas.Actual, reloj.AhoraUtc, null, null, solicitud.Origen);
        await almacen.ActualizarEstadosAsync(resultado.Estados, corrida, ct);
        return resultado;
    }
}
