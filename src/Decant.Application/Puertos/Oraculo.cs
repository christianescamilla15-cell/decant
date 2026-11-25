namespace Decant.Application.Puertos;

public sealed record OperacionDelOraculo(long Id, string Folio, decimal MontoMxn, decimal? TipoCambioCalculado);

public sealed record OrdenDelOraculo(long Id, string Folio, string Estatus, decimal? Horas);

public sealed record PartidaCorresponsalDelOraculo(long Id, long OrdenId, short Renglon, string Concepto, string Moneda);

public sealed record PartidaClienteDelOraculo(
    long Id, long OrdenId, short Renglon, string Concepto, string Moneda, decimal Monto, DateTime FechaHoraLocal,
    string Referencia);

/// <summary>
/// Lo que el legado CALCULÓ y guardó (columnas de resultado). Sólo lo lee la carga histórica, que lleva la historia
/// tal cual; el replay del motor no tiene acceso a este puerto.
/// </summary>
public interface IOraculoHistorico
{
    IReadOnlyDictionary<string, int> Consecutivos();

    IEnumerable<OperacionDelOraculo> Operaciones();

    IEnumerable<OrdenDelOraculo> Ordenes();

    IEnumerable<PartidaCorresponsalDelOraculo> PartidasDelCorresponsal();

    IEnumerable<PartidaClienteDelOraculo> PartidasDelCliente();
}
