using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Microsoft.EntityFrameworkCore;

namespace Decant.Infrastructure.Persistencia;

/// <summary>Consultas del TO-BE con EF Core (LINQ traducido a SQL: se prueban contra PostgreSQL real).</summary>
public sealed class ConsultasEf(DecantDbContext contexto) : IConsultasTobe
{
    public async Task<DetalleDeOperacion?> DetalleAsync(long operacionId, CancellationToken ct)
    {
        var operacion = await (
            from o in contexto.Operaciones.AsNoTracking()
            join m in contexto.Monedas.AsNoTracking() on o.Moneda equals m.Codigo into monedas
            from m in monedas.DefaultIfEmpty()
            where o.Id == operacionId
            select new OperacionVista(o.Id, o.Folio, o.FechaOperacion, o.Sucursal, o.Canal, o.Cliente, o.CuentaClabe,
                o.Tipo, o.Moneda, m == null ? null : m.Nombre, m == null ? null : (int?)m.Decimales, o.MontoDivisa,
                o.TipoCambio, o.TipoCambioReferencia, o.MontoMxn, o.Estatus)).FirstOrDefaultAsync(ct);
        if (operacion is null)
        {
            return null;
        }

        // El documento de la operación, elegido EXPLÍCITAMENTE (ronda 2 a ciegas, T2): el registro más reciente y,
        // si hubiera dos documentos, el folio mayor. En el TO-BE no hay filas REEMPLAZADA que esquivar.
        var orden = await contexto.Ordenes.AsNoTracking()
            .Where(o => o.OperacionId == operacionId)
            .OrderByDescending(o => o.FechaRegistro).ThenByDescending(o => o.Folio)
            .Select(o => new OrdenVista(o.Uetr, o.Folio, o.ReferenciaMt103, o.FechaRegistro, o.Registros, o.FechaEnvio,
                o.FechaValor, o.BicCorresponsal, o.BicIntermediario, o.Beneficiario, o.CuentaBeneficiario, o.Moneda,
                o.Monto, o.Gastos, o.CodigoProposito, o.Estatus, o.HorasLiquidacion))
            .FirstOrDefaultAsync(ct);
        if (orden is null)
        {
            return new DetalleDeOperacion(operacion, null, [], []);
        }

        var cliente = await contexto.PartidasCliente.AsNoTracking().Where(p => p.Uetr == orden.Uetr)
            .OrderBy(p => p.Renglon)
            .Select(p => new PartidaVista(p.Renglon, p.Concepto, p.Moneda, p.Monto, p.FechaHora, p.Referencia))
            .ToListAsync(ct);
        var corresponsal = await contexto.PartidasCorresponsal.AsNoTracking().Where(p => p.Uetr == orden.Uetr)
            .OrderBy(p => p.Renglon)
            .Select(p => new PartidaVista(p.Renglon, p.Concepto, p.Moneda, p.Monto, p.FechaHora, p.Referencia))
            .ToListAsync(ct);
        return new DetalleDeOperacion(operacion, orden, cliente, corresponsal);
    }

    /// <summary>
    /// Reporte de lo abonado por el corresponsal por fecha valor, un renglón por partida (T2: sólo órdenes CON
    /// partidas, como el legado: ADR 0006). Orden EXPLÍCITO: fecha valor (el contrato del legado), folio y renglón
    /// (el desempate que el legado dejaba al plan).
    /// </summary>
    public async Task<IReadOnlyList<RenglonDeReporte>> ReporteDeOrdenesAsync(DateOnly desde, DateOnly hasta,
        CancellationToken ct) =>
        await (
            from o in contexto.Ordenes.AsNoTracking()
            join p in contexto.PartidasCorresponsal.AsNoTracking() on o.Uetr equals p.Uetr
            where o.FechaValor >= desde && o.FechaValor <= hasta
            orderby o.FechaValor, o.Folio, p.Renglon
            select new RenglonDeReporte(o.Folio, o.Uetr, o.ReferenciaMt103, o.FechaEnvio, o.FechaValor,
                o.BicCorresponsal, o.Beneficiario, o.Moneda, o.Monto, o.Gastos, o.Estatus, p.Concepto, p.Monto,
                p.FechaHora)).ToListAsync(ct);

    /// <summary>T1: las operaciones de un día del calendario de la Ciudad de México, en orden EXPLÍCITO.</summary>
    public async Task<IReadOnlyList<OperacionDeLista>> ListaAsync(DateOnly fecha, int maximo, CancellationToken ct)
    {
        var desde = Zonas.AInstante(fecha.ToDateTime(TimeOnly.MinValue), Zonas.CiudadDeMexico);
        var hasta = Zonas.AInstante(fecha.AddDays(1).ToDateTime(TimeOnly.MinValue), Zonas.CiudadDeMexico);
        return await contexto.Operaciones.AsNoTracking()
            .Where(o => o.FechaOperacion >= desde && o.FechaOperacion < hasta)
            .OrderBy(o => o.FechaOperacion).ThenBy(o => o.Id)
            .Take(maximo)
            .Select(o => new OperacionDeLista(o.Id, o.Folio, o.FechaOperacion, o.Sucursal, o.Canal, o.Cliente, o.Tipo,
                o.Moneda, o.MontoDivisa, o.TipoCambio, o.MontoMxn, o.Estatus))
            .ToListAsync(ct);
    }
}
