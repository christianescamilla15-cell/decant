using System.Globalization;
using System.Text.RegularExpressions;
using Decant.Domain.Comun;

namespace Decant.Domain.Conciliacion;

/// <summary>
/// Confirmación de abono del corresponsal (estilo MT910 simplificado). Sus llaves REALES: la UETR del bloque 3
/// (<c>{121:…}</c>) y nuestra referencia en <c>:21:</c>. El <c>:20:</c> es la referencia PROPIA del corresponsal:
/// el primer campo «parecido», que no cruza con ningún documento nuestro.
/// </summary>
public sealed record ConfirmacionDelCorresponsal(
    Guid Uetr,
    string ReferenciaMt103,
    string TrnCorresponsal,
    DateTime HoraLocal,
    TimeSpan Desfase,
    DateOnly FechaValor,
    string Moneda,
    decimal Abono,
    decimal Comision)
{
    /// <summary>El instante exacto: <c>:13D:</c> trae la hora de Nueva York CON su desfase (el legado lo tiró).</summary>
    public DateTimeOffset Instante => new DateTimeOffset(HoraLocal, Desfase).ToUniversalTime();

    /// <summary>
    /// <c>:13D:</c> llega al minuto; el legado guardó los segundos (columna de entrada de
    /// <c>partida_solicitada.fecha_hora</c>). Sólo se aceptan si caen en el mismo minuto del mensaje.
    /// </summary>
    public Resultado<ConfirmacionDelCorresponsal> ConSegundos(DateTime horaLocalExacta)
    {
        var minuto = new DateTime(horaLocalExacta.Year, horaLocalExacta.Month, horaLocalExacta.Day,
            horaLocalExacta.Hour, horaLocalExacta.Minute, 0, DateTimeKind.Unspecified);
        if (minuto != HoraLocal)
        {
            return new Error("hora_fuera_del_minuto",
                $"{Uetr}: la hora guardada {horaLocalExacta:s} no es la del :13D: {HoraLocal:s}");
        }

        return this with { HoraLocal = DateTime.SpecifyKind(horaLocalExacta, DateTimeKind.Unspecified) };
    }
}

/// <summary>Lectura del buzón del corresponsal en su formato real.</summary>
public static class Mt910
{
    // Expresiones compiladas en campos (no [GeneratedRegex]): Stryker.NET no corre generadores de código al mutar.
    private static readonly Regex Uetr = new(
        @"\{121:([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\}", RegexOptions.Compiled);

    private static readonly Regex Campos = new(@"^:(\d{2}[A-Z]?):(.*)$", RegexOptions.Multiline | RegexOptions.Compiled);

    private static readonly Regex Swift = new(@"^([A-Z]{3})(\d+,\d*)$", RegexOptions.Compiled);

    /// <summary>Un archivo del buzón trae varios mensajes separados por <c>$</c> al inicio de renglón (RJE).</summary>
    public static IEnumerable<string> Separar(string buzon) =>
        buzon.Split("\n$").Where(m => !string.IsNullOrWhiteSpace(m));

    public static Resultado<ConfirmacionDelCorresponsal> Leer(string mensaje)
    {
        var uetr = Uetr.Match(mensaje);
        if (!uetr.Success)
        {
            return new Error("sin_uetr", "mensaje sin UETR en el bloque 3");
        }

        var campos = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (Match m in Campos.Matches(mensaje))
        {
            campos[m.Groups[1].Value] = m.Groups[2].Value.Trim();
        }

        foreach (var requerido in new[] { "20", "21", "13D", "32A" })
        {
            if (!campos.ContainsKey(requerido))
            {
                return new Error("campo_faltante", $"{uetr.Groups[1].Value}: falta :{requerido}:");
            }
        }

        var momento = campos["13D"];
        if (momento.Length != 15 || (momento[10] != '+' && momento[10] != '-'))
        {
            return new Error("13D_invalido", $"«{momento}» no es AAMMDDHHMM±HHMM");
        }

        var horaLocal = DateTime.ParseExact(momento[..10], "yyMMddHHmm", CultureInfo.InvariantCulture);
        var desfase = new TimeSpan(int.Parse(momento[11..13], CultureInfo.InvariantCulture),
            int.Parse(momento[13..15], CultureInfo.InvariantCulture), 0);
        if (momento[10] == '-')
        {
            desfase = desfase.Negate();
        }

        var valor = campos["32A"];
        var abono = Monto(valor[6..]);
        if (!abono.EsExito)
        {
            return abono.Error!;
        }

        var comision = campos.TryGetValue("71F", out var gastos)
            ? Monto(gastos)
            : Resultado<(string Moneda, decimal Monto)>.Exito((string.Empty, 0m));
        if (!comision.EsExito)
        {
            return comision.Error!;
        }

        return new ConfirmacionDelCorresponsal(
            Guid.Parse(uetr.Groups[1].Value),
            campos["21"],
            campos["20"],
            DateTime.SpecifyKind(horaLocal, DateTimeKind.Unspecified),
            desfase,
            DateOnly.ParseExact(valor[..6], "yyMMdd", CultureInfo.InvariantCulture),
            abono.Valor.Moneda,
            abono.Valor.Monto,
            comision.Valor.Monto);
    }

    private static Resultado<(string Moneda, decimal Monto)> Monto(string texto)
    {
        var m = Swift.Match(texto.Trim());
        if (!m.Success)
        {
            return new Error("monto_swift_invalido", $"monto SWIFT inválido: «{texto}»");
        }

        var numero = m.Groups[2].Value.Replace(',', '.').TrimEnd('.');
        return (m.Groups[1].Value,
            numero.Length == 0 ? 0m : decimal.Parse(numero, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture));
    }
}
