using Decant.Application.Carga;
using Decant.Application.Motor;
using Decant.Application.Puertos;
using Decant.Domain.Pagos;

namespace Decant.Application.Tests;

/// <summary>
/// Invariantes del lote: cargar dos veces no duplica, permutar el lote da lo mismo, un archivo
/// dañado no detiene a los demás, un rechazo de negocio no es un error técnico ni se reintenta y lo que no aplica
/// queda UNA vez con su motivo.
/// </summary>
public class InvariantesDeLoteTests
{
    private static readonly RelojFijo Hoy = new(new DateTimeOffset(2026, 11, 24, 12, 0, 0, TimeSpan.Zero));

    private static readonly string ConfirmacionUno = Universo.Confirmacion(Universo.Uetr1, "BFN231201000001",
        "FICT000000000001", new DateTime(2023, 12, 4, 9, 15, 0), "-0500", "988,50", "11,50");

    /// <summary>Llega el martes, cuando el documento 2 ya venció: no aplica (D3).</summary>
    private static readonly string ConfirmacionTardia = Universo.Confirmacion(Universo.Uetr2, "BFN231201000002",
        "FICT000000000002", new DateTime(2023, 12, 5, 9, 0, 0), "-0500", "1000,00");

    private static UniversoEnMemoria Escenario()
    {
        var u = new UniversoEnMemoria();
        u.ListaOperaciones.Add(Universo.Operacion(1, new DateTime(2023, 12, 1, 10, 0, 0)));
        u.ListaOperaciones.Add(Universo.Operacion(2, new DateTime(2023, 12, 1, 11, 0, 0)));
        u.ListaOperaciones.Add(Universo.Operacion(3, new DateTime(2023, 12, 1, 11, 0, 0))); // mismo minuto que la 2
        u.ListaRegistros.Add(Universo.Registro(10, 1, Universo.Uetr1, "BFN231201000001", new DateTime(2023, 12, 1, 10, 5, 0)));
        u.ListaRegistros.Add(Universo.Registro(11, 2, Universo.Uetr2, "BFN231201000002", new DateTime(2023, 12, 1, 11, 5, 0)));
        u.ListaRegistros.Add(Universo.Registro(12, 1, Universo.Uetr1, "BFN231201000001", new DateTime(2023, 12, 4, 7, 0, 0),
            new DateTime(2023, 12, 1, 10, 5, 30)));
        u.Archivos.Add(new ArchivoDeInterfaz("20231204.fin", ConfirmacionUno + "\n", null));
        u.Archivos.Add(new ArchivoDeInterfaz("20231205.fin", ConfirmacionTardia + "\n", null));
        u.ListaPartidas.Add(new(1, 988.50m, new DateTime(2023, 12, 4, 9, 15, 42), "FICT000000000001   "));
        return u;
    }

    private static async Task<(ResumenDeReplay Resumen, AlmacenEnMemoria Almacen)> Correr(IUniverso u,
        IAlmacenTobe? almacen = null)
    {
        var destino = almacen as AlmacenEnMemoria ?? new AlmacenEnMemoria();
        var resumen = await new ReproducirUniversoManejador(u, almacen ?? destino, Hoy)
            .ManejarAsync(new ReproducirUniverso(new OpcionesDelMotor(Banderas.Todas, null), "prueba"), default);
        return (resumen, destino);
    }

    /// <summary>Una huella canónica del estado: todo lo que se persiste, sin depender del orden de las listas.</summary>
    private static List<string> Huella(EstadoTobe e) =>
    [
        .. e.Operaciones.Select(o => $"op {o.Id} {o.Folio} {o.MontoMxn} {o.TipoDeCambio}").Order(StringComparer.Ordinal),
        .. e.Ordenes.Select(o =>
                $"doc {o.Uetr} {o.Folio} {o.OperacionId} {o.Estatus} {o.HorasLiquidacion} {o.FechaRegistro:O} " +
                $"{string.Join(';', o.Registros.Select(r => $"{r.Numero}@{r.Instante:O}#{r.IdLegado}"))} " +
                $"{string.Join(';', o.SolicitadoPorElCliente.Select(p => $"{p.Renglon}{p.Concepto}{p.Monto}"))} " +
                $"{string.Join(';', o.LiquidadoPorElCorresponsal.Select(p => $"{p.Renglon}{p.Concepto}{p.Monto}{p.FechaHora:O}"))}")
            .Order(StringComparer.Ordinal),
        .. e.Descartadas.Select(d => $"descartada {d.Uetr} {d.TrnCorresponsal} {d.Instante:O} {d.Motivo}")
            .Order(StringComparer.Ordinal),
        .. e.Marcas.Select(m => $"marca {m.Regla} {m.Caso} {m.Instante:O} {m.Cumple}").Order(StringComparer.Ordinal),
        .. e.Consecutivos.Select(c => $"consecutivo {c.Key} {c.Value}").Order(StringComparer.Ordinal),
    ];

    [Fact]
    public async Task Correr_el_mismo_lote_dos_veces_deja_el_mismo_estado_sin_duplicar()
    {
        var u = Escenario();
        var almacen = new AlmacenEnMemoria();
        await Correr(u, almacen);
        var primera = Huella(almacen.Guardado!);
        var (resumen, _) = await Correr(u, almacen);
        Assert.Equal(primera, Huella(almacen.Guardado!));
        Assert.Equal((3, 2, 1), (almacen.Guardado!.Operaciones.Count, almacen.Guardado.Ordenes.Count,
            almacen.Guardado.Descartadas.Count));
        Assert.Equal(0, resumen.ConfirmacionesRepetidas);
    }

    [Fact]
    public async Task El_mismo_archivo_dos_veces_en_el_lote_cuenta_una_vez_y_lo_que_no_aplica_queda_una_vez()
    {
        var u = Escenario();
        u.Archivos.Add(new ArchivoDeInterfaz("20231205_reenvio.fin", ConfirmacionTardia + "\n$" + ConfirmacionUno + "\n",
            null));
        var (resumen, almacen) = await Correr(u);
        var (resumenSinRepetir, sinRepetir) = await Correr(Escenario());
        Assert.Equal(Huella(sinRepetir.Guardado!), Huella(almacen.Guardado!));
        var descartada = Assert.Single(almacen.Guardado!.Descartadas);
        Assert.Equal("documento VENCIDA", descartada.Motivo);
        Assert.Equal((2, resumenSinRepetir.Confirmaciones), (resumen.ConfirmacionesRepetidas, resumen.Confirmaciones));
        var reenvio = almacen.Guardado.Archivos!.Single(a => a.Archivo == "20231205_reenvio.fin");
        Assert.Equal((2, 0, 0, 2), (reenvio.Mensajes, reenvio.Leidos, reenvio.Rechazados, reenvio.Repetidos));
    }

    [Fact]
    public async Task Permutar_el_lote_da_el_mismo_resultado()
    {
        var (_, base_) = await Correr(Escenario());
        var u = Escenario();
        u.ListaOperaciones.Reverse();
        u.ListaRegistros.Reverse();
        u.Archivos.Reverse();
        var (_, permutado) = await Correr(u);
        Assert.Equal(Huella(base_.Guardado!), Huella(permutado.Guardado!));
        Assert.Equal(["FX-000000001", "FX-000000002", "FX-000000003"],
            permutado.Guardado!.Operaciones.OrderBy(o => o.Id).Select(o => o.Folio));
    }

    [Fact]
    public async Task Cada_archivo_deja_su_resultado_aunque_otro_no_se_pueda_leer()
    {
        var u = Escenario();
        u.Archivos.Insert(1, new ArchivoDeInterfaz("20231204_danado.fin", null, "DecoderFallbackException"));
        u.Archivos.Add(new ArchivoDeInterfaz("20231206.fin", "{3:{121:" + Universo.Uetr1 + "}}{4:\n:20:X\n-}\n", null));
        var (resumen, almacen) = await Correr(u);
        var archivos = almacen.Guardado!.Archivos!.ToDictionary(a => a.Archivo);
        Assert.Equal(4, archivos.Count);
        Assert.Equal(("no se pudo leer", "DecoderFallbackException"),
            (archivos["20231204_danado.fin"].Estado, archivos["20231204_danado.fin"].Detalle));
        Assert.Equal(("leído", 1), (archivos["20231204.fin"].Estado, archivos["20231204.fin"].Leidos));
        Assert.Equal(("leído con rechazos", 1, "campo_faltante"), (archivos["20231206.fin"].Estado,
            archivos["20231206.fin"].Rechazados, archivos["20231206.fin"].Detalle));
        Assert.Equal((4, 1), (resumen.Archivos, resumen.ArchivosConFalla));
        // lo que sí se leyó se procesó igual: el documento 1 se concilió y el 2 venció
        Assert.Equal([EstatusOrden.Conciliada, EstatusOrden.Vencida],
            almacen.Guardado.Ordenes.OrderBy(o => o.Folio).Select(o => o.Estatus));
    }

    /// <summary>
    /// Un rechazo de validación o de negocio (mensaje incompleto, D3) se cuenta y queda con su motivo: no es una
    /// excepción, la corrida termina y se guarda UNA vez (no hay reintentos). El universo se lee una sola vez.
    /// </summary>
    [Fact]
    public async Task Un_rechazo_de_negocio_no_es_error_tecnico_ni_se_reintenta()
    {
        var u = new UniversoQueCuenta(Escenario());
        u.Interno.Archivos.Add(new ArchivoDeInterfaz("20231206.fin", "{3:{121:" + Universo.Uetr1 + "}}{4:\n:20:X\n-}\n",
            null));
        var almacen = new AlmacenQueCuenta();
        var resumen = await new ReproducirUniversoManejador(u, almacen, Hoy)
            .ManejarAsync(new ReproducirUniverso(new OpcionesDelMotor(Banderas.Todas, null), "prueba"), default);
        Assert.Equal(1, resumen.Errores["campo_faltante"]);
        Assert.Equal(1, resumen.Descartadas);
        Assert.Equal((1, 1), (almacen.Guardados, u.LecturasDelBuzon));
    }

    /// <summary>Un error técnico (la base no responde) SÍ es una excepción: sube sin estado a medias.</summary>
    [Fact]
    public async Task Un_error_tecnico_sube_como_excepcion_y_no_deja_estado()
    {
        var almacen = new AlmacenQueFalla();
        await Assert.ThrowsAsync<TimeoutException>(() => Correr(Escenario(), almacen));
        Assert.Equal(1, almacen.Intentos);
    }

    [Fact]
    public async Task Cargar_el_historico_dos_veces_deja_el_mismo_estado()
    {
        var u = Escenario();
        var o = new OraculoEnMemoria();
        o.ListaOperaciones.AddRange([new(1, "FX-000000001", 19929.24m, 19.929243m),
            new(2, "FX-000000002", 19929.24m, 19.929243m), new(3, "FX-000000003", 19929.24m, 19.929243m)]);
        o.ListaOrdenes.AddRange([new(10, "OP-000000001", "REEMPLAZADA", null), new(11, "OP-000000002", "VENCIDA", null),
            new(12, "OP-000000001", "CONCILIADA", 70.17m)]);
        var almacen = new AlmacenEnMemoria();
        var manejador = new MigrarHistoricoManejador(u, o, almacen, Hoy);
        await manejador.ManejarAsync(new MigrarHistorico("prueba"), default);
        var primera = Huella(almacen.Guardado!);
        await manejador.ManejarAsync(new MigrarHistorico("prueba"), default);
        Assert.Equal(primera, Huella(almacen.Guardado!));
        Assert.Equal(2, almacen.Guardado!.Ordenes.Count);
    }

    private sealed class UniversoQueCuenta(UniversoEnMemoria interno) : IUniverso
    {
        public UniversoEnMemoria Interno => interno;
        public int LecturasDelBuzon { get; private set; }
        public IReadOnlyList<Decant.Domain.Divisas.Moneda> Monedas() => interno.Monedas();
        public IReadOnlyList<string> Series() => interno.Series();
        public IEnumerable<OperacionDeEntrada> Operaciones() => interno.Operaciones();
        public IEnumerable<RegistroDeEntrada> RegistrosDeOrden() => interno.RegistrosDeOrden();
        public IEnumerable<PartidaDeEntrada> PartidasDelCorresponsal() => interno.PartidasDelCorresponsal();

        public IEnumerable<ArchivoDeInterfaz> ArchivosDelBuzon()
        {
            LecturasDelBuzon++;
            return interno.ArchivosDelBuzon();
        }

        public IReadOnlyList<HorarioDelJob> Horario() => interno.Horario();
    }

    private sealed class AlmacenQueCuenta : IAlmacenTobe
    {
        public int Guardados { get; private set; }

        public Task GuardarAsync(EstadoTobe estado, CancellationToken ct)
        {
            Guardados++;
            return Task.CompletedTask;
        }

        public Task<IReadOnlyDictionary<Guid, Decant.Domain.Reproceso.EstadoDeDocumento>> EstadosAsync(
            CancellationToken ct) => throw new NotSupportedException();

        public Task ActualizarEstadosAsync(IReadOnlyDictionary<Guid, Decant.Domain.Reproceso.EstadoDeDocumento> estados,
            Corrida corrida, CancellationToken ct) => throw new NotSupportedException();
    }

    private sealed class AlmacenQueFalla : IAlmacenTobe
    {
        public int Intentos { get; private set; }

        public Task GuardarAsync(EstadoTobe estado, CancellationToken ct)
        {
            Intentos++;
            throw new TimeoutException("la base no respondió");
        }

        public Task<IReadOnlyDictionary<Guid, Decant.Domain.Reproceso.EstadoDeDocumento>> EstadosAsync(
            CancellationToken ct) => throw new NotSupportedException();

        public Task ActualizarEstadosAsync(IReadOnlyDictionary<Guid, Decant.Domain.Reproceso.EstadoDeDocumento> estados,
            Corrida corrida, CancellationToken ct) => throw new NotSupportedException();
    }
}
