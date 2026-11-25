using System.Reflection;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Infrastructure.Persistencia;
using Decant.Infrastructure.Reloj;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Mono.Cecil;
using Mono.Cecil.Cil;
using NetArchTest.Rules;

namespace Decant.Architecture.Tests;

/// <summary>
/// Los tipos de EF no salen de la infraestructura (ni IQueryable, ni el DbContext, ni entidades
/// rastreadas), el reloj tampoco entra por la base (defaults now()) ni por conversiones de zona sueltas, y las fechas
/// de negocio son DateOnly guardadas como <c>date</c>, nunca convertidas a UTC.
/// </summary>
public class PersistenciaYTiempoTests
{
    private static readonly Assembly Dominio = typeof(IClock).Assembly;
    private static readonly Assembly Aplicacion = typeof(IUniverso).Assembly;
    private static readonly Assembly Infraestructura = typeof(SystemClock).Assembly;
    private static readonly Assembly Api = typeof(Decant.Api.Presentacion).Assembly;
    private static readonly Assembly Cli = typeof(Decant.Cli.Program).Assembly;
    private static readonly Assembly[] Todos = [Dominio, Aplicacion, Infraestructura, Api, Cli];

    public static TheoryData<string> FueraDeLaInfraestructura() =>
        [Dominio.GetName().Name!, Aplicacion.GetName().Name!, Api.GetName().Name!, Cli.GetName().Name!];

    /// <summary>Ni EF, ni Npgsql, ni las filas (entidades) de la persistencia: la API y el CLI componen con
    /// <c>Servicios</c> y consumen puertos que devuelven registros de la aplicación.</summary>
    [Theory]
    [MemberData(nameof(FueraDeLaInfraestructura))]
    public void Los_tipos_de_ef_no_salen_de_la_infraestructura(string ensamblado)
    {
        var resultado = Types.InAssembly(Todos.Single(a => a.GetName().Name == ensamblado)).ShouldNot()
            .HaveDependencyOnAny("Microsoft.EntityFrameworkCore", "Npgsql", "Decant.Infrastructure.Persistencia")
            .GetResult();
        Assert.True(resultado.IsSuccessful, string.Join(", ", resultado.FailingTypeNames ?? []));
    }

    /// <summary>Ningún puerto ni tipo público fuera de la persistencia expone IQueryable (consultas abiertas que se
    /// traducirían a SQL lejos de las pruebas contra PostgreSQL).</summary>
    [Fact]
    public void Nadie_expone_iqueryable()
    {
        var hallazgos = Todos
            .SelectMany(a => a.GetTypes())
            .Where(t => t.Namespace != typeof(DecantDbContext).Namespace)
            .SelectMany(t => t.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static |
                BindingFlags.DeclaredOnly).Select(m => (t, m)))
            .Where(x => new[] { x.m.ReturnType }.Concat(x.m.GetParameters().Select(p => p.ParameterType))
                .Any(EsConsultaAbierta))
            .Select(x => $"{x.t.FullName}.{x.m.Name}")
            .ToList();
        Assert.Empty(hallazgos);
    }

    private static bool EsConsultaAbierta(Type tipo) =>
        typeof(IQueryable).IsAssignableFrom(tipo) ||
        (tipo.IsGenericType && tipo.GetGenericArguments().Any(EsConsultaAbierta));

    /// <summary>
    /// Nada se escribe por el rastreador de cambios (las escrituras son COPY): cada DbSet que se lee pasa de inmediato
    /// por AsNoTracking. Se recorre el IL de la infraestructura (incluidas las máquinas de estado de los async).
    /// </summary>
    [Fact]
    public void Toda_lectura_de_un_dbset_es_sin_rastreo()
    {
        var hallazgos = new List<string>();
        var lecturas = 0;
        using var modulo = ModuleDefinition.ReadModule(Infraestructura.Location);
        foreach (var metodo in modulo.GetTypes().SelectMany(t => t.Methods).Where(m => m.HasBody))
        {
            var llamadas = metodo.Body.Instructions
                .Where(i => i.OpCode.FlowControl == FlowControl.Call && i.Operand is MethodReference)
                .Select(i => (MethodReference)i.Operand).ToList();
            for (var k = 0; k < llamadas.Count; k++)
            {
                var llamada = llamadas[k];
                if (llamada.DeclaringType.FullName != typeof(DecantDbContext).FullName ||
                    !llamada.Name.StartsWith("get_", StringComparison.Ordinal) ||
                    !llamada.ReturnType.Name.StartsWith("DbSet", StringComparison.Ordinal) ||
                    metodo.DeclaringType.FullName == typeof(DecantDbContext).FullName)
                {
                    continue;
                }

                lecturas++;
                if (k + 1 >= llamadas.Count || llamadas[k + 1].Name != "AsNoTracking")
                {
                    hallazgos.Add($"{metodo.DeclaringType.FullName}.{metodo.Name} → {llamada.Name}");
                }
            }
        }

        Assert.Empty(hallazgos);
        Assert.True(lecturas >= 8, $"la prueba sí ve las lecturas: {lecturas}");
    }

    /// <summary>
    /// El reloj no entra por la base ni por la máquina: ningún texto SQL (migraciones incluidas) usa now(),
    /// CURRENT_TIMESTAMP y similares ni conversiones AT TIME ZONE, y fuera de <see cref="Zonas"/> nadie convierte
    /// con la zona de la máquina o con TimeZoneInfo.
    /// </summary>
    [Fact]
    public void Ni_defaults_de_reloj_en_la_base_ni_conversiones_de_zona_fuera_de_zonas()
    {
        string[] sqlProhibido =
        [
            "now()", "current_timestamp", "current_date", "current_time", "localtimestamp", "localtime",
            "clock_timestamp", "transaction_timestamp", "statement_timestamp", "at time zone", "timezone(",
        ];
        string[] llamadasProhibidas =
        [
            "System.TimeZoneInfo::get_Local", "System.TimeZoneInfo::ConvertTime",
            "System.TimeZoneInfo::ConvertTimeToUtc", "System.TimeZoneInfo::ConvertTimeFromUtc",
            "System.TimeZoneInfo::ConvertTimeBySystemTimeZoneId", "System.TimeZoneInfo::FindSystemTimeZoneById",
            "System.DateTime::ToLocalTime", "System.DateTime::ToUniversalTime", "System.DateTimeOffset::ToLocalTime",
            "System.DateTimeOffset::get_LocalDateTime",
        ];
        var hallazgos = new List<string>();
        var enZonas = 0;
        var textos = 0;
        foreach (var ensamblado in Todos)
        {
            using var modulo = ModuleDefinition.ReadModule(ensamblado.Location);
            foreach (var tipo in modulo.GetTypes())
            {
                var esZonas = tipo.FullName == typeof(Zonas).FullName;
                foreach (var instruccion in tipo.Methods.Where(m => m.HasBody).SelectMany(m => m.Body.Instructions))
                {
                    if (instruccion.OpCode == OpCodes.Ldstr && instruccion.Operand is string texto)
                    {
                        textos++;
                        hallazgos.AddRange(sqlProhibido
                            .Where(p => texto.Contains(p, StringComparison.OrdinalIgnoreCase))
                            .Select(p => $"{tipo.FullName}: «{p}» en un texto"));
                    }
                    else if (instruccion.OpCode.FlowControl == FlowControl.Call &&
                             instruccion.Operand is MethodReference llamada &&
                             llamadasProhibidas.Contains($"{llamada.DeclaringType.FullName}::{llamada.Name}"))
                    {
                        if (esZonas)
                        {
                            enZonas++;
                        }
                        else
                        {
                            hallazgos.Add($"{tipo.FullName} → {llamada.DeclaringType.Name}.{llamada.Name}");
                        }
                    }
                }
            }
        }

        Assert.Empty(hallazgos);
        Assert.True(enZonas > 0 && textos > 100, $"la prueba sí ve llamadas ({enZonas}) y textos ({textos})");
    }

    private static Microsoft.EntityFrameworkCore.Metadata.IModel Modelo()
    {
        using var contexto = new DecantDbContext(new DbContextOptionsBuilder<DecantDbContext>()
            .UseNpgsql("Host=localhost;Database=solo_modelo").Options);
        return contexto.GetService<Microsoft.EntityFrameworkCore.Metadata.IDesignTimeModel>().Model;
    }

    /// <summary>
    /// En el esquema: ninguna columna tiene default o cálculo en la base; las fechas de negocio (DateOnly) son
    /// <c>date</c> (no se convierten a UTC) y los instantes son <c>timestamptz</c>. No hay columnas DateTime.
    /// </summary>
    [Fact]
    public void El_esquema_no_tiene_defaults_y_separa_fechas_de_negocio_de_instantes()
    {
        var hallazgos = new List<string>();
        var fechas = 0;
        foreach (var propiedad in Modelo().GetEntityTypes().SelectMany(e => e.GetProperties()))
        {
            var nombre = $"{propiedad.DeclaringType.ClrType.Name}.{propiedad.Name}";
            var tipo = Nullable.GetUnderlyingType(propiedad.ClrType) ?? propiedad.ClrType;
            if (propiedad.GetDefaultValueSql() is not null || propiedad.GetComputedColumnSql() is not null)
            {
                hallazgos.Add($"{nombre}: default o cálculo en la base");
            }

            if (tipo == typeof(DateTime))
            {
                hallazgos.Add($"{nombre}: DateTime en el esquema");
            }
            else if (tipo == typeof(DateOnly))
            {
                fechas++;
                if (propiedad.GetColumnType() != "date")
                {
                    hallazgos.Add($"{nombre}: fecha de negocio como {propiedad.GetColumnType()}");
                }
            }
            else if (tipo == typeof(DateTimeOffset) && propiedad.GetColumnType() != "timestamp with time zone")
            {
                hallazgos.Add($"{nombre}: instante como {propiedad.GetColumnType()}");
            }
        }

        Assert.Empty(hallazgos);
        Assert.True(fechas > 0);
    }

    /// <summary>
    /// En el código: DateTime sólo para la hora LOCAL cruda que llega del legado (su nombre termina en «Local»), antes
    /// de que <see cref="Zonas"/> la vuelva instante. Toda fecha valor es DateOnly en todas las capas.
    /// </summary>
    [Fact]
    public void Datetime_solo_para_horas_locales_crudas_y_la_fecha_valor_es_dateonly()
    {
        var miembros = Todos.SelectMany(a => a.GetTypes())
            .Where(t => !t.Name.StartsWith('<'))
            .SelectMany(t => t.GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)
                .Select(p => (Tipo: t, Nombre: p.Name, Clr: Nullable.GetUnderlyingType(p.PropertyType) ?? p.PropertyType)))
            .ToList();
        var hallazgos = miembros
            .Where(m => (m.Clr == typeof(DateTime) && !m.Nombre.EndsWith("Local", StringComparison.Ordinal)) ||
                        (m.Nombre == "FechaValor" && m.Clr != typeof(DateOnly)))
            .Select(m => $"{m.Tipo.FullName}.{m.Nombre}: {m.Clr.Name}")
            .ToList();
        Assert.Empty(hallazgos);
        Assert.True(miembros.Count(m => m.Nombre == "FechaValor") >= 4);
    }
}
