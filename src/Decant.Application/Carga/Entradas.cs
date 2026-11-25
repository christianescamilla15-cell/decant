using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;

namespace Decant.Application.Carga;

/// <summary>
/// Del universo al dominio, con los parches DOCUMENTADOS y nada más (los mismos para la carga histórica y para el
/// replay; la verificación de la migración los cuenta uno por uno):
/// <list type="bullet">
/// <item>T3: centinelas «NA» y 0 → NULL (ADR 0007).</item>
/// <item>T5: hora local → instante; la del legado es de la Ciudad de México (ADR 0008). En la hora repetida, las altas
/// de órdenes se ordenan por llegada.</item>
/// <item>char(n): sin el relleno del tipo.</item>
/// </list>
/// </summary>
public static class Entradas
{
    public static Resultado<DatosDeOperacion> Operacion(OperacionDeEntrada e)
    {
        var tipo = TiposDeOperacion.DesdeCodigo(e.Tipo);
        if (!tipo.EsExito)
        {
            return tipo.Error!;
        }

        return new DatosDeOperacion(
            Zonas.AInstante(e.FechaOperacionLocal, Zonas.CiudadDeMexico),
            CharLegado.SinRelleno(e.Sucursal),
            e.Canal,
            e.Cliente,
            Centinelas.Texto(e.CuentaClabe),
            tipo.Valor,
            CharLegado.SinRelleno(e.Moneda),
            e.MontoDivisa,
            Centinelas.Numero(e.TipoCambioReferencia),
            e.TipoCambioTecleado,
            e.Estatus);
    }

    /// <summary>Un registro de la orden de pago del legado como DOCUMENTO del TO-BE: su UETR, sus datos y el instante
    /// del registro (hora local de la Ciudad de México vuelta instante).</summary>
    /// <param name="e">El registro tal como lo dejó el legado.</param>
    /// <param name="registroAnterior">El instante del alta anterior POR IDENTIDAD (orden de llegada): decide la hora
    /// repetida al terminar el horario de verano.</param>
    /// <param name="primerRegistro">El primer registro del MISMO documento, si ya llegó. El envío se ancla ahí: un
    /// re-registro repite el envío original (días después) y no sirve de piso. Sin él, el piso es este registro.</param>
    public static Resultado<(Guid Uetr, DatosDeOrden Datos, DateTimeOffset Registro)> Orden(
        RegistroDeEntrada e, DateTimeOffset? registroAnterior = null, DateTimeOffset? primerRegistro = null)
    {
        if (!Guid.TryParseExact(CharLegado.SinRelleno(e.Uetr), "D", out var uetr))
        {
            return new Error("uetr_invalida", $"orden {e.Id}: UETR inválida «{e.Uetr}»");
        }

        var gastos = CodigosDeGastos.DesdeCodigo(e.Gastos);
        if (!gastos.EsExito)
        {
            return gastos.Error!;
        }

        var registro = Zonas.AInstanteNoAntesDe(e.FechaRegistroLocal, Zonas.CiudadDeMexico, registroAnterior);
        var datos = new DatosDeOrden(
            e.ReferenciaMt103,
            Zonas.AInstanteNoAntesDe(e.FechaEnvioLocal, Zonas.CiudadDeMexico, primerRegistro ?? registro),
            e.FechaValor,
            CharLegado.SinRelleno(e.BicCorresponsal),
            Centinelas.Texto(CharLegado.SinRelleno(e.BicIntermediario)),
            e.Beneficiario,
            e.CuentaBeneficiario,
            CharLegado.SinRelleno(e.Moneda),
            e.Monto,
            gastos.Valor,
            CharLegado.SinRellenoONulo(e.CodigoProposito));
        return (uetr, datos, registro);
    }

    /// <summary>
    /// Ronda 1 a ciegas, T3: una versión de la interfaz guardó la referencia del corresponsal con su relleno de ancho
    /// fijo. El buzón la trae sin relleno; el TO-BE la recorta (decisión explícita, ADR 0007).
    /// </summary>
    public static string ReferenciaDelCorresponsal(string referencia) => referencia.TrimEnd(' ');
}
