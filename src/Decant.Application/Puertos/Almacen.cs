using Decant.Domain.Conciliacion;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;

namespace Decant.Application.Puertos;

/// <summary>Una carga o un replay: qué se corrió, con qué reglas y banderas.</summary>
public sealed record Corrida(
    string Tipo, string VersionDeReglas, DateTimeOffset Inicio, DateTimeOffset? Hasta, Banderas? Banderas,
    string Origen);

/// <summary>D3 visible: la confirmación que el legado tiraba en silencio queda registrada con su motivo.</summary>
public sealed record LiquidacionDescartada(
    Guid Uetr, string ReferenciaMt103, string TrnCorresponsal, DateTimeOffset Instante, decimal Abono,
    decimal Comision, string Motivo);

public sealed record EstadoTobe(
    Corrida Corrida,
    IReadOnlyList<Moneda> Monedas,
    IReadOnlyDictionary<string, int> Consecutivos,
    IReadOnlyList<Operacion> Operaciones,
    IReadOnlyList<OrdenDePago> Ordenes,
    IReadOnlyList<LiquidacionDescartada> Descartadas,
    IReadOnlyList<Marca> Marcas);

/// <summary>Escritura del TO-BE en bloque y lectura de lo resuelto para reprocesar.</summary>
public interface IAlmacenTobe
{
    /// <summary>Reemplaza el estado completo (carga histórica o replay) en una transacción.</summary>
    Task GuardarAsync(EstadoTobe estado, CancellationToken ct);

    Task<IReadOnlyDictionary<Guid, EstadoDeDocumento>> EstadosAsync(CancellationToken ct);

    /// <summary>Escribe el estatus y las horas de cada documento (el resultado de un reproceso).</summary>
    Task ActualizarEstadosAsync(IReadOnlyDictionary<Guid, EstadoDeDocumento> estados, Corrida corrida,
        CancellationToken ct);
}
