using Decant.Domain.Conciliacion;
using Decant.Domain.Pagos;

namespace Decant.Domain.Tests;

/// <summary>Máquina de estados del documento (R06, R07, R09, D3) y transiciones inválidas.</summary>
public class OrdenDePagoTests
{
    private static readonly Guid Uetr = Guid.Parse("e0a842db-5fda-41ca-950d-1f5613b831f5");

    private static OrdenDePago Nueva(decimal monto = 1000.00m, string moneda = "USD") =>
        OrdenDePago.Registrar(Uetr, "OP-000000001", 7, Datos.Orden(monto: monto, moneda: moneda), 20000.00m,
            Datos.Mx(2023, 12, 1, 10, 0), 101);

    private static ConfirmacionDelCorresponsal Confirmacion(decimal abono, decimal comision, DateTime horaNy) =>
        new(Uetr, "BFN231201000001", "FICT000000000001", horaNy, TimeSpan.FromHours(-5), new DateOnly(2023, 12, 1),
            "USD", abono, comision);

    [Fact]
    public void El_alta_deja_el_documento_enviado_con_las_partidas_del_cliente()
    {
        var orden = Nueva();
        Assert.Equal(EstatusOrden.Enviada, orden.Estatus);
        Assert.Equal([Conceptos.Principal, Conceptos.Comision, Conceptos.Iva],
            orden.SolicitadoPorElCliente.Select(p => p.Concepto));
        Assert.Empty(orden.LiquidadoPorElCorresponsal);
        Assert.Single(orden.Registros);
    }

    [Fact]
    public void El_re_registro_conserva_el_folio_y_gana_el_mas_reciente()
    {
        var orden = Nueva();
        var manana = Datos.Mx(2023, 12, 4, 7, 0);
        Assert.True(orden.ReRegistrar(Datos.Orden(), 20000.00m, manana, 102).EsExito);
        Assert.Equal("OP-000000001", orden.Folio);
        Assert.Equal(2, orden.Registros.Count);
        Assert.Equal(manana, orden.FechaRegistro);
        Assert.All(orden.SolicitadoPorElCliente, p => Assert.Equal(manana, p.FechaHora));
    }

    [Fact]
    public void La_liquidacion_registra_lo_que_abono_el_corresponsal_en_la_moneda_de_la_orden()
    {
        var orden = Nueva();
        Assert.True(orden.RegistrarLiquidacion(Confirmacion(988.50m, 11.50m, new DateTime(2023, 12, 1, 14, 0, 0)))
            .EsExito);
        Assert.Equal(EstatusOrden.Liquidada, orden.Estatus);
        Assert.Equal([(Conceptos.Abono, 988.50m), (Conceptos.ComisionCorresponsal, 11.50m)],
            orden.LiquidadoPorElCorresponsal.Select(p => (p.Concepto, p.Monto)));
        Assert.All(orden.LiquidadoPorElCorresponsal, p => Assert.Equal("USD", p.Moneda));
    }

    [Fact]
    public void Sin_comision_del_corresponsal_solo_hay_abono()
    {
        var orden = Nueva();
        orden.RegistrarLiquidacion(Confirmacion(1000.00m, 0m, new DateTime(2023, 12, 1, 14, 0, 0)));
        Assert.Single(orden.LiquidadoPorElCorresponsal);
    }

    [Fact]
    public void Conciliar_cuadra_lo_abonado_con_el_principal_y_calcula_las_horas()
    {
        var orden = Nueva();
        orden.RegistrarLiquidacion(Confirmacion(988.50m, 11.50m, new DateTime(2023, 12, 1, 14, 0, 0)));
        var decision = orden.EvaluarConciliacion()!;
        Assert.Equal(EstatusOrden.Conciliada, decision.Veredicto);
        orden.Conciliar(decision);
        Assert.Equal(EstatusOrden.Conciliada, orden.Estatus);
        Assert.Equal(3.00m, orden.HorasLiquidacion); // 10:00 en la Ciudad de México → 14:00 en Nueva York
    }

    [Fact]
    public void Un_abono_incompleto_sale_en_diferencia()
    {
        var orden = Nueva();
        orden.RegistrarLiquidacion(Confirmacion(980.00m, 11.50m, new DateTime(2023, 12, 1, 14, 0, 0)));
        Assert.Equal(EstatusOrden.Diferencia, orden.EvaluarConciliacion()!.Veredicto);
    }

    /// <summary>D3: la confirmación de un documento vencido se descarta (como el legado), pero con un error visible.</summary>
    [Fact]
    public void La_liquidacion_de_un_documento_vencido_se_descarta_con_error_visible()
    {
        var orden = Nueva();
        Assert.True(orden.DebeVencer(Datos.Mx(2023, 12, 4, 23, 30)));
        orden.Vencer();
        var r = orden.RegistrarLiquidacion(Confirmacion(1000m, 0m, new DateTime(2023, 12, 5, 9, 0, 0)));
        Assert.Equal("liquidacion_descartada", r.Error!.Codigo);
        Assert.Equal(EstatusOrden.Vencida, orden.Estatus);
        Assert.Empty(orden.LiquidadoPorElCorresponsal);
    }

    [Fact]
    public void Re_registrar_un_documento_que_ya_no_esta_enviado_es_un_error_no_un_folio_nuevo()
    {
        var orden = Nueva();
        orden.RegistrarLiquidacion(Confirmacion(1000m, 0m, new DateTime(2023, 12, 1, 14, 0, 0)));
        var r = orden.ReRegistrar(Datos.Orden(), 20000m, Datos.Mx(2023, 12, 4, 7, 0));
        Assert.Equal("reregistro_no_enviada", r.Error!.Codigo);
        Assert.Single(orden.Registros);
    }

    [Fact]
    public void Transiciones_invalidas_no_se_permiten()
    {
        var orden = Nueva();
        Assert.Null(orden.EvaluarConciliacion());
        Assert.Throws<InvalidOperationException>(() =>
            orden.Conciliar(new DecisionDeConciliacion(EstatusOrden.Conciliada, 1m, 1m, 1m)));
        orden.RegistrarLiquidacion(Confirmacion(1000m, 0m, new DateTime(2023, 12, 1, 14, 0, 0)));
        Assert.False(orden.DebeVencer(Datos.Mx(2024, 1, 1, 23, 30)));
        Assert.Throws<InvalidOperationException>(orden.Vencer);
    }

    [Fact]
    public void Rehidratar_exige_al_menos_un_registro() =>
        Assert.Throws<ArgumentException>(() => OrdenDePago.Rehidratar(Uetr, "OP-1", 1, Datos.Orden(),
            EstatusOrden.Enviada, null, [], [], []));
}
