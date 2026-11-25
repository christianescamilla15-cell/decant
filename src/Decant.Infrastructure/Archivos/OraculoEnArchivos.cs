using Decant.Application.Puertos;

namespace Decant.Infrastructure.Archivos;

/// <summary>Los RESULTADOS del legado en archivos (carpeta <c>oraculo/</c>). Sólo los usa la carga histórica.</summary>
public sealed class OraculoEnArchivos(string carpeta) : IOraculoHistorico
{
    public IReadOnlyDictionary<string, int> Consecutivos() =>
        Jsonl.Leer(Ruta("folio.jsonl"), ["serie", "siguiente", "actualizado"])
            .ToDictionary(f => f.Requerido("serie").TrimEnd(' '), f => f.Entero("siguiente"), StringComparer.Ordinal);

    public IEnumerable<OperacionDelOraculo> Operaciones() =>
        Jsonl.Leer(Ruta("operacion.jsonl"), ["id", "folio", "monto_mxn", "tipo_cambio"])
            .Select(f => new OperacionDelOraculo(f.Largo("id"), f.Requerido("folio"), f.Decimal("monto_mxn"),
                f.DecimalONulo("tipo_cambio")));

    public IEnumerable<OrdenDelOraculo> Ordenes() =>
        Jsonl.Leer(Ruta("orden_pago.jsonl"), ["id", "folio", "estatus", "horas_liquidacion"])
            .Select(f => new OrdenDelOraculo(f.Largo("id"), f.Requerido("folio"), f.Requerido("estatus"),
                f.DecimalONulo("horas_liquidacion")));

    public IEnumerable<PartidaCorresponsalDelOraculo> PartidasDelCorresponsal() =>
        Jsonl.Leer(Ruta("partida_solicitada.jsonl"), ["id", "orden_id", "renglon", "concepto", "moneda"])
            .Select(f => new PartidaCorresponsalDelOraculo(f.Largo("id"), f.Largo("orden_id"),
                (short)f.Entero("renglon"), f.Requerido("concepto"), f.Requerido("moneda")));

    public IEnumerable<PartidaClienteDelOraculo> PartidasDelCliente() =>
        Jsonl.Leer(Ruta("partida_liquidada.jsonl"),
                ["id", "orden_id", "renglon", "concepto", "moneda", "monto", "fecha_hora", "referencia"])
            .Select(f => new PartidaClienteDelOraculo(f.Largo("id"), f.Largo("orden_id"), (short)f.Entero("renglon"),
                f.Requerido("concepto"), f.Requerido("moneda"), f.Decimal("monto"), f.Hora("fecha_hora"),
                f.Requerido("referencia")));

    private string Ruta(string archivo) => RutaDentro.De(carpeta, archivo);
}
