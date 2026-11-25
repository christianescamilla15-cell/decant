using Decant.Domain.Comun;

namespace Decant.Infrastructure.Reloj;

/// <summary>El ÚNICO lugar que lee el reloj del sistema (una prueba de arquitectura lo exige).</summary>
public sealed class SystemClock : IClock
{
    public DateTimeOffset AhoraUtc => DateTimeOffset.UtcNow;
}
