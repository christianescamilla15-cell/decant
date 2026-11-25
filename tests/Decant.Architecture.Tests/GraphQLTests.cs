using System.Reflection;
using Decant.Api.GraphQL;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Infrastructure;
using Decant.Infrastructure.Reloj;
using HotChocolate.Execution;
using HotChocolate.Types;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using NetArchTest.Rules;

namespace Decant.Architecture.Tests;

/// <summary>
/// ADR 0017: GraphQL es un ADAPTADOR de entrada más. Sus tipos (HotChocolate y GreenDonut) viven SÓLO en
/// <c>Decant.Api.GraphQL</c>; ni el dominio, ni la aplicación, ni la infraestructura, ni los lotes lo conocen, y el
/// esquema no expone registros de otras capas: su forma se decide en la API.
/// </summary>
public class GraphQLTests
{
    private static readonly Assembly Dominio = typeof(IClock).Assembly;
    private static readonly Assembly Aplicacion = typeof(IUniverso).Assembly;
    private static readonly Assembly Infraestructura = typeof(SystemClock).Assembly;
    private static readonly Assembly Api = typeof(Decant.Api.Presentacion).Assembly;
    private static readonly Assembly Cli = typeof(Decant.Cli.Program).Assembly;
    private static readonly string[] Graphql = ["HotChocolate", "GreenDonut", "ChilliCream"];

    public static TheoryData<string> FueraDeLaApi() =>
        [Dominio.GetName().Name!, Aplicacion.GetName().Name!, Infraestructura.GetName().Name!, Cli.GetName().Name!];

    /// <summary>Ni por tipos (NetArchTest) ni por referencias del ensamblado.</summary>
    [Theory]
    [MemberData(nameof(FueraDeLaApi))]
    public void Fuera_de_la_api_nadie_conoce_graphql(string nombre)
    {
        var ensamblado = new[] { Dominio, Aplicacion, Infraestructura, Cli }.Single(a => a.GetName().Name == nombre);
        var resultado = Types.InAssembly(ensamblado).ShouldNot().HaveDependencyOnAny(Graphql).GetResult();
        Assert.True(resultado.IsSuccessful, string.Join(", ", resultado.FailingTypeNames ?? []));
        Assert.DoesNotContain(ensamblado.GetReferencedAssemblies(),
            r => Graphql.Any(g => r.Name!.StartsWith(g, StringComparison.Ordinal)));
    }

    /// <summary>
    /// Dentro de la API, quien depende de GraphQL está en su espacio de nombres (Program sólo llama a
    /// AgregarGraphQL y MapearGraphQL). La prueba sí ve las dependencias: hay tipos que las tienen.
    /// </summary>
    [Fact]
    public void Dentro_de_la_api_graphql_vive_en_su_espacio_de_nombres()
    {
        var conGraphql = Types.InAssembly(Api).That().HaveDependencyOnAny(Graphql).GetTypes()
            .Where(t => !t.Name.StartsWith('<')).ToList();
        Assert.True(conGraphql.Count >= 5, $"la prueba sí ve los tipos de GraphQL: {conGraphql.Count}");
        Assert.All(conGraphql, t => Assert.StartsWith(typeof(Composicion).Namespace!, t.Namespace!,
            StringComparison.Ordinal));
    }

    /// <summary>
    /// Cada tipo objeto del esquema es un tipo de la API (no un registro de la aplicación expuesto tal cual), salvo
    /// los que la biblioteca genera para la paginación (conexiones, aristas y PageInfo).
    /// </summary>
    [Fact]
    public async Task El_esquema_no_expone_tipos_de_otras_capas()
    {
        var servicios = new ServiceCollection();
        servicios.AgregarDecant("Host=localhost;Database=solo_esquema");
        servicios.AgregarGraphQL(new ConfigurationBuilder().Build());
        await using var proveedor = servicios.BuildServiceProvider();
        var ejecutor = await proveedor.GetRequiredService<IRequestExecutorProvider>().GetExecutorAsync();
        var propios = ejecutor.Schema.Types.OfType<ObjectType>()
            .Where(t => !t.Name.StartsWith("__", StringComparison.Ordinal))
            .Where(t => t.RuntimeType != typeof(object) && t.RuntimeType.Assembly != typeof(ObjectType).Assembly &&
                !t.RuntimeType.Namespace!.StartsWith("HotChocolate", StringComparison.Ordinal))
            .ToList();
        Assert.True(propios.Count >= 5, string.Join(", ", propios.Select(t => t.Name)));
        Assert.All(propios, t => Assert.Equal(Api, t.RuntimeType.Assembly));
        Assert.Null(ejecutor.Schema.MutationType);
    }
}
