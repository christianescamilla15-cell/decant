namespace Decant.Domain.Comun;

/// <summary>
/// El legado guarda hora LOCAL sin zona: la de la Ciudad de México en sus fechas y la de Nueva York en lo que manda
/// el corresponsal (T5). El TO-BE guarda instantes (UTC) y convierte en la frontera con estas dos reglas.
/// </summary>
public static class Zonas
{
    public static TimeZoneInfo CiudadDeMexico { get; } = TimeZoneInfo.FindSystemTimeZoneById("America/Mexico_City");

    public static TimeZoneInfo NuevaYork { get; } = TimeZoneInfo.FindSystemTimeZoneById("America/New_York");

    /// <summary>
    /// Hora local del legado → instante. En la hora que se repite al terminar el horario de verano toma la PRIMERA
    /// ocurrencia (la de verano): el legado no guardó cuál fue y el universo tampoco lo dice. En la hora que no
    /// existe (el salto de primavera) usa el desfase de antes del cambio.
    /// </summary>
    public static DateTimeOffset AInstante(DateTime horaLocal, TimeZoneInfo zona)
    {
        var local = DateTime.SpecifyKind(horaLocal, DateTimeKind.Unspecified);
        TimeSpan desfase;
        if (zona.IsAmbiguousTime(local))
        {
            desfase = zona.GetAmbiguousTimeOffsets(local).Max();
        }
        else if (zona.IsInvalidTime(local))
        {
            desfase = zona.GetUtcOffset(local.AddHours(-1));
        }
        else
        {
            desfase = zona.GetUtcOffset(local);
        }

        return new DateTimeOffset(local, desfase).ToUniversalTime();
    }

    /// <summary>
    /// Igual que <see cref="AInstante"/>, pero en la hora repetida decide con el ORDEN DE LLEGADA: si la primera
    /// ocurrencia quedaría antes de <paramref name="noAntesDe"/> (el evento anterior, por identidad), fue la segunda.
    /// Las altas de órdenes llegan en el orden de su identidad; el legado guardó la hora sin zona y el folio OP se
    /// consumió en ese orden (encontrado por la paridad: 5 folios del 31-oct-2021). El envío se ancla al PRIMER
    /// registro de su documento (encontrado contra la verdad del generador: 2 envíos del 30-oct-2022 que un
    /// re-registro posterior empujaba a la segunda vuelta).
    /// </summary>
    public static DateTimeOffset AInstanteNoAntesDe(DateTime horaLocal, TimeZoneInfo zona, DateTimeOffset? noAntesDe)
    {
        var local = DateTime.SpecifyKind(horaLocal, DateTimeKind.Unspecified);
        if (!zona.IsAmbiguousTime(local) || noAntesDe is null)
        {
            return AInstante(local, zona);
        }

        var desfases = zona.GetAmbiguousTimeOffsets(local).OrderByDescending(d => d).ToArray();
        var primera = new DateTimeOffset(local, desfases[0]).ToUniversalTime();
        return primera >= noAntesDe.Value ? primera : new DateTimeOffset(local, desfases[^1]).ToUniversalTime();
    }

    /// <summary>¿La hora local se repite ese día? Entonces el instante no se puede saber (T5).</summary>
    public static bool EsAmbigua(DateTime horaLocal, TimeZoneInfo zona) =>
        zona.IsAmbiguousTime(DateTime.SpecifyKind(horaLocal, DateTimeKind.Unspecified));

    /// <summary>Instante → hora local sin zona, como la guarda el legado.</summary>
    public static DateTime ALocal(DateTimeOffset instante, TimeZoneInfo zona) =>
        TimeZoneInfo.ConvertTime(instante, zona).DateTime;

    /// <summary>Instante con el desfase de la zona (para publicar sin ambigüedad).</summary>
    public static DateTimeOffset EnZona(DateTimeOffset instante, TimeZoneInfo zona) =>
        TimeZoneInfo.ConvertTime(instante, zona);
}
