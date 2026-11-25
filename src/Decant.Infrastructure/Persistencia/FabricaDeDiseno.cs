using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace Decant.Infrastructure.Persistencia;

/// <summary>Sólo para <c>dotnet ef migrations add</c>: no se conecta a nada.</summary>
public sealed class FabricaDeDiseno : IDesignTimeDbContextFactory<DecantDbContext>
{
    public DecantDbContext CreateDbContext(string[] args) =>
        new(new DbContextOptionsBuilder<DecantDbContext>()
            .UseNpgsql("Host=localhost;Database=decant_diseno",
                n => n.MigrationsHistoryTable("__historial_migraciones", DecantDbContext.Esquema))
            .Options);
}
