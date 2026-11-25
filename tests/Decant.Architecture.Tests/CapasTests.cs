using System.Reflection;
using Decant.Application.Motor;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Infrastructure.Reloj;
using Mono.Cecil;
using Mono.Cecil.Cil;
using NetArchTest.Rules;

namespace Decant.Architecture.Tests;

/// <summary>Las capas se hacen cumplir con pruebas, no con un diagrama.</summary>
public class CapasTests
{
    private static readonly Assembly Dominio = typeof(IClock).Assembly;
    private static readonly Assembly Aplicacion = typeof(IUniverso).Assembly;
    private static readonly Assembly Infraestructura = typeof(SystemClock).Assembly;
    private static readonly Assembly Api = typeof(Decant.Api.Presentacion).Assembly;
    private static readonly Assembly Cli = typeof(Decant.Cli.Program).Assembly;

    [Fact]
    public void El_dominio_no_depende_de_ningun_otro_proyecto_ni_paquete()
    {
        var resultado = Types.InAssembly(Dominio).ShouldNot()
            .HaveDependencyOnAny("Decant.Application", "Decant.Infrastructure", "Decant.Api", "Decant.Cli",
                "Microsoft", "Npgsql")
            .GetResult();
        Assert.True(resultado.IsSuccessful, string.Join(", ", resultado.FailingTypeNames ?? []));
    }

    [Fact]
    public void El_dominio_solo_referencia_la_biblioteca_base()
    {
        var referencias = Dominio.GetReferencedAssemblies().Select(a => a.Name!).ToList();
        Assert.All(referencias, r => Assert.True(r.StartsWith("System", StringComparison.Ordinal), r));
    }

    [Fact]
    public void El_dominio_no_hace_entrada_ni_salida()
    {
        var resultado = Types.InAssembly(Dominio).ShouldNot()
            .HaveDependencyOnAny("System.IO", "System.Net", "System.Data", "System.Net.Http").GetResult();
        Assert.True(resultado.IsSuccessful, string.Join(", ", resultado.FailingTypeNames ?? []));
    }

    [Fact]
    public void La_aplicacion_no_conoce_la_infraestructura_ni_la_base()
    {
        var resultado = Types.InAssembly(Aplicacion).ShouldNot()
            .HaveDependencyOnAny("Decant.Infrastructure", "Decant.Api", "Decant.Cli", "Microsoft.EntityFrameworkCore",
                "Npgsql")
            .GetResult();
        Assert.True(resultado.IsSuccessful, string.Join(", ", resultado.FailingTypeNames ?? []));
    }

    [Fact]
    public void La_infraestructura_no_conoce_a_quien_la_compone()
    {
        var resultado = Types.InAssembly(Infraestructura).ShouldNot()
            .HaveDependencyOnAny("Decant.Api", "Decant.Cli").GetResult();
        Assert.True(resultado.IsSuccessful, string.Join(", ", resultado.FailingTypeNames ?? []));
    }

    /// <summary>«Medir el motor» se alimenta SÓLO del universo: el manejador del replay no puede recibir el oráculo.</summary>
    [Fact]
    public void El_replay_no_tiene_acceso_al_oraculo()
    {
        var parametros = typeof(ReproducirUniversoManejador).GetConstructors()
            .SelectMany(c => c.GetParameters()).Select(p => p.ParameterType).ToList();
        Assert.Contains(typeof(IUniverso), parametros);
        Assert.DoesNotContain(typeof(IOraculoHistorico), parametros);
    }

    /// <summary>
    /// T8: nadie lee el reloj del sistema salvo <see cref="SystemClock"/>. NetArchTest ve tipos, no llamadas: aquí se
    /// recorre el IL de TODOS los métodos de los cinco ensamblados buscando las propiedades del reloj.
    /// </summary>
    [Fact]
    public void Nadie_usa_el_reloj_del_sistema_salvo_SystemClock()
    {
        string[] prohibidos =
        [
            "System.DateTime::get_Now", "System.DateTime::get_UtcNow", "System.DateTime::get_Today",
            "System.DateTimeOffset::get_Now", "System.DateTimeOffset::get_UtcNow", "System.TimeProvider::get_System",
        ];
        var hallazgos = new List<string>();
        var permitidos = 0;
        foreach (var ensamblado in new[] { Dominio, Aplicacion, Infraestructura, Api, Cli })
        {
            using var modulo = ModuleDefinition.ReadModule(ensamblado.Location);
            foreach (var tipo in modulo.GetTypes())
            {
                foreach (var metodo in tipo.Methods.Where(m => m.HasBody))
                {
                    foreach (var instruccion in metodo.Body.Instructions)
                    {
                        if (instruccion.OpCode.FlowControl != FlowControl.Call ||
                            instruccion.Operand is not MethodReference llamada)
                        {
                            continue;
                        }

                        var firma = $"{llamada.DeclaringType.FullName}::{llamada.Name}";
                        if (!prohibidos.Contains(firma))
                        {
                            continue;
                        }

                        if (tipo.FullName == typeof(SystemClock).FullName)
                        {
                            permitidos++;
                        }
                        else
                        {
                            hallazgos.Add($"{tipo.FullName}.{metodo.Name} → {firma}");
                        }
                    }
                }
            }
        }

        Assert.Empty(hallazgos);
        Assert.Equal(1, permitidos); // la prueba sí ve llamadas: SystemClock tiene exactamente una
    }
}
