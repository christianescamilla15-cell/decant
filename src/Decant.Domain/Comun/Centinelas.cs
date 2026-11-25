namespace Decant.Domain.Comun;

/// <summary>
/// T3: el legado guarda centinelas en columnas NOT NULL donde el dato no existe: «NA» en la CLABE (operación en
/// efectivo) y en el BIC intermediario (sin intermediario), y 0 en el tipo de cambio de referencia (el cajero no la
/// capturó). El TO-BE guarda NULL: se cuenta CONTENIDO, no filas (ADR 0007).
/// </summary>
public static class Centinelas
{
    public const string SinDato = "NA";

    /// <summary>Texto del legado → null si es el centinela. El relleno de un char(n) no cuenta.</summary>
    public static string? Texto(string valor) => valor.TrimEnd(' ') == SinDato ? null : valor;

    public static decimal? Numero(decimal valor) => valor == 0m ? null : valor;
}

/// <summary>
/// Un <c>char(n)</c> del legado viene relleno con espacios por TIPO, no por dato. El TO-BE guarda el código sin ese
/// relleno. Los <c>varchar</c> no pasan por aquí: sus espacios finales sí son dato (ver la referencia del
/// corresponsal).
/// </summary>
public static class CharLegado
{
    public static string SinRelleno(string valor) => valor.TrimEnd(' ');

    public static string? SinRellenoONulo(string? valor) => valor?.TrimEnd(' ');
}
