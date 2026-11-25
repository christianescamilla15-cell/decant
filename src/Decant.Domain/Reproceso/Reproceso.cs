using Decant.Domain.Pagos;

namespace Decant.Domain.Reproceso;

/// <summary>Versión de las reglas del motor: va en cada corrida y en todo resultado guardado.</summary>
public static class VersionDeReglas
{
    public const string Actual = "s2-2026.11.24";
}

/// <summary>Lo que una corrida dejó resuelto (o no) para un documento.</summary>
public sealed record EstadoDeDocumento(EstatusOrden Estatus, decimal? Horas, string VersionDeReglas);

/// <summary>Un documento que la corrida nueva habría «des-resuelto» y que se conserva como estaba.</summary>
public sealed record Conservado(Guid Uetr, EstadoDeDocumento Previo, EstadoDeDocumento? Propuesto, string Motivo);

public sealed record ResultadoDeReproceso(
    IReadOnlyDictionary<Guid, EstadoDeDocumento> Estados, IReadOnlyList<Conservado> Conservados);

/// <summary>
/// Invariante: reprocesar con reglas nuevas NUNCA quita lo ya resuelto. «Resuelto» es conciliado (CONCILIADA o
/// DIFERENCIA): el corresponsal pagó y el job ya lo cuadró. Una regla nueva puede cambiar el veredicto (DIFERENCIA →
/// CONCILIADA, por ejemplo con los decimales de ISO 4217) o las horas, pero no regresar el documento a ENVIADA,
/// LIQUIDADA o VENCIDA, ni hacerlo desaparecer: en ese caso se conserva el estado previo y se reporta.
/// </summary>
public static class Reprocesamiento
{
    public static bool EstaResuelto(EstatusOrden estatus) =>
        estatus is EstatusOrden.Conciliada or EstatusOrden.Diferencia;

    public static ResultadoDeReproceso Combinar(
        IReadOnlyDictionary<Guid, EstadoDeDocumento> previo, IReadOnlyDictionary<Guid, EstadoDeDocumento> nuevo)
    {
        var estados = new Dictionary<Guid, EstadoDeDocumento>(nuevo);
        var conservados = new List<Conservado>();
        foreach (var (uetr, antes) in previo)
        {
            if (!EstaResuelto(antes.Estatus))
            {
                continue;
            }

            if (!nuevo.TryGetValue(uetr, out var propuesto))
            {
                estados[uetr] = antes;
                conservados.Add(new Conservado(uetr, antes, null, "la corrida nueva no trae el documento"));
            }
            else if (!EstaResuelto(propuesto.Estatus))
            {
                estados[uetr] = antes;
                conservados.Add(new Conservado(uetr, antes, propuesto,
                    $"la corrida nueva lo regresaría a {EstatusDeOrden.Codigo(propuesto.Estatus)}"));
            }
        }

        return new ResultadoDeReproceso(estados, conservados);
    }
}
