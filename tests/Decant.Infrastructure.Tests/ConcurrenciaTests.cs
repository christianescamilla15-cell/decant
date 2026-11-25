using Decant.Application.Puertos;
using Decant.Infrastructure.Persistencia;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace Decant.Infrastructure.Tests;

/// <summary>
/// Carreras contra los índices únicos (folio, UETR, regla y caso de la marca, archivo por corrida): dos cargas a la
/// vez del mismo documento no duplican ni chocan, y una carga que sí choca no deja nada a medias.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class ConcurrenciaTests(BaseDePrueba baseDePrueba)
{
    private async Task<(int Operaciones, int Ordenes, int Registros, int Marcas, int Descartadas, int Corridas)>
        Conteos()
    {
        await using var c = baseDePrueba.Contexto();
        return (await c.Operaciones.CountAsync(), await c.Ordenes.CountAsync(), await c.Registros.CountAsync(),
            await c.Marcas.CountAsync(), await c.LiquidacionesDescartadas.CountAsync(), await c.Corridas.CountAsync());
    }

    private async Task Guardar(EstadoTobe estado)
    {
        await using var contexto = baseDePrueba.Contexto();
        await new AlmacenPostgres(contexto).GuardarAsync(estado, default);
    }

    [Fact]
    public async Task Cuatro_cargas_simultaneas_del_mismo_documento_dejan_una_sola_copia()
    {
        await Guardar(Escenario.Estado());
        var antes = await Conteos();
        var estado = Escenario.Estado() with
        {
            Archivos = [new ResultadoDeArchivo("20231204.fin", 2, 2, 0, 0, "leído", string.Empty)],
        };
        using var salida = new Barrier(4);
        await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => Task.Run(async () =>
        {
            salida.SignalAndWait(TimeSpan.FromSeconds(30));
            await Guardar(estado);
        })));
        var despues = await Conteos();
        Assert.Equal(antes with { Corridas = antes.Corridas + 4 }, despues);
        await using var c = baseDePrueba.Contexto();
        Assert.Equal(4, await c.ResultadosDeArchivo.CountAsync(r => r.Archivo == "20231204.fin"
            && c.Corridas.OrderByDescending(x => x.Id).Take(4).Select(x => x.Id).Contains(r.CorridaId)));
    }

    /// <summary>Dos lotes DISTINTOS a la vez: queda uno u otro completo (el último en confirmar), nunca una mezcla.</summary>
    [Fact]
    public async Task Dos_cargas_distintas_a_la_vez_dejan_una_completa_y_no_una_mezcla()
    {
        var completo = Escenario.Estado() with { Corrida = Escenario.Estado().Corrida with { Origen = "completo" } };
        var parcial = completo with
        {
            Corrida = completo.Corrida with { Origen = "parcial" },
            Ordenes = completo.Ordenes.Take(1).ToList(),
            Descartadas = [],
            Marcas = [],
        };
        using var salida = new Barrier(2);
        await Task.WhenAll(new[] { completo, parcial }.Select(e => Task.Run(async () =>
        {
            salida.SignalAndWait(TimeSpan.FromSeconds(30));
            await Guardar(e);
        })));
        await using var c = baseDePrueba.Contexto();
        var ultima = await c.Corridas.OrderByDescending(x => x.Id).Select(x => x.Origen).FirstAsync();
        var esperado = ultima == "completo" ? (3, 1, 1) : (1, 0, 0);
        Assert.Equal(esperado, (await c.Ordenes.CountAsync(), await c.Marcas.CountAsync(),
            await c.LiquidacionesDescartadas.CountAsync()));
    }

    /// <summary>
    /// El mismo documento dos veces en UN lote choca con el índice único: es un error técnico (excepción), la
    /// transacción se revierte entera y el estado anterior queda intacto; volver a correr con el lote corregido
    /// reanuda.
    /// </summary>
    [Fact]
    public async Task Un_lote_que_choca_con_un_indice_unico_no_deja_nada_a_medias()
    {
        await Guardar(Escenario.Estado());
        var antes = await Conteos();
        var estado = Escenario.Estado();
        var duplicado = estado with { Ordenes = [.. estado.Ordenes, estado.Ordenes[0]] };
        var error = await Assert.ThrowsAsync<PostgresException>(() => Guardar(duplicado));
        Assert.Equal(PostgresErrorCodes.UniqueViolation, error.SqlState);
        Assert.Equal(antes, await Conteos());
        await Guardar(estado);
        Assert.Equal(antes with { Corridas = antes.Corridas + 1 }, await Conteos());
    }
}
