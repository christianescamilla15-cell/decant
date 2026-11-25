using System.Globalization;
using System.Text.Json;

namespace Decant.Infrastructure.Archivos;

/// <summary>
/// Lector de los paquetes de universo y oráculo: JSON Lines con encabezado (lista de columnas) y filas de textos.
/// Exige que el encabezado sea EXACTAMENTE el esperado: un archivo con una columna de más (por ejemplo, un resultado
/// colado en el universo) no se lee.
/// </summary>
internal static class Jsonl
{
    public static IEnumerable<Fila> Leer(string ruta, IReadOnlyList<string> columnasEsperadas)
    {
        using var lector = new StreamReader(ruta);
        var encabezado = JsonSerializer.Deserialize<string[]>(lector.ReadLine() ?? "[]") ?? [];
        if (!encabezado.SequenceEqual(columnasEsperadas))
        {
            throw new InvalidDataException(
                $"{Path.GetFileName(ruta)}: columnas [{string.Join(", ", encabezado)}], se esperaban " +
                $"[{string.Join(", ", columnasEsperadas)}]");
        }

        var indice = encabezado.Select((c, i) => (c, i)).ToDictionary(x => x.c, x => x.i, StringComparer.Ordinal);
        string? linea;
        while ((linea = lector.ReadLine()) is not null)
        {
            if (linea.Length > 0)
            {
                yield return new Fila(JsonSerializer.Deserialize<string?[]>(linea)!, indice);
            }
        }
    }

    internal readonly record struct Fila(string?[] Valores, IReadOnlyDictionary<string, int> Indice)
    {
        public string? Texto(string columna) => Valores[Indice[columna]];

        public string Requerido(string columna) =>
            Texto(columna) ?? throw new InvalidDataException($"«{columna}» viene nulo");

        public long Largo(string columna) => long.Parse(Requerido(columna), CultureInfo.InvariantCulture);

        public int Entero(string columna) => int.Parse(Requerido(columna), CultureInfo.InvariantCulture);

        public decimal Decimal(string columna) =>
            decimal.Parse(Requerido(columna), NumberStyles.Number, CultureInfo.InvariantCulture);

        public decimal? DecimalONulo(string columna) =>
            Texto(columna) is { } t ? decimal.Parse(t, NumberStyles.Number, CultureInfo.InvariantCulture) : null;

        public DateTime Hora(string columna) =>
            DateTime.SpecifyKind(DateTime.Parse(Requerido(columna), CultureInfo.InvariantCulture,
                DateTimeStyles.None), DateTimeKind.Unspecified);

        public DateOnly Fecha(string columna) =>
            DateOnly.ParseExact(Requerido(columna), "yyyy-MM-dd", CultureInfo.InvariantCulture);
    }
}
