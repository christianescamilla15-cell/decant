using Decant.Application;
using Decant.Application.Puertos;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using NpgsqlTypes;

namespace Decant.Infrastructure.Persistencia;

/// <summary>
/// Escritura en bloque del TO-BE con COPY binario de PostgreSQL, en UNA transacción: se vacían las tablas y se vuelca
/// el estado completo (padres antes que hijos). Los instantes viajan en UTC; los NULL son NULL (no centinelas).
/// </summary>
public sealed class AlmacenPostgres(DecantDbContext contexto) : IAlmacenTobe
{
    private static readonly string[] Tablas =
    [
        "marca", "liquidacion_descartada", "partida_corresponsal", "partida_cliente", "registro_orden",
        "orden_pago", "operacion", "consecutivo", "moneda",
    ];

    public async Task GuardarAsync(EstadoTobe estado, CancellationToken ct)
    {
        var conexion = (NpgsqlConnection)contexto.Database.GetDbConnection();
        await contexto.Database.OpenConnectionAsync(ct);
        try
        {
            await using var transaccion = await conexion.BeginTransactionAsync(ct);
            await using (var vaciar = new NpgsqlCommand(
                "TRUNCATE " + string.Join(", ", Tablas.Select(t => $"{DecantDbContext.Esquema}.{t}")) +
                " RESTART IDENTITY CASCADE", conexion, transaccion))
            {
                await vaciar.ExecuteNonQueryAsync(ct);
            }

            await Copiar(conexion, "moneda (codigo, numerico, nombre, decimales, activa)", estado.Monedas,
                (w, m) =>
                {
                    Txt(w, m.Codigo);
                    Txt(w, m.Numerico);
                    Txt(w, m.Nombre);
                    w.Write((short)m.Decimales, NpgsqlDbType.Smallint);
                    w.Write(m.Activa, NpgsqlDbType.Boolean);
                }, ct);
            await Copiar(conexion, "consecutivo (serie, siguiente)", estado.Consecutivos.ToList(),
                (w, c) =>
                {
                    Txt(w, c.Key);
                    w.Write(c.Value, NpgsqlDbType.Integer);
                }, ct);
            await Copiar(conexion,
                "operacion (id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda, " +
                "monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus)",
                estado.Operaciones, EscribirOperacion, ct);
            await Copiar(conexion,
                "orden_pago (uetr, folio, operacion_id, referencia_mt103, fecha_registro, registros, fecha_envio, " +
                "fecha_valor, bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, " +
                "gastos, codigo_proposito, estatus, horas_liquidacion, version_reglas)",
                estado.Ordenes, (w, o) => EscribirOrden(w, o, estado.Corrida.VersionDeReglas), ct);
            await Copiar(conexion, "registro_orden (uetr, numero, fecha_registro, id_legado)",
                estado.Ordenes.SelectMany(o => o.Registros.Select(r => (o.Uetr, r))).ToList(),
                (w, x) =>
                {
                    w.Write(x.Uetr, NpgsqlDbType.Uuid);
                    w.Write(x.r.Numero, NpgsqlDbType.Integer);
                    Instante(w, x.r.Instante);
                    Largo(w, x.r.IdLegado);
                }, ct);
            await Copiar(conexion, "partida_cliente (uetr, renglon, concepto, moneda, monto, fecha_hora, referencia)",
                estado.Ordenes.SelectMany(o => o.SolicitadoPorElCliente.Select(p => (o.Uetr, p))).ToList(),
                (w, x) => EscribirPartida(w, x.Uetr, x.p), ct);
            await Copiar(conexion,
                "partida_corresponsal (uetr, renglon, concepto, moneda, monto, fecha_hora, referencia)",
                estado.Ordenes.SelectMany(o => o.LiquidadoPorElCorresponsal.Select(p => (o.Uetr, p))).ToList(),
                (w, x) => EscribirPartida(w, x.Uetr, x.p), ct);
            await Copiar(conexion,
                "liquidacion_descartada (uetr, referencia_mt103, trn_corresponsal, instante, abono, comision, motivo)",
                estado.Descartadas,
                (w, d) =>
                {
                    w.Write(d.Uetr, NpgsqlDbType.Uuid);
                    Txt(w, d.ReferenciaMt103);
                    Txt(w, d.TrnCorresponsal);
                    Instante(w, d.Instante);
                    Num(w, d.Abono);
                    Num(w, d.Comision);
                    Txt(w, d.Motivo);
                }, ct);
            await Copiar(conexion, "marca (regla, caso, instante, cumple, detalle)", estado.Marcas,
                (w, m) =>
                {
                    Txt(w, m.Regla);
                    Txt(w, m.Caso);
                    Instante(w, m.Instante);
                    w.Write(m.Cumple, NpgsqlDbType.Boolean);
                    Txt(w, m.Detalle);
                }, ct);
            await InsertarCorrida(conexion, transaccion, estado.Corrida, ct);
            await transaccion.CommitAsync(ct);
        }
        finally
        {
            await contexto.Database.CloseConnectionAsync();
        }
    }

    public async Task<IReadOnlyDictionary<Guid, EstadoDeDocumento>> EstadosAsync(CancellationToken ct)
    {
        var filas = await contexto.Ordenes.AsNoTracking()
            .Select(o => new { o.Uetr, o.Estatus, o.HorasLiquidacion, o.VersionDeReglas })
            .ToListAsync(ct);
        return filas.ToDictionary(
            f => f.Uetr,
            f => new EstadoDeDocumento(EstatusDeOrden.DesdeCodigo(f.Estatus).Valor, f.HorasLiquidacion,
                f.VersionDeReglas));
    }

    public async Task ActualizarEstadosAsync(IReadOnlyDictionary<Guid, EstadoDeDocumento> estados, Corrida corrida,
        CancellationToken ct)
    {
        var conexion = (NpgsqlConnection)contexto.Database.GetDbConnection();
        await contexto.Database.OpenConnectionAsync(ct);
        try
        {
            await using var transaccion = await conexion.BeginTransactionAsync(ct);
            await using (var temporal = new NpgsqlCommand(
                "CREATE TEMP TABLE estado_nuevo (uetr uuid PRIMARY KEY, estatus varchar(12), horas numeric(9,2), " +
                "version varchar(20)) ON COMMIT DROP", conexion, transaccion))
            {
                await temporal.ExecuteNonQueryAsync(ct);
            }

            await using (var escritor = await conexion.BeginBinaryImportAsync(
                "COPY estado_nuevo (uetr, estatus, horas, version) FROM STDIN (FORMAT BINARY)", ct))
            {
                foreach (var (uetr, e) in estados)
                {
                    await escritor.StartRowAsync(ct);
                    escritor.Write(uetr, NpgsqlDbType.Uuid);
                    Txt(escritor, EstatusDeOrden.Codigo(e.Estatus));
                    Num(escritor, e.Horas);
                    Txt(escritor, e.VersionDeReglas);
                }

                await escritor.CompleteAsync(ct);
            }

            await using (var actualizar = new NpgsqlCommand(
                $"UPDATE {DecantDbContext.Esquema}.orden_pago o SET estatus = n.estatus, horas_liquidacion = n.horas, " +
                "version_reglas = n.version FROM estado_nuevo n WHERE n.uetr = o.uetr", conexion, transaccion))
            {
                await actualizar.ExecuteNonQueryAsync(ct);
            }

            await InsertarCorrida(conexion, transaccion, corrida, ct);
            await transaccion.CommitAsync(ct);
        }
        finally
        {
            await contexto.Database.CloseConnectionAsync();
        }
    }

    private static async Task InsertarCorrida(NpgsqlConnection conexion, NpgsqlTransaction transaccion,
        Corrida corrida, CancellationToken ct)
    {
        await using var comando = new NpgsqlCommand(
            $"INSERT INTO {DecantDbContext.Esquema}.corrida (tipo, version_reglas, inicio, hasta, banderas, origen) " +
            "VALUES (@tipo, @version, @inicio, @hasta, @banderas, @origen)", conexion, transaccion);
        comando.Parameters.AddWithValue("tipo", corrida.Tipo);
        comando.Parameters.AddWithValue("version", corrida.VersionDeReglas);
        comando.Parameters.AddWithValue("inicio", corrida.Inicio.ToUniversalTime());
        comando.Parameters.Add(new NpgsqlParameter("hasta", NpgsqlDbType.TimestampTz)
        {
            Value = corrida.Hasta is { } h ? h.ToUniversalTime() : DBNull.Value,
        });
        comando.Parameters.Add(new NpgsqlParameter("banderas", NpgsqlDbType.Varchar)
        {
            Value = corrida.Banderas is { } b ? Describir(b) : DBNull.Value,
        });
        comando.Parameters.AddWithValue("origen", corrida.Origen);
        await comando.ExecuteNonQueryAsync(ct);
    }

    private static string Describir(Banderas b) =>
        $"vencer={b.VencerAutomatico};conciliar={b.ConciliarAutomatico};notificar={b.NotificarCorresponsal}";

    private static async Task Copiar<T>(NpgsqlConnection conexion, string destino, IReadOnlyCollection<T> filas,
        Action<NpgsqlBinaryImporter, T> escribir, CancellationToken ct)
    {
        await using var escritor = await conexion.BeginBinaryImportAsync(
            $"COPY {DecantDbContext.Esquema}.{destino} FROM STDIN (FORMAT BINARY)", ct);
        foreach (var fila in filas)
        {
            await escritor.StartRowAsync(ct);
            escribir(escritor, fila);
        }

        await escritor.CompleteAsync(ct);
    }

    private static void Txt(NpgsqlBinaryImporter w, string? valor)
    {
        if (valor is null)
        {
            w.WriteNull();
        }
        else
        {
            w.Write(valor, NpgsqlDbType.Varchar);
        }
    }

    private static void Num(NpgsqlBinaryImporter w, decimal? valor)
    {
        if (valor is { } v)
        {
            w.Write(v, NpgsqlDbType.Numeric);
        }
        else
        {
            w.WriteNull();
        }
    }

    private static void Largo(NpgsqlBinaryImporter w, long? valor)
    {
        if (valor is { } v)
        {
            w.Write(v, NpgsqlDbType.Bigint);
        }
        else
        {
            w.WriteNull();
        }
    }

    /// <summary>timestamptz exige el instante en UTC (desfase cero).</summary>
    private static void Instante(NpgsqlBinaryImporter w, DateTimeOffset valor) =>
        w.Write(valor.ToUniversalTime(), NpgsqlDbType.TimestampTz);

    private static void EscribirOperacion(NpgsqlBinaryImporter w, Operacion o)
    {
        w.Write(o.Id, NpgsqlDbType.Bigint);
        Txt(w, o.Folio);
        Instante(w, o.Datos.FechaOperacion);
        Txt(w, o.Datos.Sucursal);
        Txt(w, o.Datos.Canal);
        Txt(w, o.Datos.Cliente);
        Txt(w, o.Datos.CuentaClabe);
        Txt(w, TiposDeOperacion.Codigo(o.Datos.Tipo));
        Txt(w, o.Datos.Moneda);
        Num(w, o.Datos.MontoDivisa);
        Num(w, o.TipoDeCambio);
        Num(w, o.Datos.TipoDeCambioReferencia);
        Num(w, o.MontoMxn);
        Txt(w, o.Datos.Estatus);
    }

    private static void EscribirOrden(NpgsqlBinaryImporter w, OrdenDePago o, string version)
    {
        w.Write(o.Uetr, NpgsqlDbType.Uuid);
        Txt(w, o.Folio);
        w.Write(o.OperacionId, NpgsqlDbType.Bigint);
        Txt(w, o.Datos.ReferenciaMt103);
        Instante(w, o.FechaRegistro);
        w.Write(o.Registros.Count, NpgsqlDbType.Integer);
        Instante(w, o.Datos.FechaEnvio);
        w.Write(o.Datos.FechaValor, NpgsqlDbType.Date);
        Txt(w, o.Datos.BicCorresponsal);
        Txt(w, o.Datos.BicIntermediario);
        Txt(w, o.Datos.Beneficiario);
        Txt(w, o.Datos.CuentaBeneficiario);
        Txt(w, o.Datos.Moneda);
        Num(w, o.Datos.Monto);
        Txt(w, CodigosDeGastos.Codigo(o.Datos.Gastos));
        Txt(w, o.Datos.CodigoProposito);
        Txt(w, EstatusDeOrden.Codigo(o.Estatus));
        Num(w, o.HorasLiquidacion);
        Txt(w, version);
    }

    private static void EscribirPartida(NpgsqlBinaryImporter w, Guid uetr, Partida p)
    {
        w.Write(uetr, NpgsqlDbType.Uuid);
        w.Write(p.Renglon, NpgsqlDbType.Smallint);
        Txt(w, p.Concepto);
        Txt(w, p.Moneda);
        Num(w, p.Monto);
        Instante(w, p.FechaHora);
        Txt(w, p.Referencia);
    }
}
