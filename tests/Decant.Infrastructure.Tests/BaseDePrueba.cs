using Decant.Infrastructure.Persistencia;
using Microsoft.EntityFrameworkCore;
using DotNet.Testcontainers.Builders;
using Testcontainers.PostgreSql;

namespace Decant.Infrastructure.Tests;

/// <summary>PostgreSQL REAL en un contenedor (Testcontainers), con las migraciones aplicadas. La imagen va fija por
/// digest (la misma en local y en el CI), con tope de memoria y espera EXPLÍCITA: el puerto dentro del contenedor y
/// una consulta que responde, nunca un retraso fijo.</summary>
public sealed class BaseDePrueba : IAsyncLifetime
{
    public const string Imagen =
        "postgres:16-alpine@sha256:f2f98726820d0342055351c6e9d36e705f5bfffb3dd53ff556325114b08afb6d";

    private const string Base = "decant_pruebas";

    private readonly PostgreSqlContainer _contenedor = new PostgreSqlBuilder(Imagen)
        .WithDatabase(Base)
        .WithCreateParameterModifier(p => p.HostConfig!.Memory = 1L << 30)
        .WithWaitStrategy(Wait.ForUnixContainer()
            .UntilInternalTcpPortIsAvailable(5432)
            .UntilCommandIsCompleted("psql", "-h", "127.0.0.1", "-U", "postgres", "-d", Base, "-tAc", "SELECT 1"))
        .Build();

    public string Conexion => _contenedor.GetConnectionString();

    public DecantDbContext Contexto() =>
        new(new DbContextOptionsBuilder<DecantDbContext>()
            .UseNpgsql(Conexion, n => n.MigrationsHistoryTable("__historial_migraciones", DecantDbContext.Esquema))
            .Options);

    public async Task InitializeAsync()
    {
        await _contenedor.StartAsync();
        await using var contexto = Contexto();
        await contexto.Database.MigrateAsync();
    }

    public Task DisposeAsync() => _contenedor.DisposeAsync().AsTask();
}

[CollectionDefinition(nameof(BaseDePrueba))]
public sealed class ColeccionDeBase : ICollectionFixture<BaseDePrueba>;
