using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace Decant.Infrastructure.Persistencia;

/// <summary>
/// Esquema del TO-BE en PostgreSQL (esquema <c>decant</c>). Las columnas guardan instantes (<c>timestamptz</c>),
/// NULL donde el legado ponía centinelas y los nombres de lo que SON las listas del detalle.
/// </summary>
public sealed class DecantDbContext(DbContextOptions<DecantDbContext> opciones) : DbContext(opciones)
{
    public const string Esquema = "decant";

    public DbSet<MonedaFila> Monedas => Set<MonedaFila>();
    public DbSet<ConsecutivoFila> Consecutivos => Set<ConsecutivoFila>();
    public DbSet<OperacionFila> Operaciones => Set<OperacionFila>();
    public DbSet<OrdenFila> Ordenes => Set<OrdenFila>();
    public DbSet<RegistroFila> Registros => Set<RegistroFila>();
    public DbSet<PartidaClienteFila> PartidasCliente => Set<PartidaClienteFila>();
    public DbSet<PartidaCorresponsalFila> PartidasCorresponsal => Set<PartidaCorresponsalFila>();
    public DbSet<LiquidacionDescartadaFila> LiquidacionesDescartadas => Set<LiquidacionDescartadaFila>();
    public DbSet<MarcaFila> Marcas => Set<MarcaFila>();
    public DbSet<CorridaFila> Corridas => Set<CorridaFila>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema(Esquema);

        modelBuilder.Entity<MonedaFila>(e =>
        {
            e.ToTable("moneda");
            e.HasKey(x => x.Codigo);
            e.Property(x => x.Codigo).HasColumnName("codigo").HasMaxLength(3);
            e.Property(x => x.Numerico).HasColumnName("numerico").HasMaxLength(3);
            e.Property(x => x.Nombre).HasColumnName("nombre").HasMaxLength(60);
            e.Property(x => x.Decimales).HasColumnName("decimales");
            e.Property(x => x.Activa).HasColumnName("activa");
        });

        modelBuilder.Entity<ConsecutivoFila>(e =>
        {
            e.ToTable("consecutivo");
            e.HasKey(x => x.Serie);
            e.Property(x => x.Serie).HasColumnName("serie").HasMaxLength(10);
            e.Property(x => x.Siguiente).HasColumnName("siguiente");
        });

        modelBuilder.Entity<OperacionFila>(e =>
        {
            e.ToTable("operacion");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").ValueGeneratedNever();
            e.Property(x => x.Folio).HasColumnName("folio").HasMaxLength(20);
            e.HasIndex(x => x.Folio).IsUnique();
            e.Property(x => x.FechaOperacion).HasColumnName("fecha_operacion");
            e.HasIndex(x => x.FechaOperacion);
            e.Property(x => x.Sucursal).HasColumnName("sucursal").HasMaxLength(4);
            e.Property(x => x.Canal).HasColumnName("canal").HasMaxLength(10);
            e.Property(x => x.Cliente).HasColumnName("cliente").HasMaxLength(120);
            e.Property(x => x.CuentaClabe).HasColumnName("cuenta_clabe").HasMaxLength(18);
            e.Property(x => x.Tipo).HasColumnName("tipo").HasMaxLength(1);
            e.Property(x => x.Moneda).HasColumnName("moneda").HasMaxLength(3);
            e.HasOne<MonedaFila>().WithMany().HasForeignKey(x => x.Moneda).OnDelete(DeleteBehavior.Restrict);
            Monto(e.Property(x => x.MontoDivisa).HasColumnName("monto_divisa"));
            e.Property(x => x.TipoCambio).HasColumnName("tipo_cambio").HasPrecision(18, 6);
            e.Property(x => x.TipoCambioReferencia).HasColumnName("tipo_cambio_referencia").HasPrecision(18, 6);
            Monto(e.Property(x => x.MontoMxn).HasColumnName("monto_mxn"));
            e.Property(x => x.Estatus).HasColumnName("estatus").HasMaxLength(12);
        });

        modelBuilder.Entity<OrdenFila>(e =>
        {
            e.ToTable("orden_pago");
            e.HasKey(x => x.Uetr);
            e.Property(x => x.Uetr).HasColumnName("uetr");
            e.Property(x => x.Folio).HasColumnName("folio").HasMaxLength(20);
            e.HasIndex(x => x.Folio).IsUnique();
            e.Property(x => x.OperacionId).HasColumnName("operacion_id");
            e.HasIndex(x => x.OperacionId);
            e.HasOne<OperacionFila>().WithMany().HasForeignKey(x => x.OperacionId).OnDelete(DeleteBehavior.Restrict);
            e.Property(x => x.ReferenciaMt103).HasColumnName("referencia_mt103").HasMaxLength(16);
            e.Property(x => x.FechaRegistro).HasColumnName("fecha_registro");
            e.Property(x => x.Registros).HasColumnName("registros");
            e.Property(x => x.FechaEnvio).HasColumnName("fecha_envio");
            e.Property(x => x.FechaValor).HasColumnName("fecha_valor");
            e.HasIndex(x => x.FechaValor);
            e.Property(x => x.BicCorresponsal).HasColumnName("bic_corresponsal").HasMaxLength(11);
            e.Property(x => x.BicIntermediario).HasColumnName("bic_intermediario").HasMaxLength(11);
            e.Property(x => x.Beneficiario).HasColumnName("beneficiario").HasMaxLength(120);
            e.Property(x => x.CuentaBeneficiario).HasColumnName("cuenta_beneficiario").HasMaxLength(34);
            e.Property(x => x.Moneda).HasColumnName("moneda").HasMaxLength(3);
            e.HasOne<MonedaFila>().WithMany().HasForeignKey(x => x.Moneda).OnDelete(DeleteBehavior.Restrict);
            Monto(e.Property(x => x.Monto).HasColumnName("monto"));
            e.Property(x => x.Gastos).HasColumnName("gastos").HasMaxLength(3);
            e.Property(x => x.CodigoProposito).HasColumnName("codigo_proposito").HasMaxLength(4);
            e.Property(x => x.Estatus).HasColumnName("estatus").HasMaxLength(12);
            e.Property(x => x.HorasLiquidacion).HasColumnName("horas_liquidacion").HasPrecision(9, 2);
            e.Property(x => x.VersionDeReglas).HasColumnName("version_reglas").HasMaxLength(20);
        });

        modelBuilder.Entity<RegistroFila>(e =>
        {
            e.ToTable("registro_orden");
            e.HasKey(x => new { x.Uetr, x.Numero });
            e.Property(x => x.Uetr).HasColumnName("uetr");
            e.Property(x => x.Numero).HasColumnName("numero");
            e.Property(x => x.Instante).HasColumnName("fecha_registro");
            e.Property(x => x.IdLegado).HasColumnName("id_legado");
            e.HasOne<OrdenFila>().WithMany().HasForeignKey(x => x.Uetr).OnDelete(DeleteBehavior.Cascade);
        });

        Partida(modelBuilder.Entity<PartidaClienteFila>(), "partida_cliente",
            x => new { x.Uetr, x.Renglon });
        Partida(modelBuilder.Entity<PartidaCorresponsalFila>(), "partida_corresponsal",
            x => new { x.Uetr, x.Renglon });
        modelBuilder.Entity<PartidaClienteFila>(e =>
        {
            e.Property(x => x.Uetr).HasColumnName("uetr");
            e.Property(x => x.Renglon).HasColumnName("renglon");
            e.Property(x => x.Concepto).HasColumnName("concepto").HasMaxLength(24);
            e.Property(x => x.Moneda).HasColumnName("moneda").HasMaxLength(3);
            Monto(e.Property(x => x.Monto).HasColumnName("monto"));
            e.Property(x => x.FechaHora).HasColumnName("fecha_hora");
            e.Property(x => x.Referencia).HasColumnName("referencia").HasMaxLength(35);
        });
        modelBuilder.Entity<PartidaCorresponsalFila>(e =>
        {
            e.Property(x => x.Uetr).HasColumnName("uetr");
            e.Property(x => x.Renglon).HasColumnName("renglon");
            e.Property(x => x.Concepto).HasColumnName("concepto").HasMaxLength(24);
            e.Property(x => x.Moneda).HasColumnName("moneda").HasMaxLength(3);
            Monto(e.Property(x => x.Monto).HasColumnName("monto"));
            e.Property(x => x.FechaHora).HasColumnName("fecha_hora");
            e.Property(x => x.Referencia).HasColumnName("referencia").HasMaxLength(35);
        });

        modelBuilder.Entity<LiquidacionDescartadaFila>(e =>
        {
            e.ToTable("liquidacion_descartada");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").UseIdentityAlwaysColumn();
            e.Property(x => x.Uetr).HasColumnName("uetr");
            e.Property(x => x.ReferenciaMt103).HasColumnName("referencia_mt103").HasMaxLength(16);
            e.Property(x => x.TrnCorresponsal).HasColumnName("trn_corresponsal").HasMaxLength(35);
            e.Property(x => x.Instante).HasColumnName("instante");
            Monto(e.Property(x => x.Abono).HasColumnName("abono"));
            Monto(e.Property(x => x.Comision).HasColumnName("comision"));
            e.Property(x => x.Motivo).HasColumnName("motivo").HasMaxLength(60);
        });

        modelBuilder.Entity<MarcaFila>(e =>
        {
            e.ToTable("marca");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").UseIdentityAlwaysColumn();
            e.Property(x => x.Regla).HasColumnName("regla").HasMaxLength(40);
            e.Property(x => x.Caso).HasColumnName("caso").HasMaxLength(40);
            e.HasIndex(x => new { x.Regla, x.Caso }).IsUnique();
            e.Property(x => x.Instante).HasColumnName("instante");
            e.Property(x => x.Cumple).HasColumnName("cumple");
            e.Property(x => x.Detalle).HasColumnName("detalle").HasMaxLength(200);
        });

        modelBuilder.Entity<CorridaFila>(e =>
        {
            e.ToTable("corrida");
            e.HasKey(x => x.Id);
            e.Property(x => x.Id).HasColumnName("id").UseIdentityAlwaysColumn();
            e.Property(x => x.Tipo).HasColumnName("tipo").HasMaxLength(20);
            e.Property(x => x.VersionDeReglas).HasColumnName("version_reglas").HasMaxLength(20);
            e.Property(x => x.Inicio).HasColumnName("inicio");
            e.Property(x => x.Hasta).HasColumnName("hasta");
            e.Property(x => x.Banderas).HasColumnName("banderas").HasMaxLength(200);
            e.Property(x => x.Origen).HasColumnName("origen").HasMaxLength(200);
        });
    }

    private static void Monto(PropertyBuilder<decimal> propiedad) => propiedad.HasPrecision(18, 2);

    private static void Partida<T>(EntityTypeBuilder<T> e, string tabla,
        System.Linq.Expressions.Expression<Func<T, object?>> llave)
        where T : class
    {
        e.ToTable(tabla);
        e.HasKey(llave);
        e.HasOne<OrdenFila>().WithMany().HasForeignKey("Uetr").OnDelete(DeleteBehavior.Cascade);
    }
}
