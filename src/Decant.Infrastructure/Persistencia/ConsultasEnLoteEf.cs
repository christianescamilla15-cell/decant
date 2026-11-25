using Decant.Application.Puertos;
using Microsoft.EntityFrameworkCore;

namespace Decant.Infrastructure.Persistencia;

/// <summary>
/// Páginas por llave de conjunto y lecturas en lote con EF Core. Cada llamada abre SU contexto desde la fábrica: el
/// DbContext no admite dos consultas a la vez y quien llama (los cargadores de GraphQL) sí las hace en paralelo.
/// </summary>
public sealed class ConsultasEnLoteEf(IDbContextFactory<DecantDbContext> fabrica) : IConsultasEnLote
{
    public async Task<Pagina<OperacionVista>> OperacionesDelDiaAsync(DateOnly fecha, PosicionDeOperacion? despuesDe,
        int cuantas, CancellationToken ct)
    {
        var (desde, hasta) = Proyecciones.DiaLocal(fecha);
        await using var contexto = await fabrica.CreateDbContextAsync(ct);
        var operaciones = contexto.Operaciones.AsNoTracking()
            .Where(o => o.FechaOperacion >= desde && o.FechaOperacion < hasta);
        if (despuesDe is not null)
        {
            // timestamptz sólo admite parámetros en UTC; el orden es el de T1 (fecha y luego id).
            var instante = despuesDe.FechaOperacion.ToUniversalTime();
            var id = despuesDe.Id;
            operaciones = operaciones.Where(o =>
                o.FechaOperacion > instante || (o.FechaOperacion == instante && o.Id > id));
        }

        var filas = await Proyecciones.OperacionesConMoneda(operaciones, contexto.Monedas.AsNoTracking())
            .Take(cuantas + 1).ToListAsync(ct);
        return Paginar(filas, cuantas);
    }

    public async Task<Pagina<RenglonConPosicion>> RenglonesDelReporteAsync(DateOnly desde, DateOnly hasta,
        PosicionDeRenglon? despuesDe, int cuantos, CancellationToken ct)
    {
        await using var contexto = await fabrica.CreateDbContextAsync(ct);
        var renglones =
            from o in contexto.Ordenes.AsNoTracking()
            join p in contexto.PartidasCorresponsal.AsNoTracking() on o.Uetr equals p.Uetr
            where o.FechaValor >= desde && o.FechaValor <= hasta
            select new { Orden = o, Partida = p };
        if (despuesDe is not null)
        {
            // La misma comparación que el ORDER BY (la colación de la base para el folio): nada se salta ni se repite.
            var (valor, folio, renglon) = (despuesDe.FechaValor, despuesDe.Folio, despuesDe.Renglon);
            renglones = renglones.Where(x => x.Orden.FechaValor > valor ||
                (x.Orden.FechaValor == valor && (string.Compare(x.Orden.Folio, folio) > 0 ||
                    (x.Orden.Folio == folio && x.Partida.Renglon > renglon))));
        }

        var filas = await renglones
            .OrderBy(x => x.Orden.FechaValor).ThenBy(x => x.Orden.Folio).ThenBy(x => x.Partida.Renglon)
            .Take(cuantos + 1)
            .Select(x => new RenglonConPosicion(
                new RenglonDeReporte(x.Orden.Folio, x.Orden.Uetr, x.Orden.ReferenciaMt103, x.Orden.FechaEnvio,
                    x.Orden.FechaValor, x.Orden.BicCorresponsal, x.Orden.Beneficiario, x.Orden.Moneda, x.Orden.Monto,
                    x.Orden.Gastos, x.Orden.Estatus, x.Partida.Concepto, x.Partida.Monto, x.Partida.FechaHora),
                new PosicionDeRenglon(x.Orden.FechaValor, x.Orden.Folio, x.Partida.Renglon)))
            .ToListAsync(ct);
        return Paginar(filas, cuantos);
    }

    public async Task<IReadOnlyDictionary<long, OperacionVista>> OperacionesAsync(IReadOnlyCollection<long> ids,
        CancellationToken ct)
    {
        var llaves = ids.Distinct().ToArray();
        await using var contexto = await fabrica.CreateDbContextAsync(ct);
        return await Proyecciones.OperacionesConMoneda(
                contexto.Operaciones.AsNoTracking().Where(o => llaves.Contains(o.Id)),
                contexto.Monedas.AsNoTracking())
            .ToDictionaryAsync(o => o.Id, ct);
    }

    public async Task<IReadOnlyDictionary<long, OrdenVista>> OrdenesDeOperacionesAsync(
        IReadOnlyCollection<long> operacionIds, CancellationToken ct)
    {
        var llaves = operacionIds.Distinct().ToArray();
        await using var contexto = await fabrica.CreateDbContextAsync(ct);
        // Todos los documentos de esas operaciones, del más reciente al más viejo (la regla del detalle); el primero
        // de cada operación es el suyo. Normalmente hay uno; si hubiera dos, gana el mismo que en el detalle.
        var documentos = await Proyecciones.DelMasReciente(contexto.Ordenes.AsNoTracking()
                .Where(o => llaves.Contains(o.OperacionId)))
            .ToListAsync(ct);
        return documentos.GroupBy(o => o.OperacionId)
            .ToDictionary(g => g.Key, g => Proyecciones.OrdenEnMemoria(g.First()));
    }

    public async Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> SolicitadoPorElClienteAsync(
        IReadOnlyCollection<Guid> uetrs, CancellationToken ct)
    {
        var llaves = uetrs.Distinct().ToArray();
        await using var contexto = await fabrica.CreateDbContextAsync(ct);
        var filas = await contexto.PartidasCliente.AsNoTracking().Where(p => llaves.Contains(p.Uetr))
            .OrderBy(p => p.Uetr).ThenBy(p => p.Renglon)
            .ToListAsync(ct);
        return Agrupar(filas.Select(p => (p.Uetr, Proyecciones.PartidaClienteEnMemoria(p))));
    }

    public async Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> LiquidadoPorElCorresponsalAsync(
        IReadOnlyCollection<Guid> uetrs, CancellationToken ct)
    {
        var llaves = uetrs.Distinct().ToArray();
        await using var contexto = await fabrica.CreateDbContextAsync(ct);
        var filas = await contexto.PartidasCorresponsal.AsNoTracking().Where(p => llaves.Contains(p.Uetr))
            .OrderBy(p => p.Uetr).ThenBy(p => p.Renglon)
            .ToListAsync(ct);
        return Agrupar(filas.Select(p => (p.Uetr, Proyecciones.PartidaCorresponsalEnMemoria(p))));
    }

    /// <summary>Se leyó uno de más: si llegó, hay otra página después de la última posición entregada.</summary>
    private static Pagina<T> Paginar<T>(List<T> filas, int cuantas) =>
        filas.Count > cuantas ? new Pagina<T>(filas.GetRange(0, cuantas), true) : new Pagina<T>(filas, false);

    private static Dictionary<Guid, IReadOnlyList<PartidaVista>> Agrupar(
        IEnumerable<(Guid Uetr, PartidaVista Partida)> filas) =>
        filas.GroupBy(f => f.Uetr)
            .ToDictionary(g => g.Key, g => (IReadOnlyList<PartidaVista>)g.Select(f => f.Partida).ToList());
}
