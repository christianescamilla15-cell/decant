using Decant.Domain.Comun;
using Decant.Domain.Conciliacion;
using Decant.Domain.Pagos;

namespace Decant.Domain.Tests;

/// <summary>R07/R08/R10 con documentos REALES del respaldo (uetr en el comentario).</summary>
public class ConciliacionTests
{
    /// <summary>
    /// T5 se REPLICA (ADR 0006): la hora fija del legado, calculada desde los instantes que guarda el TO-BE. Los tres
    /// casos son documentos reales y el valor esperado es el que el legado GUARDÓ, uno por ventana: en diciembre de
    /// 2023 Nueva York va 1 h adelante; en junio de 2023 y el 20-mar-2022 va 2 h (el legado tiene una hora de más,
    /// y la réplica también).
    /// </summary>
    [Theory]
    [InlineData(2023, 12, 1, 0, 22, 41, 2023, 12, 1, 10, 8, 5, "8.77")]   // 2da9c50b…
    [InlineData(2023, 6, 1, 0, 39, 53, 2023, 6, 1, 8, 30, 42, "6.85")]    // 469818d6…
    [InlineData(2022, 3, 20, 5, 55, 9, 2022, 3, 21, 8, 50, 6, "25.92")]   // 274cab37…
    public void Las_horas_de_liquidacion_replican_la_hora_fija_del_legado(
        int a, int m, int d, int h, int mi, int s, int a2, int m2, int d2, int h2, int mi2, int s2, string horas)
    {
        var envio = Datos.Mx(a, m, d, h, mi, s);
        var ultima = Datos.Ny(a2, m2, d2, h2, mi2, s2);
        Assert.Equal(decimal.Parse(horas), ReglasDeConciliacion.HorasDeLiquidacion(envio, ultima));
    }

    /// <summary>La réplica cuenta fronteras de minuto como DATEDIFF: 10:00:59 → 10:01:00 es un minuto.</summary>
    [Fact]
    public void Las_horas_cuentan_fronteras_de_minuto_como_datediff() =>
        Assert.Equal(0.02m, ReglasDeConciliacion.HorasDeLiquidacion(Datos.Mx(2023, 12, 1, 10, 0, 59),
            Datos.Ny(2023, 12, 1, 11, 1, 0)));

    [Theory]
    [InlineData("1000.00", "1000.00", EstatusOrden.Conciliada)]
    [InlineData("150000.00", "149999.00", EstatusOrden.Diferencia)] // D2: yenes con centavos que nunca se abonan
    public void El_veredicto_compara_lo_abonado_contra_el_principal(string abonado, string principal,
        EstatusOrden esperado) =>
        Assert.Equal(esperado, ReglasDeConciliacion.Veredicto(decimal.Parse(abonado), decimal.Parse(principal)));

    /// <summary>
    /// R10 / T8, caso real 0507f6b1…: enviada el 27-oct-2022 20:24:34 y vencida por el job del 30-oct a las 23:30
    /// (la noche del cambio de horario de México), no por el del 29.
    /// </summary>
    [Fact]
    public void Vence_con_la_noche_del_job_y_el_calendario_local()
    {
        var envio = Datos.Mx(2022, 10, 27, 20, 24, 34);
        Assert.False(ReglasDeVencimiento.Vence(envio, Datos.Mx(2022, 10, 29, 23, 30)));
        Assert.True(ReglasDeVencimiento.Vence(envio, Datos.Mx(2022, 10, 30, 23, 30)));
    }

    [Fact]
    public void Con_el_reloj_de_hoy_vence_todo_lo_enviado_por_eso_el_reloj_entra()
    {
        // lo que pasa si el job del legado corre hoy sobre el respaldo (T8): una orden enviada el día del corte
        var envio = Datos.Mx(2023, 12, 29, 9, 0);
        Assert.False(ReglasDeVencimiento.Vence(envio, Datos.Mx(2023, 12, 29, 23, 30)));
        Assert.True(ReglasDeVencimiento.Vence(envio, new DateTimeOffset(2026, 11, 24, 12, 0, 0, TimeSpan.Zero)));
    }

    /// <summary>Mensaje REAL del buzón (corresponsal/20230601.fin): la llave es la UETR y :21:, no :20:.</summary>
    [Fact]
    public void La_confirmacion_se_lee_por_sus_llaves_reales()
    {
        const string mensaje = "{1:F01FICTMXMMXXX0000000000}{2:O9100802230601FICTUS33XXXX00000000002306010802N}" +
            "{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}{4:\n:20:FICT601153364968\n:21:BFN230530000167\n" +
            ":25:BFNUSDNOSTRO01\n:13D:2306010802-0400\n:32A:230531USD366,57\n:52A:FICTUS33XXX\n-}";
        var c = Mt910.Leer(mensaje).Valor;
        Assert.Equal(Guid.Parse("3edcbeae-c21e-40f1-b309-430eca67e133"), c.Uetr);
        Assert.Equal("BFN230530000167", c.ReferenciaMt103);
        Assert.Equal("FICT601153364968", c.TrnCorresponsal);
        Assert.Equal(new DateTimeOffset(2023, 6, 1, 12, 2, 0, TimeSpan.Zero), c.Instante);
        Assert.Equal((366.57m, 0m, "USD"), (c.Abono, c.Comision, c.Moneda));
        Assert.Equal(new DateOnly(2023, 5, 31), c.FechaValor);
    }

    [Fact]
    public void Los_yenes_enteros_y_la_comision_del_corresponsal_se_leen_del_formato_swift()
    {
        const string mensaje = "{3:{121:95d23926-c141-41ec-8420-f9056a792606}}\n:20:FICT287062128141\n" +
            ":21:BFN231227000069\n:13D:2312290802-0500\n:32A:231227JPY313693,\n:71F:JPY1523,\n-}";
        var c = Mt910.Leer(mensaje).Valor;
        Assert.Equal((313693m, 1523m, "JPY"), (c.Abono, c.Comision, c.Moneda));
    }

    [Theory]
    [InlineData(":20:X\n:21:Y\n:13D:2306010802-0400\n:32A:230531USD1,00", "sin_uetr")]
    [InlineData("{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}\n:20:X\n:13D:2306010802-0400\n:32A:230531USD1,00",
        "campo_faltante")]
    [InlineData("{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}\n:20:X\n:21:Y\n:13D:2306010802\n:32A:230531USD1,00",
        "13D_invalido")]
    public void Un_mensaje_incompleto_es_un_error_con_nombre(string mensaje, string codigo) =>
        Assert.Equal(codigo, Mt910.Leer(mensaje).Error!.Codigo);

    [Fact]
    public void Los_segundos_del_respaldo_solo_valen_en_el_mismo_minuto_del_mensaje()
    {
        var c = new ConfirmacionDelCorresponsal(Guid.NewGuid(), "R", "T", new DateTime(2023, 6, 1, 8, 2, 0),
            TimeSpan.FromHours(-4), new DateOnly(2023, 6, 1), "USD", 1m, 0m);
        Assert.Equal(new DateTime(2023, 6, 1, 8, 2, 37), c.ConSegundos(new DateTime(2023, 6, 1, 8, 2, 37)).Valor.HoraLocal);
        Assert.Equal("hora_fuera_del_minuto", c.ConSegundos(new DateTime(2023, 6, 1, 8, 3, 1)).Error!.Codigo);
    }

    [Fact]
    public void Los_centinelas_se_vuelven_nulos_y_el_relleno_de_char_no_es_dato()
    {
        Assert.Null(Centinelas.Texto("NA"));
        Assert.Null(Centinelas.Texto("NA         ")); // char(11) del BIC intermediario
        Assert.Equal("987650746912048194", Centinelas.Texto("987650746912048194"));
        Assert.Null(Centinelas.Numero(0.000000m));
        Assert.Equal("FICTUS33XXX", CharLegado.SinRelleno("FICTUS33XXX"));
    }
}
