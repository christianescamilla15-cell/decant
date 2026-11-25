using Decant.Application.Motor;
using Decant.Domain.Pagos;

namespace Decant.Application.Tests;

/// <summary>El replay del universo con dobles: re-registro, liquidación, D3, vencimiento con la noche del job y
/// «sólo marca». El reloj del sistema (2026) no entra a ninguna regla.</summary>
public class ReproducirUniversoTests
{
    private static readonly RelojFijo Hoy = new(new DateTimeOffset(2026, 11, 24, 12, 0, 0, TimeSpan.Zero));

    private static UniversoEnMemoria Escenario()
    {
        var u = new UniversoEnMemoria();
        u.ListaOperaciones.Add(Universo.Operacion(1, new DateTime(2023, 12, 1, 10, 0, 0)));
        u.ListaOperaciones.Add(Universo.Operacion(2, new DateTime(2023, 12, 1, 11, 0, 0)));
        // documento 1: alta el viernes, re-registro el lunes 07:00, liquidado el lunes a las 09:15 de Nueva York
        u.ListaRegistros.Add(Universo.Registro(10, 1, Universo.Uetr1, "BFN231201000001", new DateTime(2023, 12, 1, 10, 5, 0)));
        u.ListaRegistros.Add(Universo.Registro(11, 2, Universo.Uetr2, "BFN231201000002", new DateTime(2023, 12, 1, 11, 5, 0)));
        u.ListaRegistros.Add(Universo.Registro(12, 1, Universo.Uetr1, "BFN231201000001", new DateTime(2023, 12, 4, 7, 0, 0),
            new DateTime(2023, 12, 1, 10, 5, 30)));
        u.ListaRegistros.Add(Universo.Registro(13, 2, Universo.Uetr2, "BFN231201000002", new DateTime(2023, 12, 4, 7, 0, 2),
            new DateTime(2023, 12, 1, 11, 5, 30)));
        u.Buzon.Add(Universo.Confirmacion(Universo.Uetr1, "BFN231201000001", "FICT000000000001",
            new DateTime(2023, 12, 4, 9, 15, 0), "-0500", "988,50", "11,50"));
        // documento 2: el job lo vence la noche del lunes 4 (enviado el viernes 1 a las 11:05); la confirmación
        // llega el martes: D3
        u.Buzon.Add(Universo.Confirmacion(Universo.Uetr2, "BFN231201000002", "FICT000000000002",
            new DateTime(2023, 12, 5, 9, 0, 0), "-0500", "1000,00"));
        u.ListaPartidas.Add(new(1, 988.50m, new DateTime(2023, 12, 4, 9, 15, 42), "FICT000000000001   "));
        return u;
    }

    private static async Task<(ResumenDeReplay Resumen, AlmacenEnMemoria Almacen)> Correr(UniversoEnMemoria u,
        Banderas banderas, DateTimeOffset? hasta = null)
    {
        var almacen = new AlmacenEnMemoria();
        var resumen = await new ReproducirUniversoManejador(u, almacen, Hoy)
            .ManejarAsync(new ReproducirUniverso(new OpcionesDelMotor(banderas, hasta), "prueba"), default);
        return (resumen, almacen);
    }

    [Fact]
    public async Task Reproduce_re_registro_liquidacion_d3_y_vencimiento_con_las_noches_del_job()
    {
        var (resumen, almacen) = await Correr(Escenario(), Banderas.Todas);
        var docs = almacen.Guardado!.Ordenes.ToDictionary(o => o.Uetr.ToString());
        var uno = docs[Universo.Uetr1];
        Assert.Equal(("OP-000000001", EstatusOrden.Conciliada, 2), (uno.Folio, uno.Estatus, uno.Registros.Count));
        // envío 10:05:30 CDMX = 16:05:30Z; liquidación 09:15:42 NY (segundos del respaldo) = 14:15:42Z del lunes
        Assert.Equal(70.17m, uno.HorasLiquidacion);
        Assert.Equal("FICT000000000001", uno.LiquidadoPorElCorresponsal[0].Referencia); // sin el relleno
        var dos = docs[Universo.Uetr2];
        Assert.Equal(("OP-000000002", EstatusOrden.Vencida), (dos.Folio, dos.Estatus));
        Assert.Equal("documento VENCIDA", Assert.Single(almacen.Guardado.Descartadas).Motivo);
        Assert.Equal(2, resumen.ReRegistros);
        Assert.Equal(1, resumen.Descartadas);
        Assert.Equal(1, resumen.Vencidas);
        Assert.Equal(1, resumen.Conciliadas);
        Assert.Equal(1, resumen.ConfirmacionesConSegundosDelRespaldo);
        Assert.Empty(resumen.Errores);
    }

    [Fact]
    public async Task El_folio_fx_es_el_consumible_en_orden_de_llegada()
    {
        var (_, almacen) = await Correr(Escenario(), Banderas.Todas);
        Assert.Equal(["FX-000000001", "FX-000000002"], almacen.Guardado!.Operaciones.Select(o => o.Folio));
        Assert.Equal(3, almacen.Guardado.Consecutivos["FX"]);
    }

    [Fact]
    public async Task Con_la_bandera_apagada_solo_marca_y_no_vence()
    {
        var (resumen, almacen) = await Correr(Escenario(), Banderas.Todas with { VencerAutomatico = false });
        var marcas = almacen.Guardado!.Marcas.Where(m => m.Regla == ReproducirUniversoManejador.ReglaVencimiento)
            .ToDictionary(m => m.Caso);
        Assert.True(marcas[Universo.Uetr2].Cumple);   // ✔ la vencería la noche del 4
        Assert.False(marcas[Universo.Uetr1].Cumple);  // ✘ se liquidó antes
        Assert.Equal(0, resumen.Vencidas);
        // sin vencerla, la confirmación tardía SÍ entra (queda liquidada: el universo termina antes de la noche
        // siguiente); por eso la marca se compara contra la bitácora del legado y no contra el estado final
        Assert.Equal(EstatusOrden.Liquidada,
            almacen.Guardado.Ordenes.Single(o => o.Uetr.ToString() == Universo.Uetr2).Estatus);
    }

    [Fact]
    public async Task Con_la_conciliacion_en_solo_marca_queda_liquidada_y_marcada()
    {
        var (_, almacen) = await Correr(Escenario(), Banderas.Todas with { ConciliarAutomatico = false });
        var uno = almacen.Guardado!.Ordenes.Single(o => o.Uetr.ToString() == Universo.Uetr1);
        Assert.Equal(EstatusOrden.Liquidada, uno.Estatus);
        var marca = Assert.Single(almacen.Guardado.Marcas);
        Assert.True(marca.Cumple);
        Assert.Contains("CONCILIADA", marca.Detalle, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Hasta_el_corte_no_procesa_lo_posterior()
    {
        var corte = new DateTimeOffset(2023, 12, 4, 12, 0, 0, TimeSpan.Zero); // antes de la liquidación del lunes
        var (resumen, almacen) = await Correr(Escenario(), Banderas.Todas, corte);
        Assert.Equal(corte, resumen.Limite);
        Assert.All(almacen.Guardado!.Ordenes, o => Assert.Equal(EstatusOrden.Enviada, o.Estatus));
    }

    [Fact]
    public async Task Una_confirmacion_sin_documento_queda_visible_como_huerfana()
    {
        var u = Escenario();
        u.Buzon.Add(Universo.Confirmacion("b34b9ba7-b64f-4480-9fb1-2bc85e070f8d", "BFN231204000099",
            "FICT000000000003", new DateTime(2023, 12, 4, 10, 0, 0), "-0500", "10,00"));
        var (resumen, almacen) = await Correr(u, Banderas.Todas);
        Assert.Equal(1, resumen.Huerfanas);
        Assert.Contains(almacen.Guardado!.Descartadas, d => d.Motivo == "sin_documento");
    }

    [Fact]
    public async Task La_referencia_21_que_no_cruza_se_cuenta_como_error()
    {
        var u = Escenario();
        u.Buzon[0] = u.Buzon[0].Replace(":21:BFN231201000001", ":21:BFN231201999999", StringComparison.Ordinal);
        var (resumen, _) = await Correr(u, Banderas.Todas);
        Assert.Equal(1, resumen.Errores["referencia_21_no_cruza"]);
    }

    /// <summary>
    /// Regresión (encontrada contra la verdad del generador): el documento 3f4abf43… se envió el 30-oct-2022 a las
    /// 01:30:59 de la PRIMERA vuelta de la hora y se re-registró el 31 a las 07:01. El re-registro repite ese envío y
    /// no debe empujarlo a la segunda vuelta.
    /// </summary>
    [Fact]
    public async Task Un_re_registro_no_cambia_la_vuelta_de_la_hora_del_envio_original()
    {
        var u = new UniversoEnMemoria();
        u.ListaOperaciones.Add(Universo.Operacion(1, new DateTime(2022, 10, 30, 1, 20, 0)));
        var envio = new DateTime(2022, 10, 30, 1, 30, 59);
        u.ListaRegistros.Add(Universo.Registro(159429, 1, Universo.Uetr1, "BFN221030000001",
            new DateTime(2022, 10, 30, 1, 30, 27), envio));
        u.ListaRegistros.Add(Universo.Registro(159548, 1, Universo.Uetr1, "BFN221030000001",
            new DateTime(2022, 10, 31, 7, 1, 32), envio));
        var (_, almacen) = await Correr(u, Banderas.Todas);
        var doc = Assert.Single(almacen.Guardado!.Ordenes);
        Assert.Equal(new DateTimeOffset(2022, 10, 30, 6, 30, 59, TimeSpan.Zero), doc.Datos.FechaEnvio);
    }
}
