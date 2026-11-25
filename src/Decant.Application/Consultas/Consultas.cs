using Decant.Application.Abstracciones;
using Decant.Application.Puertos;

namespace Decant.Application.Consultas;

public sealed record ConsultarDetalle(long OperacionId) : ISolicitud<DetalleDeOperacion?>;

public sealed record ConsultarReporteDeOrdenes(DateOnly Desde, DateOnly Hasta) : ISolicitud<IReadOnlyList<RenglonDeReporte>>;

/// <summary>T1: la lista del día con orden EXPLÍCITO (fecha y luego id); el legado cortaba en TOP sin ORDER BY.</summary>
public sealed record ConsultarLista(DateOnly Fecha, int Maximo = 200) : ISolicitud<IReadOnlyList<OperacionDeLista>>;

public sealed class ConsultarDetalleManejador(IConsultasTobe consultas)
    : IManejador<ConsultarDetalle, DetalleDeOperacion?>
{
    public Task<DetalleDeOperacion?> ManejarAsync(ConsultarDetalle solicitud, CancellationToken ct) =>
        consultas.DetalleAsync(solicitud.OperacionId, ct);
}

public sealed class ConsultarReporteDeOrdenesManejador(IConsultasTobe consultas)
    : IManejador<ConsultarReporteDeOrdenes, IReadOnlyList<RenglonDeReporte>>
{
    public Task<IReadOnlyList<RenglonDeReporte>> ManejarAsync(ConsultarReporteDeOrdenes solicitud,
        CancellationToken ct)
    {
        if (solicitud.Hasta < solicitud.Desde)
        {
            throw new ArgumentException("«hasta» es anterior a «desde»", nameof(solicitud));
        }

        return consultas.ReporteDeOrdenesAsync(solicitud.Desde, solicitud.Hasta, ct);
    }
}

public sealed class ConsultarListaManejador(IConsultasTobe consultas)
    : IManejador<ConsultarLista, IReadOnlyList<OperacionDeLista>>
{
    public Task<IReadOnlyList<OperacionDeLista>> ManejarAsync(ConsultarLista solicitud, CancellationToken ct)
    {
        if (solicitud.Maximo is < 1 or > 1000)
        {
            throw new ArgumentOutOfRangeException(nameof(solicitud), "el máximo va de 1 a 1000");
        }

        return consultas.ListaAsync(solicitud.Fecha, solicitud.Maximo, ct);
    }
}
