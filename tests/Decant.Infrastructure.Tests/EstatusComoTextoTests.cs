using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;
using Decant.Infrastructure.Persistencia;
using Npgsql;

namespace Decant.Infrastructure.Tests;

/// <summary>
/// El estatus del documento viaja como TEXTO (el código del legado) y no como entero: cada valor del enum hace el
/// viaje completo a PostgreSQL y de regreso, cabe en su columna y un texto desconocido en la base no se convierte
/// en silencio en otro estatus.
/// </summary>
[Collection(nameof(BaseDePrueba))]
public class EstatusComoTextoTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    private static readonly Guid[] Documentos = [Escenario.Conciliada, Escenario.Vencida, Escenario.MismaFecha];

    public async Task InitializeAsync()
    {
        await using var contexto = baseDePrueba.Contexto();
        await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Estado(), default);
    }

    public Task DisposeAsync() => Task.CompletedTask;

    [Fact]
    public async Task Cada_estatus_va_y_vuelve_como_su_codigo_de_texto()
    {
        var valores = Enum.GetValues<EstatusOrden>();
        for (var ronda = 0; ronda < valores.Length; ronda++)
        {
            var estados = Documentos.Select((uetr, i) => (uetr, valores[(ronda + i) % valores.Length]))
                .ToDictionary(x => x.uetr, x => new EstadoDeDocumento(x.Item2, null, "v-texto"));
            await using (var contexto = baseDePrueba.Contexto())
            {
                await new AlmacenPostgres(contexto).ActualizarEstadosAsync(estados,
                    Escenario.Estado().Corrida with { Tipo = "reproceso" }, default);
            }

            await using (var contexto = baseDePrueba.Contexto())
            {
                var leidos = await new AlmacenPostgres(contexto).EstadosAsync(default);
                Assert.All(Documentos, d => Assert.Equal(estados[d].Estatus, leidos[d].Estatus));
            }

            await using var conexion = new NpgsqlConnection(baseDePrueba.Conexion);
            await conexion.OpenAsync();
            foreach (var uetr in Documentos)
            {
                await using var comando = new NpgsqlCommand(
                    "SELECT estatus FROM decant.orden_pago WHERE uetr = @u", conexion);
                comando.Parameters.AddWithValue("u", uetr);
                Assert.Equal(EstatusDeOrden.Codigo(estados[uetr].Estatus), (string)(await comando.ExecuteScalarAsync())!);
            }
        }
    }

    [Fact]
    public async Task Un_texto_desconocido_en_la_base_no_se_lee_como_otro_estatus()
    {
        await using (var conexion = new NpgsqlConnection(baseDePrueba.Conexion))
        {
            await conexion.OpenAsync();
            await using var comando = new NpgsqlCommand(
                "UPDATE decant.orden_pago SET estatus = 'REEMPLAZADA' WHERE uetr = @u", conexion);
            comando.Parameters.AddWithValue("u", Escenario.Vencida);
            Assert.Equal(1, await comando.ExecuteNonQueryAsync());
        }

        await using var contexto = baseDePrueba.Contexto();
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            new AlmacenPostgres(contexto).EstadosAsync(default));
        Assert.Contains("estatus_desconocido", error.Message, StringComparison.Ordinal);
    }
}
