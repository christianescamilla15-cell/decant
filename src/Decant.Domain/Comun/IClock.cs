namespace Decant.Domain.Comun;

/// <summary>
/// El reloj entra a las reglas, nunca se lee del sistema: el legado usaba GETDATE() dentro de su regla de
/// vencimiento (T8) y re-correrlo hoy vence todo. Una prueba de arquitectura prohíbe DateTime.Now fuera del reloj
/// del sistema.
/// </summary>
public interface IClock
{
    DateTimeOffset AhoraUtc { get; }
}
