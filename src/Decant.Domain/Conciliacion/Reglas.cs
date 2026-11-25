using Decant.Domain.Comun;
using Decant.Domain.Pagos;

namespace Decant.Domain.Conciliacion;

/// <summary>Lo que el proceso nocturno decidiría sobre un documento liquidado.</summary>
public sealed record DecisionDeConciliacion(EstatusOrden Veredicto, decimal Horas, decimal Abonado, decimal Principal);

/// <summary>Reglas del proceso nocturno (origen: <c>dbo.sp_conciliar</c>, el job de las 23:30).</summary>
public static class ReglasDeConciliacion
{
    /// <summary>
    /// R07 / D2. CONCILIADA si lo abonado (abono + comisión del corresponsal) es igual al principal; si no,
    /// DIFERENCIA. Se compara con los decimales que trae cada monto, como el legado: el yen con centavos que el
    /// corresponsal nunca abona sale en DIFERENCIA (D2, se replica mientras negocio no decida).
    /// </summary>
    public static EstatusOrden Veredicto(decimal abonado, decimal principal) =>
        abonado == principal ? EstatusOrden.Conciliada : EstatusOrden.Diferencia;

    /// <summary>
    /// R08 / T5. Se REPLICA la hora fija del legado mientras negocio no decida (ADR 0006): <c>DATEDIFF(minute,
    /// fecha_envio, DATEADD(hour, -1, ultima)) / 60.0</c> a dos decimales, con <c>fecha_envio</c> en la hora de pared
    /// de la Ciudad de México y <c>ultima</c> en la de Nueva York. El TO-BE GUARDA los instantes en UTC (ADR 0008) y
    /// de ellos recupera esas horas de pared: la réplica sólo afecta a esta regla. La corrección (con los instantes)
    /// se publica como hipótesis en el informe de paridad.
    /// </summary>
    public static decimal HorasDeLiquidacion(DateTimeOffset envio, DateTimeOffset ultimaPartida)
    {
        var envioLocal = Zonas.ALocal(envio, Zonas.CiudadDeMexico);
        var ultimaMenosUnaHora = Zonas.ALocal(ultimaPartida, Zonas.NuevaYork).AddHours(-1);
        var minutos = (ultimaMenosUnaHora.Ticks / TimeSpan.TicksPerMinute) - (envioLocal.Ticks / TimeSpan.TicksPerMinute);
        return Math.Round(minutos / 60m, 2, MidpointRounding.AwayFromZero);
    }
}

/// <summary>Regla de vencimiento del job (origen: <c>dbo.sp_conciliar</c>, T8).</summary>
public static class ReglasDeVencimiento
{
    public const int DiasDeEspera = 3;

    /// <summary>
    /// R10. Vence lo ENVIADO hace más de 3 días: <c>fecha_envio &lt; DATEADD(day, -3, GETDATE())</c>. Los días se
    /// cuentan en el CALENDARIO de la Ciudad de México (el legado compara horas locales), y «hoy» es el reloj que
    /// entra (la noche del job), nunca el del servidor.
    /// </summary>
    public static bool Vence(DateTimeOffset fechaEnvio, DateTimeOffset noche)
    {
        var envioLocal = Zonas.ALocal(fechaEnvio, Zonas.CiudadDeMexico);
        var nocheLocal = Zonas.ALocal(noche, Zonas.CiudadDeMexico);
        return envioLocal < nocheLocal.AddDays(-DiasDeEspera);
    }
}

/// <summary>
/// Evidencia del modo «sólo marca»: con la bandera de la acción APAGADA, el motor evalúa la regla y deja ✔ o ✘ por
/// caso, sin cambiar nada. Vencimiento: ✔ = la vencería esa noche; ✘ = nunca la vencería. Conciliación: ✔ = cuadra
/// (CONCILIADA); ✘ = DIFERENCIA. El detalle lleva los datos con que decidió.
/// </summary>
public sealed record Marca(string Regla, string Caso, DateTimeOffset Instante, bool Cumple, string Detalle);
