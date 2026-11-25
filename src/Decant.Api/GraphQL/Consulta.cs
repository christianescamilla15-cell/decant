using Decant.Application.Abstracciones;
using Decant.Application.Consultas;
using Decant.Application.Puertos;
using HotChocolate;
using HotChocolate.Types;
using HotChocolate.Types.Pagination;

namespace Decant.Api.GraphQL;

/// <summary>
/// La raíz de lectura. SIN mutaciones: la carga y el replay siguen siendo lotes (ADR 0017). Los filtros son los
/// argumentos EXPLÍCITOS de REST (un día, un rango de fechas valor, un id); no hay filtrado ni orden arbitrario que
/// llegue a la base, y las listas largas son páginas por cursor.
/// </summary>
[GraphQLName("Query")]
public sealed class Consulta
{
    public const int PaginaPorOmision = 20;

    [GraphQLDescription("Una operación por su id, o nula si no existe. Equivale a GET /api/operaciones/{id}.")]
    public Task<Operacion?> GetOperacionAsync(long id, OperacionesPorId cargador, CancellationToken ct) =>
        cargador.LoadAsync(id, ct);

    [GraphQLDescription(
        "Las operaciones de un día del calendario de la Ciudad de México en orden explícito (fecha y id, T1), por " +
        "páginas. Equivale a GET /api/operaciones?fecha=.")]
    [UsePaging(MaxPageSize = Paginas.Maximo, DefaultPageSize = PaginaPorOmision, IncludeTotalCount = false,
        AllowBackwardPagination = false)]
    public async Task<Connection<Operacion>> GetOperacionesAsync(DateOnly fecha, int? first, string? after,
        IMediador mediador, CancellationToken ct)
    {
        var despuesDe = after is null ? null : Cursores.LeerOperacion(after, fecha);
        var pagina = await mediador.EnviarAsync(
            new ConsultarPaginaDeOperaciones(fecha, despuesDe, Cuantos(first)), ct);
        var aristas = pagina.Elementos
            .Select(o => new Edge<Operacion>(Operacion.De(o),
                Cursores.DeOperacion(fecha, new PosicionDeOperacion(o.FechaOperacion, o.Id))))
            .ToList();
        return Conexion(aristas, pagina.HayMas, despuesDe is not null);
    }

    [GraphQLDescription(
        "Lo abonado por el corresponsal entre dos fechas valor (inclusivas), un renglón por partida, en orden " +
        "explícito (fecha valor, folio y renglón, T2), por páginas. Equivale a GET /api/reportes/ordenes.")]
    [UsePaging(MaxPageSize = Paginas.Maximo, DefaultPageSize = PaginaPorOmision, IncludeTotalCount = false,
        AllowBackwardPagination = false)]
    public async Task<Connection<RenglonDeReporte>> GetReporteDeOrdenesAsync(DateOnly desde, DateOnly hasta,
        int? first, string? after, IMediador mediador, CancellationToken ct)
    {
        if (hasta < desde)
        {
            throw CodigosDeError.Argumento("hasta", "«hasta» es anterior a «desde».");
        }

        var despuesDe = after is null ? null : Cursores.LeerRenglon(after, desde, hasta);
        var pagina = await mediador.EnviarAsync(
            new ConsultarPaginaDelReporte(desde, hasta, despuesDe, Cuantos(first)), ct);
        var aristas = pagina.Elementos
            .Select(r => new Edge<RenglonDeReporte>(RenglonDeReporte.De(r.Renglon),
                Cursores.DeRenglon(desde, hasta, r.Posicion)))
            .ToList();
        return Conexion(aristas, pagina.HayMas, despuesDe is not null);
    }

    /// <summary>El tamaño pedido; fuera de 1..100 es un argumento inválido (también si el límite de la paginación no
    /// lo atrapó antes).</summary>
    private static int Cuantos(int? first) => first switch
    {
        null => PaginaPorOmision,
        < 1 or > Paginas.Maximo => throw CodigosDeError.Argumento("first",
            $"«first» va de 1 a {Paginas.Maximo}."),
        _ => first.Value,
    };

    private static Connection<T> Conexion<T>(List<Edge<T>> aristas, bool hayMas, bool hayAntes) =>
        new(aristas, new ConnectionPageInfo(hayMas, hayAntes, aristas.FirstOrDefault()?.Cursor,
            aristas.LastOrDefault()?.Cursor), 0);
}
