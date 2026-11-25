using Decant.Application.Puertos;
using Decant.Domain.Pagos;
using Decant.Infrastructure.Persistencia;
using Microsoft.EntityFrameworkCore;

namespace Decant.Infrastructure.Tests;

/// <summary>
/// Las lecturas por páginas (llave de conjunto) y por lotes contra PostgreSQL real: recorrer un día o un reporte de
/// a un elemento da EXACTAMENTE lo mismo que leerlo de una vez (sin saltos ni repetidos, también en los días de 23 y
/// 25 horas y en empates de instante), y el lote elige el mismo documento que el detalle.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class ConsultasEnLoteTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    public async Task InitializeAsync() => await Cargar(Escenario.Estado());

    public Task DisposeAsync() => Task.CompletedTask;

    private async Task Cargar(EstadoTobe estado)
    {
        await using var contexto = baseDePrueba.Contexto();
        await new AlmacenPostgres(contexto).GuardarAsync(estado, default);
    }

    private sealed class Fabrica(BaseDePrueba baseDePrueba) : IDbContextFactory<DecantDbContext>
    {
        public DecantDbContext CreateDbContext() => baseDePrueba.Contexto();
    }

    private ConsultasEnLoteEf Lotes() => new(new Fabrica(baseDePrueba));

    private async Task<List<long>> DiaPorPaginas(DateOnly fecha, int tamano)
    {
        var ids = new List<long>();
        PosicionDeOperacion? despuesDe = null;
        while (true)
        {
            var pagina = await Lotes().OperacionesDelDiaAsync(fecha, despuesDe, tamano, default);
            ids.AddRange(pagina.Elementos.Select(o => o.Id));
            if (!pagina.HayMas)
            {
                return ids;
            }

            var ultima = pagina.Elementos[^1];
            despuesDe = new PosicionDeOperacion(ultima.FechaOperacion, ultima.Id);
        }
    }

    private async Task<IReadOnlyList<long>> DiaDeUnaVez(DateOnly fecha)
    {
        await using var contexto = baseDePrueba.Contexto();
        return [.. (await new ConsultasEf(contexto).ListaAsync(fecha, 1000, default)).Select(o => o.Id)];
    }

    /// <summary>T1: el 1-dic tiene dos operaciones en el MISMO instante (desempata el id) y una a las 23:30 local.</summary>
    [Fact]
    public async Task Recorrer_el_dia_por_paginas_da_la_lista_completa_con_empates_de_instante()
    {
        foreach (var tamano in new[] { 1, 2, 3 })
        {
            Assert.Equal(await DiaDeUnaVez(new DateOnly(2023, 12, 1)), await DiaPorPaginas(new DateOnly(2023, 12, 1),
                tamano));
        }

        Assert.Equal([1L, 3L, 2L], await DiaPorPaginas(new DateOnly(2023, 12, 1), 1));
    }

    [Fact]
    public async Task Recorrer_por_paginas_respeta_los_dias_de_23_y_25_horas()
    {
        await Cargar(Escenario.Bordes());
        foreach (var dia in new[] { new DateOnly(2022, 10, 29), new DateOnly(2022, 10, 30), new DateOnly(2022, 10, 31),
                     new DateOnly(2022, 4, 3), new DateOnly(2022, 4, 4) })
        {
            Assert.Equal(await DiaDeUnaVez(dia), await DiaPorPaginas(dia, 1));
        }
    }

    [Fact]
    public async Task Recorrer_el_reporte_por_paginas_da_el_reporte_completo()
    {
        var (desde, hasta) = (new DateOnly(2023, 12, 1), new DateOnly(2023, 12, 31));
        await using var contexto = baseDePrueba.Contexto();
        var completo = await new ConsultasEf(contexto).ReporteDeOrdenesAsync(desde, hasta, default);
        var renglones = new List<RenglonDeReporte>();
        PosicionDeRenglon? despuesDe = null;
        var paginas = 0;
        while (true)
        {
            var pagina = await Lotes().RenglonesDelReporteAsync(desde, hasta, despuesDe, 1, default);
            paginas++;
            renglones.AddRange(pagina.Elementos.Select(r => r.Renglon));
            if (!pagina.HayMas)
            {
                break;
            }

            despuesDe = pagina.Elementos[^1].Posicion;
        }

        Assert.Equal(completo, renglones);
        Assert.Equal(3, paginas); // dos renglones del mismo folio partidos por la página
    }

    /// <summary>Ronda 2 a ciegas (T2): con dos documentos para una operación, el lote elige el MISMO que el detalle.</summary>
    [Fact]
    public async Task El_lote_elige_el_mismo_documento_que_el_detalle()
    {
        var estado = Escenario.Estado();
        var segundo = OrdenDePago.Registrar(Guid.Parse("4169faf3-0000-4000-8000-000000000001"), "OP-000000009", 1,
            estado.Ordenes[0].Datos with { ReferenciaMt103 = "BFN231205000001" }, 19939.20m,
            Escenario.Mx(2023, 12, 5, 9, 0), 99);
        await Cargar(estado with { Ordenes = [.. estado.Ordenes, segundo] });

        var ordenes = await Lotes().OrdenesDeOperacionesAsync([1, 2, 3, 4, 999], default);
        await using var contexto = baseDePrueba.Contexto();
        var detalle = await new ConsultasEf(contexto).DetalleAsync(1, default);
        Assert.Equal(detalle!.Orden, ordenes[1]);
        Assert.Equal("OP-000000009", ordenes[1].Folio);
        Assert.Equal([1L, 2L, 3L], ordenes.Keys.Order()); // la 4 no tiene documento y la 999 no existe
    }

    [Fact]
    public async Task Los_lotes_traen_solo_lo_que_existe_y_las_partidas_en_su_orden()
    {
        var operaciones = await Lotes().OperacionesAsync([4, 1, 999, 1], default);
        Assert.Equal([1L, 4L], operaciones.Keys.Order());
        Assert.Equal("Dólar estadounidense", operaciones[1].NombreMoneda);

        var cliente = await Lotes().SolicitadoPorElClienteAsync([Escenario.Conciliada, Escenario.Vencida], default);
        Assert.Equal(["PRINCIPAL", "COMISION", "IVA", "GASTOS_OUR"],
            cliente[Escenario.Conciliada].Select(p => p.Concepto));
        var corresponsal = await Lotes().LiquidadoPorElCorresponsalAsync(
            [Escenario.Conciliada, Escenario.Vencida, Guid.Empty], default);
        Assert.Equal(["ABONO", "COMISION_CORRESPONSAL"], corresponsal[Escenario.Conciliada].Select(p => p.Concepto));
        Assert.False(corresponsal.ContainsKey(Escenario.Vencida)); // vencida: nada abonado
        Assert.False(corresponsal.ContainsKey(Guid.Empty));
    }
}
