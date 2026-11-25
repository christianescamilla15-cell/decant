using Decant.Domain.Comun;
using Decant.Domain.Conciliacion;

namespace Decant.Domain.Pagos;

/// <summary>
/// Orden de pago como DOCUMENTO: una por UETR (llave natural). El legado la da de alta otra vez cada mañana mientras
/// el corresponsal no la liquida (T9: otra fila, otro id, mismo folio); aquí cada alta es un
/// <see cref="RegistroDeOrden"/> y gana el más reciente.
/// </summary>
public sealed class OrdenDePago
{
    private readonly List<RegistroDeOrden> _registros = [];
    private readonly List<Partida> _corresponsal = [];

    private OrdenDePago(Guid uetr, string folio, long operacionId, DatosDeOrden datos)
    {
        Uetr = uetr;
        Folio = folio;
        OperacionId = operacionId;
        Datos = datos;
    }

    public Guid Uetr { get; }

    public string Folio { get; }

    public long OperacionId { get; }

    public DatosDeOrden Datos { get; private set; }

    public EstatusOrden Estatus { get; private set; }

    public decimal? HorasLiquidacion { get; private set; }

    public IReadOnlyList<RegistroDeOrden> Registros => _registros;

    public DateTimeOffset FechaRegistro => _registros[^1].Instante;

    /// <summary>«Solicitado por el cliente» (en el legado, la tabla mal llamada <c>partida_liquidada</c>).</summary>
    public IReadOnlyList<Partida> SolicitadoPorElCliente { get; private set; } = [];

    /// <summary>«Liquidado por el corresponsal» (en el legado, la tabla mal llamada <c>partida_solicitada</c>).</summary>
    public IReadOnlyList<Partida> LiquidadoPorElCorresponsal => _corresponsal;

    /// <summary>Primera alta del documento: estatus ENVIADA y las partidas del cliente (R05).</summary>
    public static OrdenDePago Registrar(
        Guid uetr, string folio, long operacionId, DatosDeOrden datos, decimal montoMxnOperacion,
        DateTimeOffset instante, long? idLegado = null)
    {
        var orden = new OrdenDePago(uetr, folio, operacionId, datos) { Estatus = EstatusOrden.Enviada };
        orden._registros.Add(new RegistroDeOrden(1, instante, idLegado));
        orden.SolicitadoPorElCliente = ReglasDeCargos.SolicitadoPorElCliente(datos, montoMxnOperacion, instante, folio);
        return orden;
    }

    /// <summary>
    /// R09. Re-registro del mismo documento: conserva el folio, gana el registro más reciente y las partidas del
    /// cliente llevan su fecha. Sólo si el documento sigue ENVIADO; el legado, en ese caso, daría otro folio al mismo
    /// UETR (un documento nuevo con la misma llave natural): el TO-BE lo rechaza con un error visible (0 casos medidos).
    /// </summary>
    public Resultado<Unidad> ReRegistrar(
        DatosDeOrden datos, decimal montoMxnOperacion, DateTimeOffset instante, long? idLegado = null)
    {
        if (Estatus != EstatusOrden.Enviada)
        {
            return new Error("reregistro_no_enviada",
                $"{Uetr}: re-registro de un documento {EstatusDeOrden.Codigo(Estatus)}");
        }

        Datos = datos;
        _registros.Add(new RegistroDeOrden(_registros.Count + 1, instante, idLegado));
        SolicitadoPorElCliente = ReglasDeCargos.SolicitadoPorElCliente(datos, montoMxnOperacion, instante, Folio);
        return Resultado.Exito();
    }

    /// <summary>
    /// R06 / D3. La confirmación del corresponsal sólo se registra si el documento sigue ENVIADO. Si el job ya lo
    /// venció, el legado la descarta EN SILENCIO; el TO-BE la descarta igual (se replica mientras negocio no decida)
    /// pero devuelve el error para que quede visible.
    /// </summary>
    public Resultado<Unidad> RegistrarLiquidacion(ConfirmacionDelCorresponsal confirmacion)
    {
        if (Estatus != EstatusOrden.Enviada)
        {
            return new Error("liquidacion_descartada",
                $"{Uetr}: confirmación de un documento {EstatusDeOrden.Codigo(Estatus)}");
        }

        var referencia = confirmacion.TrnCorresponsal;
        var instante = confirmacion.Instante;
        _corresponsal.Add(new Partida(1, Conceptos.Abono, Datos.Moneda, confirmacion.Abono, instante, referencia));
        if (confirmacion.Comision > 0)
        {
            // la moneda es la de la ORDEN, no la del mensaje (sp_registrar_liquidacion)
            _corresponsal.Add(new Partida(2, Conceptos.ComisionCorresponsal, Datos.Moneda, confirmacion.Comision,
                instante, referencia));
        }

        Estatus = EstatusOrden.Liquidada;
        return Resultado.Exito();
    }

    /// <summary>Lo que decidiría el job sobre este documento, sin cambiar nada (para actuar o sólo marcar).</summary>
    public DecisionDeConciliacion? EvaluarConciliacion()
    {
        if (Estatus != EstatusOrden.Liquidada)
        {
            return null;
        }

        var abonado = _corresponsal.Sum(p => p.Monto);
        var principal = SolicitadoPorElCliente.Where(p => p.Concepto == Conceptos.Principal).Sum(p => p.Monto);
        var ultima = _corresponsal.Max(p => p.FechaHora);
        return new DecisionDeConciliacion(
            ReglasDeConciliacion.Veredicto(abonado, principal),
            ReglasDeConciliacion.HorasDeLiquidacion(Datos.FechaEnvio, ultima),
            abonado,
            principal);
    }

    public void Conciliar(DecisionDeConciliacion decision)
    {
        if (Estatus != EstatusOrden.Liquidada)
        {
            throw new InvalidOperationException($"{Uetr}: sólo se concilia lo LIQUIDADO");
        }

        Estatus = decision.Veredicto;
        HorasLiquidacion = decision.Horas;
    }

    /// <summary>¿La vencería el job de esta noche? (R10, con el reloj que entra.)</summary>
    public bool DebeVencer(DateTimeOffset noche) =>
        Estatus == EstatusOrden.Enviada && ReglasDeVencimiento.Vence(Datos.FechaEnvio, noche);

    public void Vencer()
    {
        if (Estatus != EstatusOrden.Enviada)
        {
            throw new InvalidOperationException($"{Uetr}: sólo vence lo ENVIADO");
        }

        Estatus = EstatusOrden.Vencida;
    }

    /// <summary>
    /// Carga histórica: el documento tal como lo dejó el legado (estatus y horas que YA calculó), sin recalcular
    /// nada. Lo que se valida aquí es la forma, no el negocio: al menos un registro y partidas numeradas.
    /// </summary>
    public static OrdenDePago Rehidratar(
        Guid uetr, string folio, long operacionId, DatosDeOrden datos, EstatusOrden estatus, decimal? horas,
        IEnumerable<RegistroDeOrden> registros, IEnumerable<Partida> solicitado, IEnumerable<Partida> liquidado)
    {
        var orden = new OrdenDePago(uetr, folio, operacionId, datos) { Estatus = estatus, HorasLiquidacion = horas };
        orden._registros.AddRange(registros.OrderBy(r => r.Numero));
        if (orden._registros.Count == 0)
        {
            throw new ArgumentException($"{uetr}: un documento sin registros", nameof(registros));
        }

        orden.SolicitadoPorElCliente = solicitado.OrderBy(p => p.Renglon).ToList();
        orden._corresponsal.AddRange(liquidado.OrderBy(p => p.Renglon));
        return orden;
    }
}
