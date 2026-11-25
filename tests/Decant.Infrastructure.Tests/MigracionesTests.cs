using Decant.Infrastructure.Persistencia;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql;

namespace Decant.Infrastructure.Tests;

/// <summary>
/// La migración N sobre una base en N-1 CON datos (no vacía): lo que había queda idéntico, la tabla nueva sirve para
/// lo que ya estaba (sus llaves foráneas apuntan a corridas viejas) y la reversa a N-1 tampoco pierde nada.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class MigracionesTests(BaseDePrueba baseDePrueba)
{
    private const string Anterior = "20261125042046_EsquemaInicial";

    private static readonly string[] Tablas =
    [
        "moneda", "consecutivo", "operacion", "orden_pago", "registro_orden", "partida_cliente", "partida_corresponsal",
        "liquidacion_descartada", "marca", "corrida",
    ];

    /// <summary>Datos de N-1 escritos con SQL de N-1 (no con el código de hoy, que ya conoce la tabla nueva).</summary>
    private const string DatosDeN1 = """
        INSERT INTO decant.moneda VALUES ('USD', '840', 'Dólar estadounidense', 2, true);
        INSERT INTO decant.consecutivo VALUES ('FX', 2), ('OP', 2);
        INSERT INTO decant.operacion (id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda,
            monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus)
          VALUES (1, 'FX-000000001', '2023-12-01 16:00:00+00', '0001', 'VENTANILLA', 'ARTESANÍAS DEL LAGO, S.C.', NULL,
            'V', 'USD', 1000.00, 19.9392, NULL, 19939.20, 'CONCERTADA');
        INSERT INTO decant.orden_pago (uetr, folio, operacion_id, referencia_mt103, fecha_registro, registros,
            fecha_envio, fecha_valor, bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda,
            monto, gastos, codigo_proposito, estatus, horas_liquidacion, version_reglas)
          VALUES ('3edcbeae-c21e-40f1-b309-430eca67e133', 'OP-000000001', 1, 'BFN231201000001',
            '2023-12-01 16:05:00+00', 1, '2023-12-01 16:05:30+00', '2023-12-04', 'FICTUS33XXX', NULL,
            'Great Plains Seed Co.', '123456789012345678', 'USD', 1000.00, 'OUR', 'SUPP', 'CONCILIADA', 70.17, 'v1');
        INSERT INTO decant.registro_orden VALUES ('3edcbeae-c21e-40f1-b309-430eca67e133', 1, '2023-12-01 16:05:00+00', 10);
        INSERT INTO decant.partida_cliente VALUES ('3edcbeae-c21e-40f1-b309-430eca67e133', 1, 'PRINCIPAL', 'USD',
            1000.00, '2023-12-01 16:05:00+00', 'OP-000000001');
        INSERT INTO decant.partida_corresponsal VALUES ('3edcbeae-c21e-40f1-b309-430eca67e133', 1, 'ABONO', 'USD',
            988.50, '2023-12-04 14:15:42+00', 'FICT000000000001');
        INSERT INTO decant.liquidacion_descartada (uetr, referencia_mt103, trn_corresponsal, instante, abono, comision,
            motivo) VALUES ('8a235e0d-82f7-4b1c-beff-439ed3620b32', 'BFN231201000002', 'FICT000000000002',
            '2023-12-05 14:00:00+00', 1000.00, 0, 'documento VENCIDA');
        INSERT INTO decant.marca (regla, caso, instante, cumple, detalle)
          VALUES ('R10-vencimiento', '8a235e0d-82f7-4b1c-beff-439ed3620b32', '2023-12-05 05:30:00+00', true, 'n-1');
        INSERT INTO decant.corrida (tipo, version_reglas, inicio, hasta, banderas, origen)
          VALUES ('migracion', 'v1', '2026-11-24 18:00:00+00', NULL, NULL, 'respaldo de prueba');
        """;

    [Fact]
    public async Task La_migracion_nueva_sobre_una_base_con_datos_no_pierde_ni_cambia_nada()
    {
        var conexion = new NpgsqlConnectionStringBuilder(baseDePrueba.Conexion)
        {
            Database = "decant_migracion_" + Guid.NewGuid().ToString("N")[..8],
        }.ConnectionString;
        await using var contexto = new DecantDbContext(new DbContextOptionsBuilder<DecantDbContext>()
            .UseNpgsql(conexion, n => n.MigrationsHistoryTable("__historial_migraciones", DecantDbContext.Esquema))
            .Options);
        var migrador = contexto.GetService<IMigrator>();
        await migrador.MigrateAsync(Anterior);
        await contexto.Database.ExecuteSqlRawAsync(DatosDeN1);
        var antes = await Huellas(conexion);

        await migrador.MigrateAsync(); // N
        Assert.Empty(await contexto.Database.GetPendingMigrationsAsync());
        Assert.Equal(antes, await Huellas(conexion));
        // la tabla nueva sirve con lo que ya había: un resultado de archivo para la corrida de N-1
        await contexto.Database.ExecuteSqlRawAsync(
            "INSERT INTO decant.resultado_archivo (corrida_id, archivo, mensajes, leidos, rechazados, repetidos, " +
            "estado, detalle) SELECT id, '20231204.fin', 2, 2, 0, 0, 'leído', '' FROM decant.corrida");
        Assert.Equal(1, await contexto.ResultadosDeArchivo.CountAsync());
        var detalle = await new ConsultasEf(contexto).DetalleAsync(1, default);
        Assert.Equal(("OP-000000001", "CONCILIADA", 70.17m), (detalle!.Orden!.Folio, detalle.Orden.Estatus,
            detalle.Orden.HorasLiquidacion));

        await migrador.MigrateAsync(Anterior); // reversa a N-1: lo de N-1 sigue igual
        Assert.Equal(antes, await Huellas(conexion));
        await contexto.Database.EnsureDeletedAsync();
    }

    /// <summary>md5 de cada tabla, fila por fila en orden de su texto: cualquier cambio de dato o de tipo la mueve.</summary>
    private static async Task<Dictionary<string, string>> Huellas(string conexion)
    {
        await using var c = new NpgsqlConnection(conexion);
        await c.OpenAsync();
        var huellas = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var tabla in Tablas)
        {
            await using var comando = new NpgsqlCommand(
                $"SELECT count(*) || ':' || coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') " +
                $"FROM decant.{tabla} t", c);
            huellas[tabla] = (string)(await comando.ExecuteScalarAsync())!;
        }

        return huellas;
    }
}
