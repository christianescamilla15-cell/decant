using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;
using Decant.Infrastructure.Persistencia;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace Decant.Infrastructure.Tests;

/// <summary>Todo lo que el ORM y el COPY traducen a SQL, contra PostgreSQL real.</summary>
[Collection(nameof(BaseDePrueba))]
public class PersistenciaTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    public async Task InitializeAsync()
    {
        await using var contexto = baseDePrueba.Contexto();
        await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Estado(), default);
    }

    public Task DisposeAsync() => Task.CompletedTask;

    private async Task<T> Con<T>(Func<DecantDbContext, Task<T>> accion)
    {
        await using var contexto = baseDePrueba.Contexto();
        return await accion(contexto);
    }

    [Fact]
    public async Task Las_migraciones_crean_la_columna_que_ningun_reporte_imprime_y_guardan_instantes()
    {
        await using var conexion = new NpgsqlConnection(baseDePrueba.Conexion);
        await conexion.OpenAsync();
        await using var comando = new NpgsqlCommand(
            "SELECT table_name || '.' || column_name, data_type, COALESCE(numeric_precision, 0), " +
            "COALESCE(numeric_scale, 0) FROM information_schema.columns WHERE table_schema = 'decant'", conexion);
        var columnas = new Dictionary<string, (string Tipo, int P, int S)>();
        await using (var lector = await comando.ExecuteReaderAsync())
        {
            while (await lector.ReadAsync())
            {
                columnas[lector.GetString(0)] = (lector.GetString(1), lector.GetInt32(2), lector.GetInt32(3));
            }
        }

        Assert.True(columnas.ContainsKey("orden_pago.codigo_proposito")); // T6
        Assert.Equal("timestamp with time zone", columnas["orden_pago.fecha_envio"].Tipo); // T5
        Assert.Equal(("numeric", 18, 2), columnas["partida_cliente.monto"]);
        Assert.Equal(("numeric", 9, 2), columnas["orden_pago.horas_liquidacion"]);
        Assert.Equal("uuid", columnas["orden_pago.uetr"].Tipo);
    }

    [Fact]
    public async Task El_detalle_devuelve_las_dos_listas_con_su_nombre_nulos_e_instantes()
    {
        var detalle = await Con(c => new ConsultasEf(c).DetalleAsync(1, default));
        Assert.NotNull(detalle);
        Assert.Null(detalle.Operacion.CuentaClabe);          // T3: no «NA»
        Assert.Null(detalle.Operacion.TipoCambioReferencia); // T3: no 0
        Assert.Equal(TimeSpan.Zero, detalle.Operacion.FechaOperacion.Offset);
        Assert.Equal(Escenario.Mx(2023, 12, 1, 10, 0), detalle.Operacion.FechaOperacion);
        Assert.Equal("ARTESANÍAS DEL LAGO, S.C.", detalle.Operacion.Cliente);
        Assert.Equal(Escenario.Conciliada, detalle.Orden!.Uetr);
        Assert.Equal(2, detalle.Orden.Registros);
        Assert.Equal([Conceptos.Principal, Conceptos.Comision, Conceptos.Iva, Conceptos.GastosOur],
            detalle.SolicitadoPorElCliente.Select(p => p.Concepto));
        Assert.Equal([Conceptos.Abono, Conceptos.ComisionCorresponsal],
            detalle.LiquidadoPorElCorresponsal.Select(p => p.Concepto));
        Assert.Equal(988.50m, detalle.LiquidadoPorElCorresponsal[0].Monto);
        Assert.Equal(new DateTimeOffset(2023, 12, 4, 14, 15, 42, TimeSpan.Zero),
            detalle.LiquidadoPorElCorresponsal[0].FechaHora);
    }

    /// <summary>
    /// Ronda 2 a ciegas, T2: la constancia del legado se quedaba con la última fila que entregara el plan. El TO-BE
    /// elige EXPLÍCITAMENTE el documento con el registro más reciente si una operación tuviera dos.
    /// </summary>
    [Fact]
    public async Task Si_una_operacion_tuviera_dos_documentos_el_detalle_elige_el_mas_reciente()
    {
        var estado = Escenario.Estado();
        var segundo = OrdenDePago.Registrar(Guid.Parse("4169faf3-0000-4000-8000-000000000001"), "OP-000000009", 1,
            estado.Ordenes[0].Datos with { ReferenciaMt103 = "BFN231205000001" }, 19939.20m,
            Escenario.Mx(2023, 12, 5, 9, 0), 99);
        await using (var contexto = baseDePrueba.Contexto())
        {
            await new AlmacenPostgres(contexto).GuardarAsync(estado with { Ordenes = [.. estado.Ordenes, segundo] },
                default);
        }

        var detalle = await Con(c => new ConsultasEf(c).DetalleAsync(1, default));
        Assert.Equal("OP-000000009", detalle!.Orden!.Folio);
    }

    [Fact]
    public async Task Una_operacion_sin_orden_tiene_detalle_sin_listas_y_una_inexistente_no_tiene()
    {
        var sinOrden = await Con(c => new ConsultasEf(c).DetalleAsync(4, default));
        Assert.Null(sinOrden!.Orden);
        Assert.Empty(sinOrden.SolicitadoPorElCliente);
        Assert.Null(await Con(c => new ConsultasEf(c).DetalleAsync(999, default)));
    }

    /// <summary>T2 se replica (un renglón por partida abonada) y el orden es EXPLÍCITO: fecha valor, folio, renglón.</summary>
    [Fact]
    public async Task El_reporte_solo_trae_partidas_abonadas_en_orden_explicito()
    {
        var reporte = await Con(c => new ConsultasEf(c).ReporteDeOrdenesAsync(new DateOnly(2023, 12, 1),
            new DateOnly(2023, 12, 31), default));
        Assert.Equal([("OP-000000002", Conceptos.Abono), ("OP-000000002", Conceptos.ComisionCorresponsal),
            ("OP-000000003", Conceptos.Abono)], reporte.Select(r => (r.Folio, r.Concepto)));
        Assert.DoesNotContain(reporte, r => r.Uetr == Escenario.Vencida);
        Assert.Empty(await Con(c => new ConsultasEf(c).ReporteDeOrdenesAsync(new DateOnly(2023, 11, 1),
            new DateOnly(2023, 11, 30), default)));
    }

    /// <summary>T1: el día es el del calendario de la Ciudad de México y el orden es fecha y luego id.</summary>
    [Fact]
    public async Task La_lista_del_dia_usa_el_calendario_local_y_desempata_por_id()
    {
        var lista = await Con(c => new ConsultasEf(c).ListaAsync(new DateOnly(2023, 12, 1), 200, default));
        Assert.Equal([1L, 3L, 2L], lista.Select(o => o.Id)); // la 2 es de las 23:30 del 1 (05:30Z del 2)
        Assert.Single(await Con(c => new ConsultasEf(c).ListaAsync(new DateOnly(2023, 12, 1), 1, default)));
        Assert.Equal([4L], (await Con(c => new ConsultasEf(c).ListaAsync(new DateOnly(2023, 12, 2), 200, default)))
            .Select(o => o.Id));
    }

    [Fact]
    public async Task Guardar_reemplaza_el_estado_completo_y_es_repetible()
    {
        await using (var contexto = baseDePrueba.Contexto())
        {
            await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Estado(), default);
        }

        var conteos = await Con(async c => (await c.Operaciones.CountAsync(), await c.Ordenes.CountAsync(),
            await c.Registros.CountAsync(), await c.PartidasCliente.CountAsync(), await c.Marcas.CountAsync(),
            await c.LiquidacionesDescartadas.CountAsync()));
        Assert.Equal((4, 3, 4, 10, 1, 1), conteos);
    }

    [Fact]
    public async Task El_reproceso_persistido_conserva_lo_resuelto()
    {
        await using (var contexto = baseDePrueba.Contexto())
        {
            var almacen = new AlmacenPostgres(contexto);
            var previo = await almacen.EstadosAsync(default);
            Assert.Equal(EstatusOrden.Conciliada, previo[Escenario.Conciliada].Estatus);
            var nuevo = previo.ToDictionary(x => x.Key, x => x.Value with { VersionDeReglas = "v2" });
            nuevo[Escenario.Conciliada] = new EstadoDeDocumento(EstatusOrden.Vencida, null, "v2");
            var r = Reprocesamiento.Combinar(previo, nuevo);
            await almacen.ActualizarEstadosAsync(r.Estados, Escenario.Estado().Corrida with { Tipo = "reproceso" },
                default);
        }

        var despues = await Con(c => new AlmacenPostgres(c).EstadosAsync(default));
        Assert.Equal(EstatusOrden.Conciliada, despues[Escenario.Conciliada].Estatus);
        Assert.Equal("v2", despues[Escenario.Vencida].VersionDeReglas);
        // la bitácora de corridas se acumula entre cargas: la última es el reproceso
        Assert.Equal("reproceso", await Con(c => c.Corridas.OrderByDescending(x => x.Id).Select(x => x.Tipo)
            .FirstAsync()));
    }
}
