namespace Decant.Application.Puertos;

/// <summary>Dónde va una operación en la lista del día: su instante y, para desempatar, su id (el orden de T1).</summary>
public sealed record PosicionDeOperacion(DateTimeOffset FechaOperacion, long Id);

/// <summary>Dónde va un renglón en el reporte: fecha valor, folio y renglón de la partida (el orden de T2).</summary>
public sealed record PosicionDeRenglon(DateOnly FechaValor, string Folio, short Renglon);

/// <summary>Un renglón del reporte con su posición, para seguir leyendo «después de» él.</summary>
public sealed record RenglonConPosicion(RenglonDeReporte Renglon, PosicionDeRenglon Posicion);

/// <summary>Una página leída por llave de conjunto: sus elementos en orden y si hay más después del último.</summary>
public sealed record Pagina<T>(IReadOnlyList<T> Elementos, bool HayMas);

/// <summary>
/// Lecturas para quien pide muchas cosas a la vez: páginas por llave de conjunto (keyset: «después de» una posición,
/// nunca por desplazamiento) y lotes por llave (una consulta para N operaciones, órdenes o UETR, no N consultas).
/// Cada llamada es independiente de las demás: se pueden hacer en paralelo dentro de la misma petición.
/// </summary>
public interface IConsultasEnLote
{
    Task<Pagina<OperacionVista>> OperacionesDelDiaAsync(DateOnly fecha, PosicionDeOperacion? despuesDe, int cuantas,
        CancellationToken ct);

    Task<Pagina<RenglonConPosicion>> RenglonesDelReporteAsync(DateOnly desde, DateOnly hasta,
        PosicionDeRenglon? despuesDe, int cuantos, CancellationToken ct);

    Task<IReadOnlyDictionary<long, OperacionVista>> OperacionesAsync(IReadOnlyCollection<long> ids,
        CancellationToken ct);

    /// <summary>El documento de cada operación, elegido con la MISMA regla que el detalle (ronda 2 a ciegas, T2).</summary>
    Task<IReadOnlyDictionary<long, OrdenVista>> OrdenesDeOperacionesAsync(IReadOnlyCollection<long> operacionIds,
        CancellationToken ct);

    Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> SolicitadoPorElClienteAsync(
        IReadOnlyCollection<Guid> uetrs, CancellationToken ct);

    Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> LiquidadoPorElCorresponsalAsync(
        IReadOnlyCollection<Guid> uetrs, CancellationToken ct);
}
