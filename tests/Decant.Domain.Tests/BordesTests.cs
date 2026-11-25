using Decant.Domain.Comun;
using Decant.Domain.Conciliacion;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;

namespace Decant.Domain.Tests;

/// <summary>Bordes que la mutación (Stryker.NET) mostró sin prueba; cada uno con su razón.</summary>
public class BordesTests
{
    /// <summary>sp_conciliar usa «menor que» estricto: lo enviado justo 3 días antes de la noche NO vence esa noche.</summary>
    [Fact]
    public void Lo_enviado_exactamente_tres_dias_antes_de_la_noche_no_vence()
    {
        Assert.False(ReglasDeVencimiento.Vence(Datos.Mx(2023, 12, 1, 23, 30), Datos.Mx(2023, 12, 4, 23, 30)));
        Assert.True(ReglasDeVencimiento.Vence(Datos.Mx(2023, 12, 1, 23, 29, 59), Datos.Mx(2023, 12, 4, 23, 30)));
    }

    /// <summary>La hora que no existe (salto de primavera de 2021) toma el desfase de antes, como el generador.</summary>
    [Fact]
    public void La_hora_que_no_existe_toma_el_desfase_de_antes_del_cambio() =>
        Assert.Equal(new DateTimeOffset(2021, 4, 4, 8, 30, 0, TimeSpan.Zero),
            Zonas.AInstante(new DateTime(2021, 4, 4, 2, 30, 0), Zonas.CiudadDeMexico));

    /// <summary>Dos altas en el MISMO segundo de la primera vuelta: la segunda no salta a la otra vuelta.</summary>
    [Fact]
    public void Dos_altas_en_el_mismo_instante_de_la_hora_repetida_se_quedan_en_la_misma_vuelta()
    {
        var primera = Zonas.AInstante(new DateTime(2021, 10, 31, 1, 41, 59), Zonas.CiudadDeMexico);
        Assert.Equal(primera,
            Zonas.AInstanteNoAntesDe(new DateTime(2021, 10, 31, 1, 41, 59), Zonas.CiudadDeMexico, primera));
    }

    /// <summary>El formato admite desfases positivos (un corresponsal al este de Greenwich).</summary>
    [Fact]
    public void Un_desfase_positivo_en_13d_se_lee_con_su_signo()
    {
        var c = Mt910.Leer("{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}\n:20:X\n:21:Y\n:13D:2306011000+0200\n" +
            ":32A:230601EUR1,00\n-}").Valor;
        Assert.Equal(new DateTimeOffset(2023, 6, 1, 8, 0, 0, TimeSpan.Zero), c.Instante);
    }

    [Fact]
    public void Un_archivo_del_buzon_se_separa_en_sus_mensajes_sin_vacios()
    {
        var mensajes = Mt910.Separar("{3:{121:a}}\n:20:A\n-}\n${3:{121:b}}\n:20:B\n-}\n\n$   ").ToList();
        Assert.Equal(2, mensajes.Count);
    }

    /// <summary>Los códigos son los que guarda el legado: la paridad los compara texto contra texto.</summary>
    [Theory]
    [InlineData(EstatusOrden.Enviada, "ENVIADA")]
    [InlineData(EstatusOrden.Liquidada, "LIQUIDADA")]
    [InlineData(EstatusOrden.Conciliada, "CONCILIADA")]
    [InlineData(EstatusOrden.Diferencia, "DIFERENCIA")]
    [InlineData(EstatusOrden.Vencida, "VENCIDA")]
    public void Los_estatus_van_y_vuelven_con_el_codigo_del_legado(EstatusOrden estatus, string codigo)
    {
        Assert.Equal(codigo, EstatusDeOrden.Codigo(estatus));
        Assert.Equal(estatus, EstatusDeOrden.DesdeCodigo(codigo).Valor);
    }

    [Fact]
    public void Reemplazada_no_es_un_estatus_del_documento() =>
        Assert.Equal("estatus_desconocido", EstatusDeOrden.DesdeCodigo("REEMPLAZADA").Error!.Codigo);

    [Theory]
    [InlineData("OUR", Gastos.Our)]
    [InlineData("SHA", Gastos.Sha)]
    [InlineData("BEN", Gastos.Ben)]
    public void Los_gastos_van_y_vuelven_con_el_codigo_mt103(string codigo, Gastos gastos)
    {
        Assert.Equal(gastos, CodigosDeGastos.DesdeCodigo(codigo).Valor);
        Assert.Equal(codigo, CodigosDeGastos.Codigo(gastos));
        Assert.False(CodigosDeGastos.DesdeCodigo("XXX").EsExito);
    }

    [Fact]
    public void El_tipo_de_operacion_usa_la_letra_del_legado()
    {
        Assert.Equal(("V", "C"), (TiposDeOperacion.Codigo(TipoOperacion.Venta), TiposDeOperacion.Codigo(TipoOperacion.Compra)));
        Assert.Equal(TipoOperacion.Compra, TiposDeOperacion.DesdeCodigo("C").Valor);
        Assert.Equal("tipo_operacion_desconocido", TiposDeOperacion.DesdeCodigo("X").Error!.Codigo);
    }

    [Fact]
    public void Concertar_sin_tipo_de_cambio_es_un_error_y_no_una_operacion_en_cero()
    {
        var datos = new DatosDeOperacion(Datos.Instante, "0001", "VENTANILLA", "X", null, TipoOperacion.Venta, "USD",
            1m, null, null, "CONCERTADA");
        Assert.Equal("sin_tipo_de_cambio", Operacion.Concertar(1, "FX-000000001", datos).Error!.Codigo);
    }

    [Fact]
    public void Los_consecutivos_siguen_desde_lo_que_dejo_el_legado() =>
        Assert.Equal("OP-000150720", new Consecutivos(new Dictionary<string, int> { ["OP"] = 150720 }).Tomar("OP"));

    [Fact]
    public void Un_centinela_numerico_sólo_es_el_cero()
    {
        Assert.Equal(19.859734m, Centinelas.Numero(19.859734m));
        Assert.Null(CharLegado.SinRellenoONulo(null));
    }

    [Fact]
    public void El_valor_de_un_resultado_fallido_no_se_puede_leer() =>
        Assert.Throws<InvalidOperationException>(() => Resultado<int>.Falla(new Error("x", "y")).Valor);

    /// <summary>La carga histórica rehidrata el documento con sus registros y partidas EN ORDEN, sin recalcular.</summary>
    [Fact]
    public void Rehidratar_ordena_registros_y_partidas_y_conserva_el_estado_del_legado()
    {
        var uetr = Guid.NewGuid();
        var r1 = new RegistroDeOrden(1, Datos.Mx(2023, 12, 1, 10, 5), 10);
        var r2 = new RegistroDeOrden(2, Datos.Mx(2023, 12, 4, 7, 0), 12);
        var p1 = new Partida(1, Conceptos.Principal, "USD", 1000m, r2.Instante, "OP-1");
        var p2 = new Partida(2, Conceptos.Comision, "MXN", 150m, r2.Instante, "OP-1");
        var a1 = new Partida(1, Conceptos.Abono, "USD", 988.5m, r2.Instante, "T");
        var a2 = new Partida(2, Conceptos.ComisionCorresponsal, "USD", 11.5m, r2.Instante, "T");
        var orden = OrdenDePago.Rehidratar(uetr, "OP-1", 1, Datos.Orden(), EstatusOrden.Conciliada, 70.17m, [r2, r1],
            [p2, p1], [a2, a1]);
        Assert.Equal((EstatusOrden.Conciliada, 70.17m), (orden.Estatus, orden.HorasLiquidacion));
        Assert.Equal([1, 2], orden.Registros.Select(r => r.Numero));
        Assert.Equal(r2.Instante, orden.FechaRegistro);
        Assert.Equal([(short)1, (short)2], orden.SolicitadoPorElCliente.Select(p => p.Renglon));
        Assert.Equal([(short)1, (short)2], orden.LiquidadoPorElCorresponsal.Select(p => p.Renglon));
    }
}
