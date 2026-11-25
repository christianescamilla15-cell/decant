using Decant.Domain.Pagos;

namespace Decant.Domain.Tests;

/// <summary>R05 / D1 con comisiones REALES del respaldo.</summary>
public class ReglasDeCargosTests
{
    [Theory]
    [InlineData("71214.42", "178.03")]   // redondeando serían 178.04: el legado TRUNCA (D1)
    [InlineData("149627.96", "374.06")]  // redondeando serían 374.07
    [InlineData("53573.19", "150.00")]   // 133.93 < mínimo
    public void La_comision_trunca_y_tiene_minimo_como_el_legado(string pesos, string comision) =>
        Assert.Equal(decimal.Parse(comision), ReglasDeCargos.Comision(decimal.Parse(pesos)));

    [Theory]
    [InlineData("1758.99", "281.44")]
    [InlineData("1771.24", "283.40")]
    public void El_iva_redondea_a_centavos(string comision, string iva) =>
        Assert.Equal(decimal.Parse(iva), ReglasDeCargos.Iva(decimal.Parse(comision)));

    [Theory]
    [InlineData(Gastos.Our, 4)]
    [InlineData(Gastos.Sha, 3)]
    [InlineData(Gastos.Ben, 3)]
    public void Gastos_our_agrega_25_dolares_y_las_demas_no(Gastos gastos, int renglones)
    {
        var datos = Datos.Orden(gastos: gastos);
        var partidas = ReglasDeCargos.SolicitadoPorElCliente(datos, 71214.42m, Datos.Instante, "OP-000000001");
        Assert.Equal(renglones, partidas.Count);
        Assert.Equal(datos.Monto, partidas.Single(p => p.Concepto == Conceptos.Principal).Monto);
        if (gastos == Gastos.Our)
        {
            Assert.Equal(("USD", 25.00m), (partidas[3].Moneda, partidas[3].Monto));
        }
    }
}
