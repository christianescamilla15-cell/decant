using System.Net;
using System.Text.Json;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Tests;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace Decant.Api.Tests;

/// <summary>La API completa (composición, enlace de configuración y JSON) contra PostgreSQL real.</summary>
[Collection(nameof(BaseDePrueba))]
public class ApiTests(BaseDePrueba baseDePrueba) : IAsyncLifetime
{
    /// <summary>La fábrica base: las derivadas (un ambiente, una conexión) cuelgan de ella y se liberan con ella.</summary>
    private readonly WebApplicationFactory<Program> _base = new();
    private WebApplicationFactory<Program> _fabrica = null!;
    private HttpClient _cliente = null!;

    public async Task InitializeAsync()
    {
        await using (var contexto = baseDePrueba.Contexto())
        {
            await new AlmacenPostgres(contexto).GuardarAsync(Escenario.Estado(), default);
        }

        _fabrica = Fabrica("Pruebas");
        _cliente = _fabrica.CreateClient();
    }

    public async Task DisposeAsync()
    {
        _cliente.Dispose();
        await _fabrica.DisposeAsync();
        await _base.DisposeAsync();
    }

    private WebApplicationFactory<Program> Fabrica(string ambiente) =>
        _base.WithWebHostBuilder(b => b
            .UseEnvironment(ambiente)
            .UseSetting("ConnectionStrings:Decant", baseDePrueba.Conexion));

    private async Task<JsonElement> Json(string ruta, HttpClient? cliente = null)
    {
        var respuesta = await (cliente ?? _cliente).GetAsync(ruta);
        Assert.Equal(HttpStatusCode.OK, respuesta.StatusCode);
        return JsonDocument.Parse(await respuesta.Content.ReadAsStringAsync()).RootElement;
    }

    [Fact]
    public async Task Salud_responde() =>
        Assert.Equal("ok", await (await _cliente.GetAsync("/salud")).Content.ReadAsStringAsync());

    /// <summary>T4: las listas llevan el nombre de lo que ve el usuario en la pantalla, con su contenido.</summary>
    [Fact]
    public async Task El_detalle_publica_las_listas_por_lo_que_son_y_cada_hora_en_su_zona()
    {
        var d = await Json("/api/operaciones/1");
        Assert.Equal(JsonValueKind.Null, d.GetProperty("operacion").GetProperty("cuentaClabe").ValueKind);
        Assert.Equal("2023-12-01T10:00:00-06:00", d.GetProperty("operacion").GetProperty("fechaOperacion").GetString());
        Assert.Equal(Escenario.Conciliada.ToString(), d.GetProperty("orden").GetProperty("uetr").GetString());
        var liquidado = d.GetProperty("liquidadoPorElCorresponsal").EnumerateArray().ToList();
        Assert.Equal(["ABONO", "COMISION_CORRESPONSAL"], liquidado.Select(p => p.GetProperty("concepto").GetString()));
        Assert.Equal("2023-12-04T09:15:42-05:00", liquidado[0].GetProperty("fechaHora").GetString());
        Assert.Equal(988.50m, liquidado[0].GetProperty("monto").GetDecimal());
        var solicitado = d.GetProperty("solicitadoPorElCliente").EnumerateArray()
            .Select(p => p.GetProperty("concepto").GetString());
        Assert.Equal(["PRINCIPAL", "COMISION", "IVA", "GASTOS_OUR"], solicitado);
    }

    [Fact]
    public async Task Una_operacion_que_no_existe_es_404() =>
        Assert.Equal(HttpStatusCode.NotFound, (await _cliente.GetAsync("/api/operaciones/999")).StatusCode);

    [Fact]
    public async Task Una_operacion_sin_orden_tiene_orden_nula_y_listas_vacias()
    {
        var d = await Json("/api/operaciones/4");
        Assert.Equal(JsonValueKind.Null, d.GetProperty("orden").ValueKind);
        Assert.Equal(0, d.GetProperty("liquidadoPorElCorresponsal").GetArrayLength());
    }

    [Fact]
    public async Task El_reporte_respeta_su_contrato_de_orden_y_publica_horas_con_desfase()
    {
        var renglones = (await Json("/api/reportes/ordenes?desde=2023-12-01&hasta=2023-12-31")).EnumerateArray().ToList();
        Assert.Equal(["OP-000000002", "OP-000000002", "OP-000000003"],
            renglones.Select(r => r.GetProperty("folio").GetString()));
        Assert.EndsWith("-06:00", renglones[0].GetProperty("fechaEnvio").GetString(), StringComparison.Ordinal);
        Assert.EndsWith("-05:00", renglones[0].GetProperty("fechaPartida").GetString(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("/api/reportes/ordenes?desde=2023-12-31&hasta=2023-12-01")]
    [InlineData("/api/operaciones?fecha=2023-12-01&maximo=0")]
    [InlineData("/api/operaciones?fecha=no-es-fecha")]
    public async Task Los_parametros_invalidos_son_400(string ruta) =>
        Assert.Equal(HttpStatusCode.BadRequest, (await _cliente.GetAsync(ruta)).StatusCode);

    [Fact]
    public async Task La_lista_del_dia_tiene_orden_explicito()
    {
        var lista = (await Json("/api/operaciones?fecha=2023-12-01")).EnumerateArray()
            .Select(o => o.GetProperty("id").GetInt64());
        Assert.Equal([1L, 3L, 2L], lista);
    }

    /// <summary>La configuración del ambiente se enlaza desde appsettings.{ambiente}.json y se valida.</summary>
    [Fact]
    public async Task Cada_ambiente_publica_sus_banderas_y_destinos()
    {
        var pruebas = await Json("/api/configuracion");
        Assert.StartsWith("emulador", pruebas.GetProperty("destinos").GetProperty("corresponsal").GetString(),
            StringComparison.Ordinal);
        Assert.Equal(0, pruebas.GetProperty("errores").GetArrayLength());

        await using var produccion = Fabrica("Produccion");
        var p = await Json("/api/configuracion", produccion.CreateClient());
        Assert.False(p.GetProperty("banderas").GetProperty("vencerAutomatico").GetBoolean()); // sólo marca
        Assert.False(p.GetProperty("banderas").GetProperty("notificarCorresponsal").GetBoolean());
        Assert.Equal(0, p.GetProperty("errores").GetArrayLength());
    }
}
