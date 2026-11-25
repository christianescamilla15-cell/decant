using System.Buffers.Text;
using System.Globalization;
using System.Text.Json;
using Decant.Application.Puertos;

namespace Decant.Api.GraphQL;

/// <summary>
/// Cursores opacos de las páginas por llave de conjunto: la POSICIÓN del último elemento (no un desplazamiento) y los
/// argumentos de la consulta que la produjo. Un cursor de otra consulta (otro día, otro rango) o alterado se rechaza
/// con <see cref="CodigosDeError.ArgumentoInvalido"/>; nunca se interpreta a medias.
/// </summary>
internal static class Cursores
{
    private const string Version = "v1";
    private const int LargoMaximo = 256;

    public static string DeOperacion(DateOnly fecha, PosicionDeOperacion posicion) =>
        Codificar("operaciones", Fecha(fecha), posicion.FechaOperacion.UtcTicks.ToString(CultureInfo.InvariantCulture),
            posicion.Id.ToString(CultureInfo.InvariantCulture));

    public static PosicionDeOperacion LeerOperacion(string cursor, DateOnly fecha)
    {
        var partes = Decodificar(cursor, "operaciones", 3);
        if (partes[0] != Fecha(fecha) ||
            !long.TryParse(partes[1], NumberStyles.None, CultureInfo.InvariantCulture, out var ticks) ||
            ticks > DateTimeOffset.MaxValue.UtcTicks ||
            !long.TryParse(partes[2], NumberStyles.None, CultureInfo.InvariantCulture, out var id))
        {
            throw Invalido();
        }

        return new PosicionDeOperacion(new DateTimeOffset(ticks, TimeSpan.Zero), id);
    }

    public static string DeRenglon(DateOnly desde, DateOnly hasta, PosicionDeRenglon posicion) =>
        Codificar("reporteDeOrdenes", Fecha(desde), Fecha(hasta), Fecha(posicion.FechaValor), posicion.Folio,
            posicion.Renglon.ToString(CultureInfo.InvariantCulture));

    public static PosicionDeRenglon LeerRenglon(string cursor, DateOnly desde, DateOnly hasta)
    {
        var partes = Decodificar(cursor, "reporteDeOrdenes", 5);
        if (partes[0] != Fecha(desde) || partes[1] != Fecha(hasta) ||
            !DateOnly.TryParseExact(partes[2], "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None,
                out var valor) ||
            partes[3].Length == 0 ||
            !short.TryParse(partes[4], NumberStyles.None, CultureInfo.InvariantCulture, out var renglon))
        {
            throw Invalido();
        }

        return new PosicionDeRenglon(valor, partes[3], renglon);
    }

    private static string Fecha(DateOnly fecha) => fecha.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private static string Codificar(string consulta, params string[] valores)
    {
        string[] partes = [Version, consulta, .. valores];
        return Base64Url.EncodeToString(JsonSerializer.SerializeToUtf8Bytes(partes));
    }

    private static string[] Decodificar(string cursor, string consulta, int valores)
    {
        if (cursor.Length is 0 or > LargoMaximo || !Base64Url.IsValid(cursor))
        {
            throw Invalido();
        }

        string[]? partes;
        try
        {
            partes = JsonSerializer.Deserialize<string[]>(Base64Url.DecodeFromChars(cursor));
        }
        catch (JsonException)
        {
            throw Invalido();
        }

        if (partes is null || partes.Length != valores + 2 || partes[0] != Version || partes[1] != consulta ||
            partes.Any(p => p is null))
        {
            throw Invalido();
        }

        return partes[2..];
    }

    private static HotChocolate.GraphQLException Invalido() =>
        CodigosDeError.Argumento("after", "El cursor no es válido para esta consulta.");
}
