using Decant.Application.Abstracciones;
using Decant.Application.Consultas;
using Decant.Domain.Comun;
using GreenDonut;

namespace Decant.Api.GraphQL;

// Cargadores por lote (DataLoader) contra el N+1: GraphQL resuelve cada campo por separado; sin ellos, una página de
// N operaciones con su orden y sus partidas haría 1 + N + 2N consultas. Cada cargador junta las llaves que se piden en
// la misma «ola» de la ejecución y hace UNA consulta por lote, a través del mediador (los mismos casos de uso).

public sealed class OperacionesPorId(IMediador mediador, IBatchScheduler planificador, DataLoaderOptions opciones)
    : BatchDataLoader<long, Operacion>(planificador, opciones)
{
    protected override async Task<IReadOnlyDictionary<long, Operacion>> LoadBatchAsync(IReadOnlyList<long> llaves,
        CancellationToken cancellationToken)
    {
        var vistas = await mediador.EnviarAsync(new ConsultarOperaciones(llaves), cancellationToken);
        return vistas.ToDictionary(v => v.Key, v => Operacion.De(v.Value));
    }
}

public sealed class OrdenesPorOperacion(IMediador mediador, IBatchScheduler planificador, DataLoaderOptions opciones)
    : BatchDataLoader<long, Orden>(planificador, opciones)
{
    protected override async Task<IReadOnlyDictionary<long, Orden>> LoadBatchAsync(IReadOnlyList<long> llaves,
        CancellationToken cancellationToken)
    {
        var vistas = await mediador.EnviarAsync(new ConsultarOrdenesDeOperaciones(llaves), cancellationToken);
        return vistas.ToDictionary(v => v.Key, v => Orden.De(v.Key, v.Value));
    }
}

public sealed class SolicitadoPorElCliente(IMediador mediador, IBatchScheduler planificador,
    DataLoaderOptions opciones) : BatchDataLoader<Guid, IReadOnlyList<Partida>>(planificador, opciones)
{
    protected override Task<IReadOnlyDictionary<Guid, IReadOnlyList<Partida>>> LoadBatchAsync(
        IReadOnlyList<Guid> llaves, CancellationToken cancellationToken) =>
        Partidas.CargarAsync(mediador, llaves, LadoDePartida.SolicitadoPorElCliente, Zonas.CiudadDeMexico,
            cancellationToken);
}

public sealed class LiquidadoPorElCorresponsal(IMediador mediador, IBatchScheduler planificador,
    DataLoaderOptions opciones) : BatchDataLoader<Guid, IReadOnlyList<Partida>>(planificador, opciones)
{
    protected override Task<IReadOnlyDictionary<Guid, IReadOnlyList<Partida>>> LoadBatchAsync(
        IReadOnlyList<Guid> llaves, CancellationToken cancellationToken) =>
        Partidas.CargarAsync(mediador, llaves, LadoDePartida.LiquidadoPorElCorresponsal, Zonas.NuevaYork,
            cancellationToken);
}

internal static class Partidas
{
    public static async Task<IReadOnlyDictionary<Guid, IReadOnlyList<Partida>>> CargarAsync(IMediador mediador,
        IReadOnlyList<Guid> uetrs, LadoDePartida lado, TimeZoneInfo zona, CancellationToken ct)
    {
        var vistas = await mediador.EnviarAsync(new ConsultarPartidas(uetrs, lado), ct);
        return vistas.ToDictionary(v => v.Key,
            v => (IReadOnlyList<Partida>)v.Value.Select(p => Partida.De(p, zona)).ToList());
    }
}
