using Decant.Infrastructure.Archivos;

namespace Decant.Infrastructure.Tests;

/// <summary>El universo en archivos: encabezados exactos (no entra un resultado) y el buzón en su formato real.</summary>
public sealed class ArchivosTests : IDisposable
{
    private readonly string _carpeta = Directory.CreateTempSubdirectory("decant-universo-").FullName;

    public void Dispose() => Directory.Delete(_carpeta, recursive: true);

    private void Escribir(string archivo, string contenido) =>
        File.WriteAllText(Path.Combine(_carpeta, archivo), contenido);

    [Fact]
    public void Un_universo_con_una_columna_de_resultado_no_se_lee()
    {
        // monto_mxn es RESULTADO del legado: si el extractor la colara, el replay no debe poder leerla
        Escribir("operacion.jsonl", "[\"id\", \"fecha_operacion\", \"monto_mxn\"]\n[\"1\", \"2023-12-01T10:00:00\", \"1.00\"]\n");
        var error = Assert.Throws<InvalidDataException>(() => new UniversoEnArchivos(_carpeta).Operaciones().ToList());
        Assert.Contains("monto_mxn", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Lee_operaciones_con_centinelas_crudos_y_decimales_exactos()
    {
        Escribir("operacion.jsonl", "[\"" + string.Join("\", \"", UniversoEnArchivos.ColumnasOperacion) + "\"]\n" +
            "[\"53\", \"2021-01-01T10:15:00\", \"0004\", \"VENTANILLA\", \"JOSÉ PÉREZ\", \"NA\", \"C\", \"CHF\", " +
            "\"801.86\", \"0.000000\", \"CONCERTADA\", \"22.282200\"]\n");
        var op = Assert.Single(new UniversoEnArchivos(_carpeta).Operaciones());
        Assert.Equal(("NA", 0m, 22.2822m, 801.86m), (op.CuentaClabe, op.TipoCambioReferencia,
            op.TipoCambioTecleado!.Value, op.MontoDivisa));
        Assert.Equal(new DateTime(2021, 1, 1, 10, 15, 0), op.FechaOperacionLocal);
    }

    [Fact]
    public void El_buzon_se_lee_archivo_por_archivo_y_mensaje_por_mensaje()
    {
        Directory.CreateDirectory(Path.Combine(_carpeta, "interfaces", "corresponsal"));
        File.WriteAllText(Path.Combine(_carpeta, "interfaces", "corresponsal", "20230601.fin"),
            "{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}\n:20:A\n-}\n${3:{121:8a235e0d-82f7-4b1c-beff-439ed3620b32}}\n:20:B\n-}\n");
        var mensajes = new UniversoEnArchivos(_carpeta).MensajesDelBuzon().ToList();
        Assert.Equal(2, mensajes.Count);
        Assert.Contains(":20:B", mensajes[1], StringComparison.Ordinal);
    }

    [Fact]
    public void El_horario_del_job_sale_de_msdb()
    {
        Escribir("job.jsonl", "[\"job\", \"frecuencia\", \"intervalo\", \"hora\"]\n[\"BFN - conciliacion nocturna\", \"4\", \"1\", \"23:30\"]\n");
        Assert.Equal(new TimeOnly(23, 30), Assert.Single(new UniversoEnArchivos(_carpeta).Horario()).Hora);
    }
}
