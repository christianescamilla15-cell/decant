using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;

namespace Decant.Domain.Tests;

/// <summary>Invariante: reprocesar con reglas nuevas NUNCA quita lo ya resuelto.</summary>
public class ReprocesoTests
{
    private static EstadoDeDocumento E(EstatusOrden estatus, string version = "v1") => new(estatus, 1.5m, version);

    [Fact]
    public void Una_regla_nueva_puede_cambiar_el_veredicto_pero_no_des_resolver()
    {
        var a = Guid.NewGuid();
        var b = Guid.NewGuid();
        var c = Guid.NewGuid();
        var previo = new Dictionary<Guid, EstadoDeDocumento>
        {
            [a] = E(EstatusOrden.Diferencia), [b] = E(EstatusOrden.Conciliada), [c] = E(EstatusOrden.Enviada),
        };
        var nuevo = new Dictionary<Guid, EstadoDeDocumento>
        {
            [a] = E(EstatusOrden.Conciliada, "v2"), // D2 corregido: sigue resuelto, cambia el veredicto
            [b] = E(EstatusOrden.Vencida, "v2"),    // lo regresaría a no resuelto: se conserva
            [c] = E(EstatusOrden.Liquidada, "v2"),  // no estaba resuelto: manda la regla nueva
        };
        var r = Reprocesamiento.Combinar(previo, nuevo);
        Assert.Equal(EstatusOrden.Conciliada, r.Estados[a].Estatus);
        Assert.Equal("v1", r.Estados[b].VersionDeReglas);
        Assert.Equal(EstatusOrden.Conciliada, r.Estados[b].Estatus);
        Assert.Equal(EstatusOrden.Liquidada, r.Estados[c].Estatus);
        Assert.Equal([b], r.Conservados.Select(x => x.Uetr));
    }

    [Fact]
    public void Un_documento_resuelto_que_la_corrida_nueva_no_trae_se_conserva()
    {
        var a = Guid.NewGuid();
        var r = Reprocesamiento.Combinar(new Dictionary<Guid, EstadoDeDocumento> { [a] = E(EstatusOrden.Conciliada) },
            new Dictionary<Guid, EstadoDeDocumento>());
        Assert.Equal(EstatusOrden.Conciliada, r.Estados[a].Estatus);
        Assert.Single(r.Conservados);
    }

    /// <summary>La invariante sobre muchas combinaciones (semilla fija): ningún resuelto deja de estarlo.</summary>
    [Fact]
    public void Ningun_resuelto_deja_de_estarlo_en_ninguna_combinacion()
    {
        var azar = new Random(20231229);
        var estatus = Enum.GetValues<EstatusOrden>();
        for (var ronda = 0; ronda < 200; ronda++)
        {
            var previo = new Dictionary<Guid, EstadoDeDocumento>();
            var nuevo = new Dictionary<Guid, EstadoDeDocumento>();
            for (var i = 0; i < 50; i++)
            {
                var uetr = Guid.NewGuid();
                previo[uetr] = E(estatus[azar.Next(estatus.Length)]);
                if (azar.NextDouble() < 0.9)
                {
                    nuevo[uetr] = E(estatus[azar.Next(estatus.Length)], "v2");
                }
            }

            var r = Reprocesamiento.Combinar(previo, nuevo);
            foreach (var (uetr, antes) in previo.Where(x => Reprocesamiento.EstaResuelto(x.Value.Estatus)))
            {
                Assert.True(Reprocesamiento.EstaResuelto(r.Estados[uetr].Estatus), $"{uetr}: {antes.Estatus}");
            }
        }
    }
}
