using Decant.Application.Abstracciones;
using Decant.Application.Carga;
using Decant.Application.Puertos;
using Decant.Application.Reproceso;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;

namespace Decant.Application.Tests;

public class CargaYReprocesoTests
{
    private static readonly RelojFijo Hoy = new(new DateTimeOffset(2026, 11, 24, 12, 0, 0, TimeSpan.Zero));

    private static (UniversoEnMemoria, OraculoEnMemoria) Historia()
    {
        var u = new UniversoEnMemoria();
        u.ListaOperaciones.Add(Universo.Operacion(1, new DateTime(2023, 12, 1, 10, 0, 0)));
        u.ListaRegistros.Add(Universo.Registro(10, 1, Universo.Uetr1, "BFN231201000001", new DateTime(2023, 12, 1, 10, 5, 0)));
        u.ListaRegistros.Add(Universo.Registro(12, 1, Universo.Uetr1, "BFN231201000001", new DateTime(2023, 12, 4, 7, 0, 0),
            new DateTime(2023, 12, 1, 10, 5, 30)));
        u.ListaPartidas.Add(new(1, 988.50m, new DateTime(2023, 12, 4, 9, 15, 42), "FICT000000000001   "));
        var o = new OraculoEnMemoria();
        o.ListaOperaciones.Add(new(1, "FX-000000001", 19929.24m, 19.929243m));
        o.ListaOrdenes.Add(new(10, "OP-000000001", "REEMPLAZADA", null));
        o.ListaOrdenes.Add(new(12, "OP-000000001", "CONCILIADA", 70.17m));
        o.ListaCorresponsal.Add(new(1, 12, 1, "ABONO", "USD"));
        o.ListaCliente.Add(new(1, 10, 1, "PRINCIPAL", "USD", 1000m, new DateTime(2023, 12, 1, 10, 5, 0), "OP-000000001"));
        o.ListaCliente.Add(new(2, 12, 1, "PRINCIPAL", "USD", 1000m, new DateTime(2023, 12, 4, 7, 0, 0), "OP-000000001"));
        return (u, o);
    }

    [Fact]
    public async Task La_carga_historica_lleva_los_resultados_tal_cual_y_un_documento_por_uetr()
    {
        var (u, o) = Historia();
        var almacen = new AlmacenEnMemoria();
        var r = await new MigrarHistoricoManejador(u, o, almacen, Hoy).ManejarAsync(new MigrarHistorico("prueba"), default);
        var doc = Assert.Single(almacen.Guardado!.Ordenes);
        Assert.Equal((EstatusOrden.Conciliada, 70.17m, 2), (doc.Estatus, doc.HorasLiquidacion, doc.Registros.Count));
        Assert.Equal([10L, 12L], doc.Registros.Select(x => x.IdLegado!.Value));
        Assert.Null(almacen.Guardado.Operaciones[0].Datos.TipoDeCambioReferencia is null ? null : (object?)null);
        Assert.Equal("FICT000000000001", doc.LiquidadoPorElCorresponsal[0].Referencia);
        Assert.Equal((1, 1), (r.PartidasDelCliente, r.PartidasDelClienteDeRegistrosReemplazados));
        Assert.Empty(r.Errores);
        Assert.Equal("migracion", almacen.UltimaCorrida!.Tipo);
    }

    [Fact]
    public async Task Un_documento_sin_exactamente_una_fila_vigente_es_un_error_contado()
    {
        var (u, o) = Historia();
        o.ListaOrdenes[0] = o.ListaOrdenes[0] with { Estatus = "ENVIADA" }; // dos vigentes para la misma UETR
        var r = await new MigrarHistoricoManejador(u, o, new AlmacenEnMemoria(), Hoy)
            .ManejarAsync(new MigrarHistorico("prueba"), default);
        Assert.Equal(1, r.Errores["documento_sin_una_fila_vigente"]);
    }

    [Fact]
    public async Task Reprocesar_conserva_lo_resuelto_y_lo_reporta()
    {
        var almacen = new AlmacenEnMemoria();
        var resuelto = Guid.NewGuid();
        almacen.Estados[resuelto] = new EstadoDeDocumento(EstatusOrden.Conciliada, 3m, "v1");
        var nuevo = new Dictionary<Guid, EstadoDeDocumento> { [resuelto] = new(EstatusOrden.Enviada, null, "v2") };
        var r = await new AplicarReprocesoManejador(almacen, Hoy).ManejarAsync(new AplicarReproceso(nuevo, "prueba"),
            default);
        Assert.Equal(EstatusOrden.Conciliada, almacen.Estados[resuelto].Estatus);
        Assert.Single(r.Conservados);
        Assert.Equal("reproceso", almacen.UltimaCorrida!.Tipo);
    }

    [Fact]
    public async Task El_mediador_resuelve_el_manejador_y_falla_con_nombre_si_no_hay()
    {
        var almacen = new AlmacenEnMemoria();
        var manejador = new AplicarReprocesoManejador(almacen, Hoy);
        var mediador = new Mediador(new Proveedor(typeof(IManejador<AplicarReproceso, ResultadoDeReproceso>), manejador));
        var r = await mediador.EnviarAsync(new AplicarReproceso(new Dictionary<Guid, EstadoDeDocumento>(), "x"));
        Assert.Empty(r.Conservados);
        var vacio = new Mediador(new Proveedor(typeof(object), new object()));
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            vacio.EnviarAsync(new AplicarReproceso(new Dictionary<Guid, EstadoDeDocumento>(), "x")));
        Assert.Contains(nameof(AplicarReproceso), error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("Pruebas", "emulador://corresponsal-emulado:8080/confirmaciones", false, 0)]
    [InlineData("Pruebas", "https://corresponsal.bfn.example/confirmaciones", false, 1)] // QA nunca al real
    [InlineData("Produccion", "https://corresponsal.bfn.example/confirmaciones", false, 0)]
    [InlineData("Produccion", "https://corresponsal.bfn.example/confirmaciones", true, 1)] // sin contrato ni humo
    public void La_configuracion_de_cada_ambiente_se_valida(string ambiente, string corresponsal, bool notificar,
        int errores)
    {
        var c = new ConfiguracionDeAmbiente(ambiente, Banderas.Todas with { NotificarCorresponsal = notificar },
            new Destinos(corresponsal, "operaciones@bfn.example"));
        Assert.Equal(errores, c.Validar().Count);
    }

    private sealed class Proveedor(Type tipo, object servicio) : IServiceProvider
    {
        public object? GetService(Type serviceType) => serviceType == tipo ? servicio : null;
    }
}
