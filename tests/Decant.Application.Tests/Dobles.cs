using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Divisas;
using Decant.Domain.Reproceso;

namespace Decant.Application.Tests;

/// <summary>Dobles escritos a mano: guardan lo que reciben y devuelven lo que se les da.</summary>
internal sealed class UniversoEnMemoria : IUniverso
{
    public List<OperacionDeEntrada> ListaOperaciones { get; } = [];
    public List<RegistroDeEntrada> ListaRegistros { get; } = [];
    public List<PartidaDeEntrada> ListaPartidas { get; } = [];
    public List<string> Buzon { get; } = [];

    public IReadOnlyList<Moneda> Monedas() => [new("USD", "840", "Dólar estadounidense", 2, true)];
    public IReadOnlyList<string> Series() => ["FX", "OP"];
    public IEnumerable<OperacionDeEntrada> Operaciones() => ListaOperaciones;
    public IEnumerable<RegistroDeEntrada> RegistrosDeOrden() => ListaRegistros;
    public IEnumerable<PartidaDeEntrada> PartidasDelCorresponsal() => ListaPartidas;
    public IEnumerable<string> MensajesDelBuzon() => Buzon;
    public IReadOnlyList<HorarioDelJob> Horario() => [new("conciliacion nocturna", 4, 1, new TimeOnly(23, 30))];
}

internal sealed class AlmacenEnMemoria : IAlmacenTobe
{
    public EstadoTobe? Guardado { get; private set; }
    public Dictionary<Guid, EstadoDeDocumento> Estados { get; } = [];
    public Corrida? UltimaCorrida { get; private set; }

    public Task GuardarAsync(EstadoTobe estado, CancellationToken ct)
    {
        Guardado = estado;
        UltimaCorrida = estado.Corrida;
        return Task.CompletedTask;
    }

    public Task<IReadOnlyDictionary<Guid, EstadoDeDocumento>> EstadosAsync(CancellationToken ct) =>
        Task.FromResult<IReadOnlyDictionary<Guid, EstadoDeDocumento>>(new Dictionary<Guid, EstadoDeDocumento>(Estados));

    public Task ActualizarEstadosAsync(IReadOnlyDictionary<Guid, EstadoDeDocumento> estados, Corrida corrida,
        CancellationToken ct)
    {
        Estados.Clear();
        foreach (var (k, v) in estados)
        {
            Estados[k] = v;
        }

        UltimaCorrida = corrida;
        return Task.CompletedTask;
    }
}

internal sealed class OraculoEnMemoria : IOraculoHistorico
{
    public Dictionary<string, int> ListaConsecutivos { get; } = new() { ["FX"] = 3, ["OP"] = 2 };
    public List<OperacionDelOraculo> ListaOperaciones { get; } = [];
    public List<OrdenDelOraculo> ListaOrdenes { get; } = [];
    public List<PartidaCorresponsalDelOraculo> ListaCorresponsal { get; } = [];
    public List<PartidaClienteDelOraculo> ListaCliente { get; } = [];

    public IReadOnlyDictionary<string, int> Consecutivos() => ListaConsecutivos;
    public IEnumerable<OperacionDelOraculo> Operaciones() => ListaOperaciones;
    public IEnumerable<OrdenDelOraculo> Ordenes() => ListaOrdenes;
    public IEnumerable<PartidaCorresponsalDelOraculo> PartidasDelCorresponsal() => ListaCorresponsal;
    public IEnumerable<PartidaClienteDelOraculo> PartidasDelCliente() => ListaCliente;
}

/// <summary>El reloj del sistema de HOY: el replay no debe usarlo para sus reglas (T8).</summary>
internal sealed class RelojFijo(DateTimeOffset ahora) : IClock
{
    public DateTimeOffset AhoraUtc { get; } = ahora;
}

internal static class Universo
{
    public const string Uetr1 = "3edcbeae-c21e-40f1-b309-430eca67e133";
    public const string Uetr2 = "8a235e0d-82f7-4b1c-beff-439ed3620b32";

    public static OperacionDeEntrada Operacion(long id, DateTime fecha) =>
        new(id, fecha, "0999", "EN_LINEA", "Elena Flores Chávez", "987320396284801163", "V", "USD", 1000.00m,
            19.859734m, "CONCERTADA", null);

    /// <summary>Un alta o re-registro: el envío es el del DOCUMENTO (el re-registro lo repite tal cual, como en el
    /// respaldo real: la verificación de la migración lo comprueba fila por fila).</summary>
    public static RegistroDeEntrada Registro(long id, long operacion, string uetr, string referencia, DateTime registro,
        DateTime? envio = null) =>
        new(id, operacion, uetr, referencia, registro, envio ?? registro.AddSeconds(30), DateOnly.FromDateTime(registro),
            "FICTUS33XXX", "NA         ", "Great Plains Seed Co.", "123456789012345678", "USD", 1000.00m, "SHA",
            "SUPP");

    /// <summary>Confirmación con el formato real del buzón (hora de Nueva York al minuto, con su desfase).</summary>
    public static string Confirmacion(string uetr, string referencia, string trn, DateTime horaNy, string desfase,
        string abono, string? comision = null) =>
        $"{{3:{{121:{uetr}}}}}{{4:\n:20:{trn}\n:21:{referencia}\n:13D:{horaNy:yyMMddHHmm}{desfase}\n" +
        $":32A:{horaNy:yyMMdd}USD{abono}\n" + (comision is null ? string.Empty : $":71F:USD{comision}\n") + "-}";
}
