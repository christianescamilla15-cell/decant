using System.Globalization;
using System.Text;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Conciliacion;
using Decant.Domain.Divisas;

namespace Decant.Infrastructure.Archivos;

/// <summary>
/// El universo en archivos (lo deja <c>python -m paridad.extraer</c>): columnas de ENTRADA del respaldo por tabla,
/// el horario del job y los archivos de interfaz. Los encabezados se exigen exactos: aquí no puede entrar un resultado.
/// </summary>
public sealed class UniversoEnArchivos(string carpeta) : IUniverso
{
    public static readonly string[] ColumnasOperacion =
    [
        "id", "fecha_operacion", "sucursal", "canal", "cliente", "cuenta_clabe", "tipo", "moneda", "monto_divisa",
        "tipo_cambio_referencia", "estatus", "tipo_cambio",
    ];

    public static readonly string[] ColumnasOrden =
    [
        "id", "operacion_id", "uetr", "referencia_mt103", "fecha_registro", "fecha_envio", "fecha_valor",
        "bic_corresponsal", "bic_intermediario", "beneficiario", "cuenta_beneficiario", "moneda", "monto", "gastos",
        "codigo_proposito",
    ];

    public static readonly string[] ColumnasPartida = ["id", "monto", "fecha_hora", "referencia"];

    public static readonly string[] ColumnasMoneda = ["codigo", "numerico", "nombre", "decimales", "activa"];

    public IReadOnlyList<Moneda> Monedas() =>
        Jsonl.Leer(Ruta("moneda.jsonl"), ColumnasMoneda)
            .Select(f => new Moneda(CharLegado.SinRelleno(f.Requerido("codigo")),
                CharLegado.SinRelleno(f.Requerido("numerico")), f.Requerido("nombre"), f.Entero("decimales"),
                f.Requerido("activa") == "1"))
            .ToList();

    public IReadOnlyList<string> Series() =>
        Jsonl.Leer(Ruta("folio.jsonl"), ["serie"]).Select(f => CharLegado.SinRelleno(f.Requerido("serie"))).ToList();

    public IEnumerable<OperacionDeEntrada> Operaciones() =>
        Jsonl.Leer(Ruta("operacion.jsonl"), ColumnasOperacion).Select(f => new OperacionDeEntrada(
            f.Largo("id"), f.Hora("fecha_operacion"), f.Requerido("sucursal"), f.Requerido("canal"),
            f.Requerido("cliente"), f.Requerido("cuenta_clabe"), f.Requerido("tipo"), f.Requerido("moneda"),
            f.Decimal("monto_divisa"), f.Decimal("tipo_cambio_referencia"), f.Requerido("estatus"),
            f.DecimalONulo("tipo_cambio")));

    public IEnumerable<RegistroDeEntrada> RegistrosDeOrden() =>
        Jsonl.Leer(Ruta("orden_pago.jsonl"), ColumnasOrden).Select(f => new RegistroDeEntrada(
            f.Largo("id"), f.Largo("operacion_id"), f.Requerido("uetr"), f.Requerido("referencia_mt103"),
            f.Hora("fecha_registro"), f.Hora("fecha_envio"), f.Fecha("fecha_valor"), f.Requerido("bic_corresponsal"),
            f.Requerido("bic_intermediario"), f.Requerido("beneficiario"), f.Requerido("cuenta_beneficiario"),
            f.Requerido("moneda"), f.Decimal("monto"), f.Requerido("gastos"), f.Texto("codigo_proposito")));

    public IEnumerable<PartidaDeEntrada> PartidasDelCorresponsal() =>
        Jsonl.Leer(Ruta("partida_solicitada.jsonl"), ColumnasPartida).Select(f => new PartidaDeEntrada(
            f.Largo("id"), f.Decimal("monto"), f.Hora("fecha_hora"), f.Requerido("referencia")));

    /// <summary>UTF-8 ESTRICTO: un byte inválido es un archivo dañado, no un carácter de reemplazo silencioso.</summary>
    private static readonly UTF8Encoding Utf8Estricto = new(encoderShouldEmitUTF8Identifier: false,
        throwOnInvalidBytes: true);

    /// <summary>
    /// Los archivos del buzón del corresponsal en orden de nombre (fecha). Un archivo que no se puede leer (permisos,
    /// bytes inválidos) se devuelve con su falla y NO detiene a los demás.
    /// </summary>
    public IEnumerable<ArchivoDeInterfaz> ArchivosDelBuzon()
    {
        var buzon = RutaDentro.De(carpeta, "interfaces", "corresponsal");
        foreach (var archivo in Directory.GetFiles(buzon, "*.fin").OrderBy(a => a, StringComparer.Ordinal))
        {
            string? contenido = null;
            string? falla = null;
            try
            {
                contenido = File.ReadAllText(archivo, Utf8Estricto);
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException or DecoderFallbackException)
            {
                falla = e.GetType().Name;
            }

            yield return new ArchivoDeInterfaz(Path.GetFileName(archivo), contenido, falla);
        }
    }

    public IReadOnlyList<HorarioDelJob> Horario() =>
        Jsonl.Leer(Ruta("job.jsonl"), ["job", "frecuencia", "intervalo", "hora"])
            .Select(f => new HorarioDelJob(f.Requerido("job"), f.Entero("frecuencia"), f.Entero("intervalo"),
                TimeOnly.ParseExact(f.Requerido("hora"), "HH:mm", CultureInfo.InvariantCulture)))
            .ToList();

    private string Ruta(string archivo) => RutaDentro.De(carpeta, archivo);
}
