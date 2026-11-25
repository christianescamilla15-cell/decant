namespace Decant.Domain.Comun;

/// <summary>Error de negocio con un código estable (lo cuenta la paridad) y un mensaje legible.</summary>
public sealed record Error(string Codigo, string Mensaje);

/// <summary>Valor vacío para los casos de uso que sólo dicen si se pudo.</summary>
public readonly record struct Unidad;

/// <summary>Resultado de una regla: el valor o el error, nunca una excepción para un caso de negocio.</summary>
public sealed class Resultado<T>
{
    private readonly T? _valor;

    private Resultado(T valor)
    {
        _valor = valor;
        EsExito = true;
    }

    private Resultado(Error error) => Error = error;

    public bool EsExito { get; }

    public Error? Error { get; }

    public T Valor => EsExito ? _valor! : throw new InvalidOperationException($"sin valor: {Error!.Codigo}");

    public static Resultado<T> Exito(T valor) => new(valor);

    public static Resultado<T> Falla(Error error) => new(error);

    public static implicit operator Resultado<T>(Error error) => Falla(error);

    public static implicit operator Resultado<T>(T valor) => Exito(valor);
}

public static class Resultado
{
    public static Resultado<Unidad> Exito() => Resultado<Unidad>.Exito(default);
}
