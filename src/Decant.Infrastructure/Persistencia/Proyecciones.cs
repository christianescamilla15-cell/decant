using System.Linq.Expressions;
using Decant.Application.Puertos;
using Decant.Domain.Comun;

namespace Decant.Infrastructure.Persistencia;

/// <summary>
/// Lo que comparten el detalle (una operación) y las lecturas en lote (N operaciones): las proyecciones a los modelos
/// de lectura, la regla que elige el documento de una operación y el día del calendario local. Una sola definición:
/// si cambia, cambia para la API REST y para la de GraphQL a la vez.
/// </summary>
internal static class Proyecciones
{
    /// <summary>Las operaciones con el nombre y los decimales de su moneda, en el orden de T1 (fecha y luego id).</summary>
    public static IQueryable<OperacionVista> OperacionesConMoneda(IQueryable<OperacionFila> operaciones,
        IQueryable<MonedaFila> monedas) =>
        from o in operaciones
        join m in monedas on o.Moneda equals m.Codigo into enMoneda
        from m in enMoneda.DefaultIfEmpty()
        orderby o.FechaOperacion, o.Id
        select new OperacionVista(o.Id, o.Folio, o.FechaOperacion, o.Sucursal, o.Canal, o.Cliente, o.CuentaClabe,
            o.Tipo, o.Moneda, m == null ? null : m.Nombre, m == null ? null : (int?)m.Decimales, o.MontoDivisa,
            o.TipoCambio, o.TipoCambioReferencia, o.MontoMxn, o.Estatus);

    public static readonly Expression<Func<OrdenFila, OrdenVista>> Orden = o => new OrdenVista(o.Uetr, o.Folio,
        o.ReferenciaMt103, o.FechaRegistro, o.Registros, o.FechaEnvio, o.FechaValor, o.BicCorresponsal,
        o.BicIntermediario, o.Beneficiario, o.CuentaBeneficiario, o.Moneda, o.Monto, o.Gastos, o.CodigoProposito,
        o.Estatus, o.HorasLiquidacion);

    public static readonly Expression<Func<PartidaClienteFila, PartidaVista>> PartidaCliente = p =>
        new PartidaVista(p.Renglon, p.Concepto, p.Moneda, p.Monto, p.FechaHora, p.Referencia);

    public static readonly Expression<Func<PartidaCorresponsalFila, PartidaVista>> PartidaCorresponsal = p =>
        new PartidaVista(p.Renglon, p.Concepto, p.Moneda, p.Monto, p.FechaHora, p.Referencia);

    /// <summary>Las mismas proyecciones, ya compiladas, para lo que se agrupa en memoria después de leer.</summary>
    public static readonly Func<OrdenFila, OrdenVista> OrdenEnMemoria = Orden.Compile();

    public static readonly Func<PartidaClienteFila, PartidaVista> PartidaClienteEnMemoria = PartidaCliente.Compile();

    public static readonly Func<PartidaCorresponsalFila, PartidaVista> PartidaCorresponsalEnMemoria =
        PartidaCorresponsal.Compile();

    /// <summary>
    /// El documento de una operación, elegido EXPLÍCITAMENTE (ronda 2 a ciegas, T2): el registro más reciente y, si
    /// hubiera dos documentos, el folio mayor. En el TO-BE no hay filas REEMPLAZADA que esquivar.
    /// </summary>
    public static IOrderedQueryable<OrdenFila> DelMasReciente(IQueryable<OrdenFila> ordenes) =>
        ordenes.OrderByDescending(o => o.FechaRegistro).ThenByDescending(o => o.Folio);

    /// <summary>T1: el día del calendario de la Ciudad de México como rango de instantes [desde, hasta).</summary>
    public static (DateTimeOffset Desde, DateTimeOffset Hasta) DiaLocal(DateOnly fecha) =>
        (Zonas.AInstante(fecha.ToDateTime(TimeOnly.MinValue), Zonas.CiudadDeMexico),
            Zonas.AInstante(fecha.AddDays(1).ToDateTime(TimeOnly.MinValue), Zonas.CiudadDeMexico));
}
