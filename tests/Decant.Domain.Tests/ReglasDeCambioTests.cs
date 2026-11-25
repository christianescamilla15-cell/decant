using Decant.Domain.Divisas;

namespace Decant.Domain.Tests;

/// <summary>R02/R03 con operaciones REALES del legado (id del respaldo del 29-dic-2023, semilla 20231229).</summary>
public class ReglasDeCambioTests
{
    [Theory]
    [InlineData("V", "27.270833", "27.366281")] // operacion.id 1, GBP, venta
    [InlineData("V", "19.859734", "19.929243")] // operacion.id 2, USD, venta
    [InlineData("C", "19.859734", "19.790225")] // operacion.id 3, USD, compra
    [InlineData("C", "23.910015", "23.826330")] // operacion.id 5, EUR, compra
    public void Sin_tipo_de_cambio_tecleado_aplica_el_margen_a_la_referencia(string tipo, string referencia,
        string esperado)
    {
        var resultado = ReglasDeCambio.TipoDeCambioAplicado(TiposDeOperacion.DesdeCodigo(tipo).Valor,
            decimal.Parse(referencia), null);
        Assert.Equal(decimal.Parse(esperado), resultado.Valor);
    }

    [Theory]
    [InlineData("530.04", "27.366281", "14505.22")]       // operacion.id 1
    [InlineData("737.99", "19.790225", "14604.99")]       // operacion.id 3
    [InlineData("42753.05", "23.826330", "1018648.28")]   // operacion.id 5
    [InlineData("801.86", "22.282200", "17867.20")]       // operacion.id 53 (tecleado por el cajero)
    [InlineData("2858.80", "19.939200", "57002.18")]      // operacion.id 66 (tecleado por el cajero)
    public void Monto_en_pesos_redondea_a_centavos_como_el_legado(string monto, string tc, string pesos) =>
        Assert.Equal(decimal.Parse(pesos), ReglasDeCambio.MontoEnPesos(decimal.Parse(monto), decimal.Parse(tc)));

    [Fact]
    public void El_tipo_de_cambio_tecleado_manda_aunque_haya_referencia()
    {
        // operacion.id 53: el cajero tecleó 22.2822 y la referencia quedó en el centinela 0 (→ NULL)
        Assert.Equal(22.2822m, ReglasDeCambio.TipoDeCambioAplicado(TipoOperacion.Compra, null, 22.2822m).Valor);
    }

    [Fact]
    public void Sin_tecleado_ni_referencia_es_un_error_visible_no_un_cero()
    {
        var resultado = ReglasDeCambio.TipoDeCambioAplicado(TipoOperacion.Venta, null, null);
        Assert.False(resultado.EsExito);
        Assert.Equal("sin_tipo_de_cambio", resultado.Error!.Codigo);
    }

    [Fact]
    public void Los_consecutivos_se_consumen_en_orden_y_con_nueve_digitos()
    {
        var c = new Consecutivos(["FX", "OP"]);
        Assert.Equal("FX-000000001", c.Tomar("FX"));
        Assert.Equal("FX-000000002", c.Tomar("FX"));
        Assert.Equal("OP-000000001", c.Tomar("OP"));
        Assert.Equal(3, c.Siguientes["FX"]);
    }
}
