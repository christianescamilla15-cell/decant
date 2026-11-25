namespace Decant.Application.Abstracciones;

/// <summary>Una solicitud (consulta o caso de uso) con su respuesta.</summary>
public interface ISolicitud<TRespuesta>;

public interface IManejador<in TSolicitud, TRespuesta>
    where TSolicitud : ISolicitud<TRespuesta>
{
    Task<TRespuesta> ManejarAsync(TSolicitud solicitud, CancellationToken ct);
}

public interface IMediador
{
    Task<TRespuesta> EnviarAsync<TRespuesta>(ISolicitud<TRespuesta> solicitud, CancellationToken ct = default);
}

/// <summary>
/// Mediador propio y delgado: resuelve del contenedor el manejador de la solicitud y lo llama. Sin tuberías; si falta
/// el manejador, falla al primer uso con el nombre de la solicitud.
/// </summary>
public sealed class Mediador(IServiceProvider servicios) : IMediador
{
    public Task<TRespuesta> EnviarAsync<TRespuesta>(ISolicitud<TRespuesta> solicitud, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(solicitud);
        var tipo = typeof(Envoltura<,>).MakeGenericType(solicitud.GetType(), typeof(TRespuesta));
        var envoltura = (IEnvoltura<TRespuesta>)Activator.CreateInstance(tipo)!;
        return envoltura.Enviar(solicitud, servicios, ct);
    }

    private interface IEnvoltura<TRespuesta>
    {
        Task<TRespuesta> Enviar(ISolicitud<TRespuesta> solicitud, IServiceProvider servicios, CancellationToken ct);
    }

    private sealed class Envoltura<TSolicitud, TRespuesta> : IEnvoltura<TRespuesta>
        where TSolicitud : ISolicitud<TRespuesta>
    {
        public Task<TRespuesta> Enviar(ISolicitud<TRespuesta> solicitud, IServiceProvider servicios,
            CancellationToken ct)
        {
            var manejador = servicios.GetService(typeof(IManejador<TSolicitud, TRespuesta>))
                as IManejador<TSolicitud, TRespuesta>
                ?? throw new InvalidOperationException($"sin manejador para {typeof(TSolicitud).Name}");
            return manejador.ManejarAsync((TSolicitud)solicitud, ct);
        }
    }
}
