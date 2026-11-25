using System;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace Decant.Infrastructure.Persistencia.Migraciones
{
    /// <inheritdoc />
    public partial class EsquemaInicial : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.EnsureSchema(
                name: "decant");

            migrationBuilder.CreateTable(
                name: "consecutivo",
                schema: "decant",
                columns: table => new
                {
                    serie = table.Column<string>(type: "character varying(10)", maxLength: 10, nullable: false),
                    siguiente = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_consecutivo", x => x.serie);
                });

            migrationBuilder.CreateTable(
                name: "corrida",
                schema: "decant",
                columns: table => new
                {
                    id = table.Column<int>(type: "integer", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityAlwaysColumn),
                    tipo = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    version_reglas = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    inicio = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    hasta = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    banderas = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: true),
                    origen = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_corrida", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "liquidacion_descartada",
                schema: "decant",
                columns: table => new
                {
                    id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityAlwaysColumn),
                    uetr = table.Column<Guid>(type: "uuid", nullable: false),
                    referencia_mt103 = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    trn_corresponsal = table.Column<string>(type: "character varying(35)", maxLength: 35, nullable: false),
                    instante = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    abono = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    comision = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    motivo = table.Column<string>(type: "character varying(60)", maxLength: 60, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_liquidacion_descartada", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "marca",
                schema: "decant",
                columns: table => new
                {
                    id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityAlwaysColumn),
                    regla = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    caso = table.Column<string>(type: "character varying(40)", maxLength: 40, nullable: false),
                    instante = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    cumple = table.Column<bool>(type: "boolean", nullable: false),
                    detalle = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_marca", x => x.id);
                });

            migrationBuilder.CreateTable(
                name: "moneda",
                schema: "decant",
                columns: table => new
                {
                    codigo = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    numerico = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    nombre = table.Column<string>(type: "character varying(60)", maxLength: 60, nullable: false),
                    decimales = table.Column<short>(type: "smallint", nullable: false),
                    activa = table.Column<bool>(type: "boolean", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_moneda", x => x.codigo);
                });

            migrationBuilder.CreateTable(
                name: "operacion",
                schema: "decant",
                columns: table => new
                {
                    id = table.Column<long>(type: "bigint", nullable: false),
                    folio = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    fecha_operacion = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    sucursal = table.Column<string>(type: "character varying(4)", maxLength: 4, nullable: false),
                    canal = table.Column<string>(type: "character varying(10)", maxLength: 10, nullable: false),
                    cliente = table.Column<string>(type: "character varying(120)", maxLength: 120, nullable: false),
                    cuenta_clabe = table.Column<string>(type: "character varying(18)", maxLength: 18, nullable: true),
                    tipo = table.Column<string>(type: "character varying(1)", maxLength: 1, nullable: false),
                    moneda = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    monto_divisa = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    tipo_cambio = table.Column<decimal>(type: "numeric(18,6)", precision: 18, scale: 6, nullable: false),
                    tipo_cambio_referencia = table.Column<decimal>(type: "numeric(18,6)", precision: 18, scale: 6, nullable: true),
                    monto_mxn = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    estatus = table.Column<string>(type: "character varying(12)", maxLength: 12, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_operacion", x => x.id);
                    table.ForeignKey(
                        name: "FK_operacion_moneda_moneda",
                        column: x => x.moneda,
                        principalSchema: "decant",
                        principalTable: "moneda",
                        principalColumn: "codigo",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "orden_pago",
                schema: "decant",
                columns: table => new
                {
                    uetr = table.Column<Guid>(type: "uuid", nullable: false),
                    folio = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false),
                    operacion_id = table.Column<long>(type: "bigint", nullable: false),
                    referencia_mt103 = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    fecha_registro = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    registros = table.Column<int>(type: "integer", nullable: false),
                    fecha_envio = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    fecha_valor = table.Column<DateOnly>(type: "date", nullable: false),
                    bic_corresponsal = table.Column<string>(type: "character varying(11)", maxLength: 11, nullable: false),
                    bic_intermediario = table.Column<string>(type: "character varying(11)", maxLength: 11, nullable: true),
                    beneficiario = table.Column<string>(type: "character varying(120)", maxLength: 120, nullable: false),
                    cuenta_beneficiario = table.Column<string>(type: "character varying(34)", maxLength: 34, nullable: false),
                    moneda = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    monto = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    gastos = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    codigo_proposito = table.Column<string>(type: "character varying(4)", maxLength: 4, nullable: true),
                    estatus = table.Column<string>(type: "character varying(12)", maxLength: 12, nullable: false),
                    horas_liquidacion = table.Column<decimal>(type: "numeric(9,2)", precision: 9, scale: 2, nullable: true),
                    version_reglas = table.Column<string>(type: "character varying(20)", maxLength: 20, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_orden_pago", x => x.uetr);
                    table.ForeignKey(
                        name: "FK_orden_pago_moneda_moneda",
                        column: x => x.moneda,
                        principalSchema: "decant",
                        principalTable: "moneda",
                        principalColumn: "codigo",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_orden_pago_operacion_operacion_id",
                        column: x => x.operacion_id,
                        principalSchema: "decant",
                        principalTable: "operacion",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "partida_cliente",
                schema: "decant",
                columns: table => new
                {
                    uetr = table.Column<Guid>(type: "uuid", nullable: false),
                    renglon = table.Column<short>(type: "smallint", nullable: false),
                    concepto = table.Column<string>(type: "character varying(24)", maxLength: 24, nullable: false),
                    moneda = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    monto = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    fecha_hora = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    referencia = table.Column<string>(type: "character varying(35)", maxLength: 35, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_partida_cliente", x => new { x.uetr, x.renglon });
                    table.ForeignKey(
                        name: "FK_partida_cliente_orden_pago_uetr",
                        column: x => x.uetr,
                        principalSchema: "decant",
                        principalTable: "orden_pago",
                        principalColumn: "uetr",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "partida_corresponsal",
                schema: "decant",
                columns: table => new
                {
                    uetr = table.Column<Guid>(type: "uuid", nullable: false),
                    renglon = table.Column<short>(type: "smallint", nullable: false),
                    concepto = table.Column<string>(type: "character varying(24)", maxLength: 24, nullable: false),
                    moneda = table.Column<string>(type: "character varying(3)", maxLength: 3, nullable: false),
                    monto = table.Column<decimal>(type: "numeric(18,2)", precision: 18, scale: 2, nullable: false),
                    fecha_hora = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    referencia = table.Column<string>(type: "character varying(35)", maxLength: 35, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_partida_corresponsal", x => new { x.uetr, x.renglon });
                    table.ForeignKey(
                        name: "FK_partida_corresponsal_orden_pago_uetr",
                        column: x => x.uetr,
                        principalSchema: "decant",
                        principalTable: "orden_pago",
                        principalColumn: "uetr",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "registro_orden",
                schema: "decant",
                columns: table => new
                {
                    uetr = table.Column<Guid>(type: "uuid", nullable: false),
                    numero = table.Column<int>(type: "integer", nullable: false),
                    fecha_registro = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    id_legado = table.Column<long>(type: "bigint", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_registro_orden", x => new { x.uetr, x.numero });
                    table.ForeignKey(
                        name: "FK_registro_orden_orden_pago_uetr",
                        column: x => x.uetr,
                        principalSchema: "decant",
                        principalTable: "orden_pago",
                        principalColumn: "uetr",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_marca_regla_caso",
                schema: "decant",
                table: "marca",
                columns: new[] { "regla", "caso" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_operacion_fecha_operacion",
                schema: "decant",
                table: "operacion",
                column: "fecha_operacion");

            migrationBuilder.CreateIndex(
                name: "IX_operacion_folio",
                schema: "decant",
                table: "operacion",
                column: "folio",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_operacion_moneda",
                schema: "decant",
                table: "operacion",
                column: "moneda");

            migrationBuilder.CreateIndex(
                name: "IX_orden_pago_fecha_valor",
                schema: "decant",
                table: "orden_pago",
                column: "fecha_valor");

            migrationBuilder.CreateIndex(
                name: "IX_orden_pago_folio",
                schema: "decant",
                table: "orden_pago",
                column: "folio",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_orden_pago_moneda",
                schema: "decant",
                table: "orden_pago",
                column: "moneda");

            migrationBuilder.CreateIndex(
                name: "IX_orden_pago_operacion_id",
                schema: "decant",
                table: "orden_pago",
                column: "operacion_id");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "consecutivo",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "corrida",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "liquidacion_descartada",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "marca",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "partida_cliente",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "partida_corresponsal",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "registro_orden",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "orden_pago",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "operacion",
                schema: "decant");

            migrationBuilder.DropTable(
                name: "moneda",
                schema: "decant");
        }
    }
}
