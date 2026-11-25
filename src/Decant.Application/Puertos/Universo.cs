using Decant.Domain.Divisas;

namespace Decant.Application.Puertos;

/// <summary>Una operación como la trae el universo: columnas de ENTRADA, con los centinelas y la hora local del
/// legado tal cual (el caso de uso aplica los parches documentados).</summary>
public sealed record OperacionDeEntrada(
    long Id,
    DateTime FechaOperacionLocal,
    string Sucursal,
    string Canal,
    string Cliente,
    string CuentaClabe,
    string Tipo,
    string Moneda,
    decimal MontoDivisa,
    decimal TipoCambioReferencia,
    string Estatus,
    decimal? TipoCambioTecleado);

/// <summary>Un alta (o re-registro) de orden como la trae el universo.</summary>
public sealed record RegistroDeEntrada(
    long Id,
    long OperacionId,
    string Uetr,
    string ReferenciaMt103,
    DateTime FechaRegistroLocal,
    DateTime FechaEnvioLocal,
    DateOnly FechaValor,
    string BicCorresponsal,
    string BicIntermediario,
    string Beneficiario,
    string CuentaBeneficiario,
    string Moneda,
    decimal Monto,
    string Gastos,
    string? CodigoProposito);

/// <summary>Columnas de entrada de <c>partida_solicitada</c> (lo que mandó el corresponsal, hora de Nueva York).</summary>
public sealed record PartidaDeEntrada(long Id, decimal Monto, DateTime FechaHoraLocal, string Referencia);

public sealed record HorarioDelJob(string Nombre, int Frecuencia, int Intervalo, TimeOnly Hora);

/// <summary>Un archivo de interfaz tal como se pudo leer: su contenido o la falla de lectura (un archivo dañado no
/// detiene a los demás).</summary>
public sealed record ArchivoDeInterfaz(string Nombre, string? Contenido, string? FallaDeLectura);

/// <summary>
/// El UNIVERSO: lo único que alimenta el replay. Columnas de entrada del respaldo, archivos de interfaz y horario del
/// job. No hay manera de pedirle un resultado del legado.
/// </summary>
public interface IUniverso
{
    IReadOnlyList<Moneda> Monedas();

    IReadOnlyList<string> Series();

    IEnumerable<OperacionDeEntrada> Operaciones();

    IEnumerable<RegistroDeEntrada> RegistrosDeOrden();

    IEnumerable<PartidaDeEntrada> PartidasDelCorresponsal();

    /// <summary>Los archivos del buzón del corresponsal, en orden de nombre (fecha).</summary>
    IEnumerable<ArchivoDeInterfaz> ArchivosDelBuzon();

    IReadOnlyList<HorarioDelJob> Horario();
}
