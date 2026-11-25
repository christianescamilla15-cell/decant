using Decant.Application.Consultas;
using Decant.Application.Puertos;

namespace Decant.Application.Tests;

/// <summary>
/// Los casos de uso de lectura por páginas y por lotes (los que usa GraphQL): validan ANTES de llegar al puerto, con
/// las mismas reglas que la API REST (rango de fechas al derecho; página acotada), y piden el lado que se nombra.
/// </summary>
public class ConsultasEnLoteTests
{
    /// <summary>Doble a mano: registra cada llamada y devuelve vacío.</summary>
    private sealed class ConsultasEnLoteEnMemoria : IConsultasEnLote
    {
        public List<string> Llamadas { get; } = [];

        public Task<Pagina<OperacionVista>> OperacionesDelDiaAsync(DateOnly fecha, PosicionDeOperacion? despuesDe,
            int cuantas, CancellationToken ct)
        {
            Llamadas.Add($"operaciones {fecha:yyyy-MM-dd} {cuantas} {despuesDe?.Id}");
            return Task.FromResult(new Pagina<OperacionVista>([], false));
        }

        public Task<Pagina<RenglonConPosicion>> RenglonesDelReporteAsync(DateOnly desde, DateOnly hasta,
            PosicionDeRenglon? despuesDe, int cuantos, CancellationToken ct)
        {
            Llamadas.Add($"reporte {desde:yyyy-MM-dd} {hasta:yyyy-MM-dd} {cuantos} {despuesDe?.Folio}");
            return Task.FromResult(new Pagina<RenglonConPosicion>([], false));
        }

        public Task<IReadOnlyDictionary<long, OperacionVista>> OperacionesAsync(IReadOnlyCollection<long> ids,
            CancellationToken ct)
        {
            Llamadas.Add($"operaciones por id {string.Join(',', ids)}");
            return Task.FromResult<IReadOnlyDictionary<long, OperacionVista>>(new Dictionary<long, OperacionVista>());
        }

        public Task<IReadOnlyDictionary<long, OrdenVista>> OrdenesDeOperacionesAsync(
            IReadOnlyCollection<long> operacionIds, CancellationToken ct)
        {
            Llamadas.Add($"órdenes {string.Join(',', operacionIds)}");
            return Task.FromResult<IReadOnlyDictionary<long, OrdenVista>>(new Dictionary<long, OrdenVista>());
        }

        public Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> SolicitadoPorElClienteAsync(
            IReadOnlyCollection<Guid> uetrs, CancellationToken ct)
        {
            Llamadas.Add("cliente");
            return Task.FromResult<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>>(
                new Dictionary<Guid, IReadOnlyList<PartidaVista>>());
        }

        public Task<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>> LiquidadoPorElCorresponsalAsync(
            IReadOnlyCollection<Guid> uetrs, CancellationToken ct)
        {
            Llamadas.Add("corresponsal");
            return Task.FromResult<IReadOnlyDictionary<Guid, IReadOnlyList<PartidaVista>>>(
                new Dictionary<Guid, IReadOnlyList<PartidaVista>>());
        }
    }

    private static readonly DateOnly Dia = new(2023, 12, 1);

    /// <summary>Los bordes de la página: 1 y 100 llegan al puerto; 0, negativos y 101 no (la base no se toca).</summary>
    [Theory]
    [InlineData(1, true)]
    [InlineData(Paginas.Maximo, true)]
    [InlineData(0, false)]
    [InlineData(-1, false)]
    [InlineData(Paginas.Maximo + 1, false)]
    public async Task La_pagina_va_de_1_a_100_en_las_dos_listas(int cuantas, bool valida)
    {
        var puerto = new ConsultasEnLoteEnMemoria();
        Task Operaciones() => new ConsultarPaginaDeOperacionesManejador(puerto)
            .ManejarAsync(new ConsultarPaginaDeOperaciones(Dia, null, cuantas), default);
        Task Reporte() => new ConsultarPaginaDelReporteManejador(puerto)
            .ManejarAsync(new ConsultarPaginaDelReporte(Dia, Dia, null, cuantas), default);
        if (valida)
        {
            await Operaciones();
            await Reporte();
            Assert.Equal([$"operaciones 2023-12-01 {cuantas} ", $"reporte 2023-12-01 2023-12-01 {cuantas} "],
                puerto.Llamadas);
        }
        else
        {
            await Assert.ThrowsAsync<ArgumentOutOfRangeException>(Operaciones);
            await Assert.ThrowsAsync<ArgumentOutOfRangeException>(Reporte);
            Assert.Empty(puerto.Llamadas);
        }
    }

    /// <summary>El mismo rango que rechaza REST con 400: «hasta» antes de «desde» no llega al puerto.</summary>
    [Fact]
    public async Task El_reporte_por_paginas_rechaza_un_rango_al_reves()
    {
        var puerto = new ConsultasEnLoteEnMemoria();
        await Assert.ThrowsAsync<ArgumentException>(() => new ConsultarPaginaDelReporteManejador(puerto)
            .ManejarAsync(new ConsultarPaginaDelReporte(Dia, Dia.AddDays(-1), null, 10), default));
        Assert.Empty(puerto.Llamadas);
    }

    /// <summary>T4 también por lotes: cada lista se pide por lo que ES, no por el nombre de la tabla del legado.</summary>
    [Theory]
    [InlineData(LadoDePartida.SolicitadoPorElCliente, "cliente")]
    [InlineData(LadoDePartida.LiquidadoPorElCorresponsal, "corresponsal")]
    public async Task Las_partidas_se_piden_del_lado_que_se_nombra(LadoDePartida lado, string llamada)
    {
        var puerto = new ConsultasEnLoteEnMemoria();
        await new ConsultarPartidasManejador(puerto).ManejarAsync(new ConsultarPartidas([Guid.Empty], lado), default);
        Assert.Equal([llamada], puerto.Llamadas);
        await Assert.ThrowsAsync<ArgumentOutOfRangeException>(() => new ConsultarPartidasManejador(puerto)
            .ManejarAsync(new ConsultarPartidas([Guid.Empty], (LadoDePartida)99), default));
    }
}
