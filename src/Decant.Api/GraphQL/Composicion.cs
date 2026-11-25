using HotChocolate.AspNetCore;
using HotChocolate.Execution;
using HotChocolate.Fetching;

namespace Decant.Api.GraphQL;

/// <summary>Lo que se configura por ambiente (sección <c>GraphQL</c> de los appsettings).</summary>
/// <param name="Introspeccion">
/// Si el esquema se puede pedir en vivo (<c>__schema</c>, <c>__type</c>). Apagada por omisión y en producción: el
/// contrato publicado es <c>src/Decant.Api/GraphQL/esquema.graphql</c>, versionado en el repo.
/// </param>
public sealed record OpcionesGraphQL(bool Introspeccion)
{
    public const string Seccion = "GraphQL";

    /// <summary>Ausente = apagada; un valor que no es booleano detiene el arranque (como las banderas).</summary>
    public static OpcionesGraphQL Leer(IConfiguration configuracion)
    {
        var clave = $"{Seccion}:{nameof(Introspeccion)}";
        var texto = configuracion[clave];
        if (texto is null)
        {
            return new OpcionesGraphQL(false);
        }

        return bool.TryParse(texto, out var valor)
            ? new OpcionesGraphQL(valor)
            : throw new InvalidOperationException($"{clave} no es booleano: «{texto}»");
    }
}

/// <summary>
/// La API GraphQL de SÓLO LECTURA (ADR 0017): esquema, cargadores, límites y contrato de errores. Todo lo de GraphQL
/// vive en este espacio de nombres; el resto de la API sólo llama a <see cref="AgregarGraphQL"/> y
/// <see cref="MapearGraphQL"/> (lo hace cumplir <c>tests/Decant.Architecture.Tests</c>).
/// </summary>
public static class Composicion
{
    public const string Ruta = "/graphql";

    /// <summary>
    /// Profundidad máxima del documento (la hoja cuenta). La consulta legítima más honda, una página con la orden, la
    /// vuelta a su operación y sus partidas (<c>operaciones.edges.node.orden.operacion.orden.liquidado.monto</c>),
    /// mide 8; el esquema tiene un ciclo (orden ↔ operación) y sin este tope no tendría fondo.
    /// </summary>
    public const int ProfundidadMaxima = 8;

    /// <summary>
    /// Topes del análisis de costo (la especificación de costo de IBM que implementa la biblioteca, estático: se
    /// calcula ANTES de ejecutar). La consulta legítima más cara, una página de 100 operaciones con su orden, sus dos
    /// listas de partidas y la vuelta a la operación, cuesta 4,112 en campos y 1,203 en tipos (medido con
    /// <c>GraphQL-Cost: validate</c> en las pruebas de límites): caben dos así en una petición, no tres.
    /// </summary>
    public const double CostoMaximoDeCampos = 10_000;

    public const double CostoMaximoDeTipos = 10_000;

    /// <summary>Una consulta de lectura cabe de sobra en 64 KiB; más es un documento hecho para gastar al parser.</summary>
    public const int TamanoMaximoDePeticion = 64 * 1024;

    public static IServiceCollection AgregarGraphQL(this IServiceCollection servicios, IConfiguration configuracion)
    {
        var opciones = OpcionesGraphQL.Leer(configuracion);
        servicios.AddSingleton(opciones);
        servicios.AddGraphQLServer(maxAllowedRequestSize: TamanoMaximoDePeticion)
            .AddQueryType<Consulta>()
            .AddDataLoader<OperacionesPorId>()
            .AddDataLoader<OrdenesPorOperacion>()
            .AddDataLoader<SolicitadoPorElCliente>()
            .AddDataLoader<LiquidadoPorElCorresponsal>()
            // Un lote se despacha cuando deja de recibir llaves (1 ms quieto), nunca por antigüedad. Con las opciones
            // por omisión (despacho forzado a los 50 ms) una corrida bajo carga partió un lote en dos: 6 consultas en
            // vez de 5. Una API de lectura prefiere una consulta por lote a un milisegundo menos de latencia.
            .AddDefaultBatchDispatcher(new BatchDispatcherOptions { MaxBatchWaitTimeUs = 0, BatchSettleTimeUs = 1_000 })
            .AddErrorFilter<FiltroDeErrores>()
            // Primero de todos: también normaliza los errores de análisis y validación (no pasan por los filtros).
            .UseRequest(FiltroDeErrores.Middleware, key: "ContratoDeErrores",
                before: WellKnownRequestMiddleware.InstrumentationMiddleware)
            .UseDefaultPipeline()
            // La introspección tiene sus propios topes (profundidad de ofType y de listas); sólo se cuenta la nuestra.
            .AddMaxExecutionDepthRule(ProfundidadMaxima, skipIntrospectionFields: true)
            .DisableIntrospection(!opciones.Introspeccion)
            .ModifyCostOptions(o =>
            {
                o.EnforceCostLimits = true;
                o.MaxFieldCost = CostoMaximoDeCampos;
                o.MaxTypeCost = CostoMaximoDeTipos;
            })
            .ModifyRequestOptions(o => o.IncludeExceptionDetails = false)
            .ModifyServerOptions(o =>
            {
                // Sólo POST con JSON: nada de GET (ni consultas en la URL), del método QUERY, de multipart ni de
                // lotes de operaciones o de variables; sin la herramienta Nitro ni la descarga del SDL (el contrato
                // publicado es el archivo versionado; la introspección queda para los ambientes que la encienden).
                o.EnableGetRequests = false;
                o.EnableQueryRequests = false;
                o.EnableMultipartRequests = false;
                o.Batching = AllowedBatching.None;
                o.EnableSchemaRequests = false;
                o.Tool.Enable = false;
            });
        return servicios;
    }

    public static IEndpointConventionBuilder MapearGraphQL(this IEndpointRouteBuilder rutas) =>
        rutas.MapGraphQLHttp(Ruta);
}
