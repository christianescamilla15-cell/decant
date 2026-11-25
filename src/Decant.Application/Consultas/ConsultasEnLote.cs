using Decant.Application.Abstracciones;
using Decant.Application.Puertos;

namespace Decant.Application.Consultas;

/// <summary>Límites de las páginas por llave de conjunto (los mismos para cualquier consumidor).</summary>
public static class Paginas
{
    public const int Maximo = 100;

    public static void Validar(int cuantas, string nombre)
    {
        if (cuantas is < 1 or > Maximo)
        {
            throw new ArgumentOutOfRangeException(nombre, cuantas, $"la página va de 1 a {Maximo}");
        }
    }
}

/// <summary>T1 por páginas: las operaciones de un día local en orden explícito (fecha y id), después de una posición.</summary>
public sealed record ConsultarPaginaDeOperaciones(DateOnly Fecha, PosicionDeOperacion? DespuesDe, int Cuantas)
    : ISolicitud<Pagina<OperacionVista>>;

/// <summary>T2 por páginas: los renglones del reporte en su orden explícito, después de una posición.</summary>
public sealed record ConsultarPaginaDelReporte(DateOnly Desde, DateOnly Hasta, PosicionDeRenglon? DespuesDe,
    int Cuantos) : ISolicitud<Pagina<RenglonConPosicion>>;

public sealed record ConsultarOperaciones(IReadOnlyCollection<long> Ids)
    : ISolicitud<IReadOnlyDictionary<long, OperacionVista>>;

public sealed record ConsultarOrdenesDeOperaciones(IReadOnlyCollection<long> OperacionIds)
    : ISolicitud<IReadOnlyDictionary<long, OrdenVista>>;

/// <summary>Las dos listas del detalle, por lo que SON (T4).</summary>
public enum LadoDePartida
{
    SolicitadoPorElCliente,
    LiquidadoPorElCorresponsal,
}

public sealed record ConsultarPartidas(IReadOnlyCollection<Guid> Uetrs, LadoDePartida Lado)
    : ISolicitud<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>>;

public sealed class ConsultarPaginaDeOperacionesManejador(IConsultasEnLote consultas)
    : IManejador<ConsultarPaginaDeOperaciones, Pagina<OperacionVista>>
{
    public Task<Pagina<OperacionVista>> ManejarAsync(ConsultarPaginaDeOperaciones solicitud, CancellationToken ct)
    {
        Paginas.Validar(solicitud.Cuantas, nameof(solicitud.Cuantas));
        return consultas.OperacionesDelDiaAsync(solicitud.Fecha, solicitud.DespuesDe, solicitud.Cuantas, ct);
    }
}

public sealed class ConsultarPaginaDelReporteManejador(IConsultasEnLote consultas)
    : IManejador<ConsultarPaginaDelReporte, Pagina<RenglonConPosicion>>
{
    public Task<Pagina<RenglonConPosicion>> ManejarAsync(ConsultarPaginaDelReporte solicitud, CancellationToken ct)
    {
        if (solicitud.Hasta < solicitud.Desde)
        {
            throw new ArgumentException("«hasta» es anterior a «desde»", nameof(solicitud));
        }

        Paginas.Validar(solicitud.Cuantos, nameof(solicitud.Cuantos));
        return consultas.RenglonesDelReporteAsync(solicitud.Desde, solicitud.Hasta, solicitud.DespuesDe,
            solicitud.Cuantos, ct);
    }
}

public sealed class ConsultarOperacionesManejador(IConsultasEnLote consultas)
    : IManejador<ConsultarOperaciones, IReadOnlyDictionary<long, OperacionVista>>
{
    public Task<IReadOnlyDictionary<long, OperacionVista>> ManejarAsync(ConsultarOperaciones solicitud,
        CancellationToken ct) => consultas.OperacionesAsync(solicitud.Ids, ct);
}

public sealed class ConsultarOrdenesDeOperacionesManejador(IConsultasEnLote consultas)
    : IManejador<ConsultarOrdenesDeOperaciones, IReadOnlyDictionary<long, OrdenVista>>
{
    public Task<IReadOnlyDictionary<long, OrdenVista>> ManejarAsync(ConsultarOrdenesDeOperaciones solicitud,
        CancellationToken ct) => consultas.OrdenesDeOperacionesAsync(solicitud.OperacionIds, ct);
}

public sealed class ConsultarPartidasManejador(IConsultasEnLote consultas)
    : IManejador<ConsultarPartidas, IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>>
{
    public Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> ManejarAsync(ConsultarPartidas solicitud,
        CancellationToken ct) => solicitud.Lado switch
    {
        LadoDePartida.SolicitadoPorElCliente => consultas.SolicitadoPorElClienteAsync(solicitud.Uetrs, ct),
        LadoDePartida.LiquidadoPorElCorresponsal => consultas.LiquidadoPorElCorresponsalAsync(solicitud.Uetrs, ct),
        _ => throw new ArgumentOutOfRangeException(nameof(solicitud), solicitud.Lado, "lado desconocido"),
    };
}
