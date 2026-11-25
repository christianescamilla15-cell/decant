using Decant.Application.Abstracciones;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Infrastructure.Archivos;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Reloj;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;

namespace Decant.Infrastructure;

/// <summary>Composición: PostgreSQL, reloj del sistema, mediador y manejadores; universo y oráculo si se dan.</summary>
public static class Servicios
{
    public static IServiceCollection AgregarDecant(this IServiceCollection servicios, string cadenaDeConexion,
        string? carpetaUniverso = null, string? carpetaOraculo = null)
    {
        servicios.AddDbContext<DecantDbContext>(o => o.UseNpgsql(cadenaDeConexion,
            n => n.MigrationsHistoryTable("__historial_migraciones", DecantDbContext.Esquema)));
        servicios.AddScoped<IConsultasTobe, ConsultasEf>();
        servicios.AddScoped<IAlmacenTobe, AlmacenPostgres>();
        servicios.AddSingleton<IClock, SystemClock>();
        servicios.AddScoped<IMediador, Mediador>();
        if (carpetaUniverso is not null)
        {
            servicios.AddSingleton<IUniverso>(new UniversoEnArchivos(carpetaUniverso));
        }

        if (carpetaOraculo is not null)
        {
            servicios.AddSingleton<IOraculoHistorico>(new OraculoEnArchivos(carpetaOraculo));
        }

        var manejadores = typeof(IMediador).Assembly.GetTypes()
            .Where(t => t is { IsClass: true, IsAbstract: false })
            .SelectMany(t => t.GetInterfaces()
                .Where(i => i.IsGenericType && i.GetGenericTypeDefinition() == typeof(IManejador<,>))
                .Select(i => (Servicio: i, Implementacion: t)));
        foreach (var (servicio, implementacion) in manejadores)
        {
            servicios.AddScoped(servicio, implementacion);
        }

        return servicios;
    }
}
