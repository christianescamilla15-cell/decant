using Decant.Infrastructure.Persistencia;
using Microsoft.EntityFrameworkCore;
using Testcontainers.PostgreSql;

namespace Decant.Infrastructure.Tests;

/// <summary>PostgreSQL REAL en un contenedor (Testcontainers), con las migraciones aplicadas. La imagen va fija por
/// digest: la misma en local y en el CI.</summary>
public sealed class BaseDePrueba : IAsyncLifetime
{
    public const string Imagen =
        "postgres:16-alpine@sha256:f2f98726820d0342055351c6e9d36e705f5bfffb3dd53ff556325114b08afb6d";

    private readonly PostgreSqlContainer _contenedor = new PostgreSqlBuilder(Imagen)
        .WithDatabase("decant_pruebas")
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
