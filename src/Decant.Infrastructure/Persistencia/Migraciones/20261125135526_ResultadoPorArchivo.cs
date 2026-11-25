using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql.EntityFrameworkCore.PostgreSQL.Metadata;

#nullable disable

namespace Decant.Infrastructure.Persistencia.Migraciones
{
    /// <inheritdoc />
    public partial class ResultadoPorArchivo : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "resultado_archivo",
                schema: "decant",
                columns: table => new
                {
                    id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("Npgsql:ValueGenerationStrategy", NpgsqlValueGenerationStrategy.IdentityAlwaysColumn),
                    corrida_id = table.Column<int>(type: "integer", nullable: false),
                    archivo = table.Column<string>(type: "character varying(120)", maxLength: 120, nullable: false),
                    mensajes = table.Column<int>(type: "integer", nullable: false),
                    leidos = table.Column<int>(type: "integer", nullable: false),
                    rechazados = table.Column<int>(type: "integer", nullable: false),
                    repetidos = table.Column<int>(type: "integer", nullable: false),
                    estado = table.Column<string>(type: "character varying(30)", maxLength: 30, nullable: false),
                    detalle = table.Column<string>(type: "character varying(200)", maxLength: 200, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_resultado_archivo", x => x.id);
                    table.ForeignKey(
                        name: "FK_resultado_archivo_corrida_corrida_id",
                        column: x => x.corrida_id,
                        principalSchema: "decant",
                        principalTable: "corrida",
                        principalColumn: "id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_resultado_archivo_corrida_id_archivo",
                schema: "decant",
                table: "resultado_archivo",
                columns: new[] { "corrida_id", "archivo" },
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "resultado_archivo",
                schema: "decant");
        }
    }
}
