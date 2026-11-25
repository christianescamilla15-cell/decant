using Decant.Domain.Comun;

namespace Decant.Application.Motor;

/// <summary>El reloj del replay: marca la hora de cada noche del job, la que el legado leía de GETDATE() (T8).</summary>
public sealed class RelojDeReplay(DateTimeOffset inicio) : IClock
{
    public DateTimeOffset AhoraUtc { get; private set; } = inicio;

    public void Ajustar(DateTimeOffset instante)
    {
        if (instante < AhoraUtc)
        {
            throw new InvalidOperationException($"el reloj del replay no regresa: {instante:o} < {AhoraUtc:o}");
        }

        AhoraUtc = instante;
    }
}
