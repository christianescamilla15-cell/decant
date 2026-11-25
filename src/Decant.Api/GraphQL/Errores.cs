using HotChocolate;
using HotChocolate.Execution;
using RequestDelegate = HotChocolate.Execution.RequestDelegate;

namespace Decant.Api.GraphQL;

/// <summary>
/// Contrato de errores de GraphQL, el equivalente del problem+json de REST (ADR 0012 y 0017): TODO error lleva un
/// código en <c>extensions.code</c> y ninguno lleva la excepción, la pila, el SQL ni datos de la conexión. Los códigos
/// propios (en español) son los de las decisiones de este repositorio; el resto conserva el código HCxxxx de la
/// biblioteca (sintaxis y validación del documento contra la especificación).
/// </summary>
public static class CodigosDeError
{
    public const string ArgumentoInvalido = "ARGUMENTO_INVALIDO";
    public const string ProfundidadExcedida = "PROFUNDIDAD_EXCEDIDA";
    public const string CostoExcedido = "COSTO_EXCEDIDO";
    public const string IntrospeccionDeshabilitada = "INTROSPECCION_DESHABILITADA";
    public const string ConsultaInvalida = "CONSULTA_INVALIDA";
    public const string ErrorInterno = "ERROR_INTERNO";

    /// <summary>Un argumento que no cumple su regla: el código, un mensaje sin datos internos y el campo.</summary>
    public static GraphQLException Argumento(string campo, string mensaje) =>
        new(ErrorBuilder.New().SetMessage(mensaje).SetCode(ArgumentoInvalido).SetExtension("campo", campo).Build());
}

/// <summary>
/// Normaliza cada error antes de responder. Como filtro (<see cref="IErrorFilter"/>) ve los errores de la ejecución,
/// con su excepción; como middleware de la petición (<see cref="Composicion"/>) ve además los de análisis y
/// validación del documento, que no pasan por los filtros. Aplicarlo dos veces da lo mismo.
/// </summary>
internal sealed class FiltroDeErrores : IErrorFilter
{
    // Códigos de HotChocolate 16 que este contrato traduce (las pruebas de límites fallan si la biblioteca los cambia).
    private const string CostoHc = "HC0047";
    private const string IntrospeccionHc = "HC0046";
    private const string CicloHc = "HC0087";
    private const string ProfundidadDeSeleccionHc = "HC0138";
    private const string PaginaMaximaHc = "HC0051";
    private const string PaginaMinimaHc = "HC0079";

    public IError OnError(IError error) => Normalizar(error);

    public static IError Normalizar(IError error)
    {
        // Lo inesperado (la base caída, un defecto nuestro): sólo el código y la ruta; el mensaje, la excepción y
        // cualquier extensión se quedan en el servidor.
        if (error.Exception is not null and not GraphQLException)
        {
            return ErrorBuilder.New()
                .SetMessage("Error interno.")
                .SetCode(CodigosDeError.ErrorInterno)
                .SetPath(error.Path)
                .Build();
        }

        var limpio = error.WithException(null).RemoveExtension("stackTrace").RemoveExtension("exception");
        return limpio.Code switch
        {
            CostoHc => limpio.WithCode(CodigosDeError.CostoExcedido),
            IntrospeccionHc => limpio.WithCode(CodigosDeError.IntrospeccionDeshabilitada),
            CicloHc or ProfundidadDeSeleccionHc => limpio.WithCode(CodigosDeError.ProfundidadExcedida),
            PaginaMaximaHc or PaginaMinimaHc =>
                limpio.WithCode(CodigosDeError.ArgumentoInvalido).SetExtension("campo", "first"),
            null when limpio.Extensions?.ContainsKey("allowedExecutionDepth") == true =>
                limpio.WithCode(CodigosDeError.ProfundidadExcedida),
            null => limpio.WithCode(CodigosDeError.ConsultaInvalida),
            _ => limpio,
        };
    }

    /// <summary>El middleware: al volver la petición, normaliza los errores del resultado, vengan de donde vengan.</summary>
    public static RequestDelegate Middleware(RequestDelegate siguiente) => async contexto =>
    {
        await siguiente(contexto);
        if (contexto.Result is OperationResult { Errors.Count: > 0 } resultado)
        {
            resultado.Errors = [.. resultado.Errors.Select(Normalizar)];
        }
    };
}
