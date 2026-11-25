namespace Decant.Domain.Divisas;

/// <summary>
/// R01 / R04. Consumibles de folio por serie (<c>dbo.folio</c>): «FX» por operación y «OP» por documento. Cada alta
/// toma el siguiente y lo avanza; el folio es la serie y el número a 9 dígitos.
/// </summary>
public sealed class Consecutivos
{
    public const string SerieOperaciones = "FX";
    public const string SerieOrdenes = "OP";

    private readonly Dictionary<string, int> _siguiente;

    public Consecutivos(IEnumerable<string> series, int inicial = 1)
    {
        _siguiente = series.ToDictionary(s => s, _ => inicial, StringComparer.Ordinal);
    }

    public Consecutivos(IReadOnlyDictionary<string, int> siguientes)
    {
        _siguiente = new Dictionary<string, int>(siguientes, StringComparer.Ordinal);
    }

    public IReadOnlyDictionary<string, int> Siguientes => _siguiente;

    public string Tomar(string serie)
    {
        var n = _siguiente[serie];
        _siguiente[serie] = n + 1;
        return Formatear(serie, n);
    }

    public static string Formatear(string serie, int numero) => $"{serie}-{numero:D9}";
}
