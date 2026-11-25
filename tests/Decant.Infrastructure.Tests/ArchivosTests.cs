using Decant.Infrastructure.Archivos;

namespace Decant.Infrastructure.Tests;

/// <summary>El universo en archivos: encabezados exactos (no entra un resultado) y el buzón en su formato real.</summary>
public sealed class ArchivosTests : IDisposable
{
    private readonly string _carpeta = Directory.CreateTempSubdirectory("decant-universo-").FullName;

    public void Dispose() => Directory.Delete(_carpeta, recursive: true);

    private void Escribir(string archivo, string contenido) =>
        File.WriteAllText(Path.Join(_carpeta, archivo), contenido);

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
    public void El_buzon_se_lee_archivo_por_archivo_en_orden_de_fecha()
    {
        var buzon = Directory.CreateDirectory(Path.Join(_carpeta, "interfaces", "corresponsal")).FullName;
        File.WriteAllText(Path.Join(buzon, "20230602.fin"), "{3:{121:8a235e0d-82f7-4b1c-beff-439ed3620b32}}\n-}\n");
        File.WriteAllText(Path.Join(buzon, "20230601.fin"),
            "{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}\n:20:A\n-}\n${3:{121:8a235e0d-82f7-4b1c-beff-439ed3620b32}}\n:20:B\n-}\n");
        var archivos = new UniversoEnArchivos(_carpeta).ArchivosDelBuzon().ToList();
        Assert.Equal(["20230601.fin", "20230602.fin"], archivos.Select(a => a.Nombre));
        Assert.All(archivos, a => Assert.Null(a.FallaDeLectura));
        Assert.Contains(":20:B", archivos[0].Contenido!, StringComparison.Ordinal);
    }

    /// <summary>Lotes (retro 2): un archivo dañado deja su falla y los demás se leen igual.</summary>
    [Fact]
    public void Un_archivo_danado_deja_su_falla_y_no_detiene_a_los_demas()
    {
        var buzon = Directory.CreateDirectory(Path.Join(_carpeta, "interfaces", "corresponsal")).FullName;
        File.WriteAllText(Path.Join(buzon, "20230601.fin"), "{3:{121:3edcbeae-c21e-40f1-b309-430eca67e133}}\n-}\n");
        File.WriteAllBytes(Path.Join(buzon, "20230602.fin"), [0x3A, 0x32, 0x30, 0x3A, 0xC3, 0x28, 0x0A]);
        File.WriteAllText(Path.Join(buzon, "20230603.fin"), "{3:{121:8a235e0d-82f7-4b1c-beff-439ed3620b32}}\n-}\n");
        var archivos = new UniversoEnArchivos(_carpeta).ArchivosDelBuzon().ToList();
        Assert.Equal(3, archivos.Count);
        Assert.Equal((null, "DecoderFallbackException"), (archivos[1].Contenido, archivos[1].FallaDeLectura));
        Assert.NotNull(archivos[0].Contenido);
        Assert.NotNull(archivos[2].Contenido);
    }

    /// <summary>La carpeta llega de datos: ninguna parte puede sacar la ruta de la raíz (control negativo de lo que
    /// <c>Path.Combine</c> permitía: con una parte absoluta descartaba la raíz sin avisar).</summary>
    [Theory]
    [InlineData("/etc/passwd")]
    [InlineData("../fuera.jsonl")]
    [InlineData("interfaces/../../fuera.jsonl")]
    [InlineData("..")]
    [InlineData("")]
    public void Una_ruta_que_sale_de_la_raiz_se_rechaza(string parte)
    {
        Assert.Throws<ArgumentException>(() => RutaDentro.De(_carpeta, parte));
    }

    [Fact]
    public void Una_ruta_dentro_de_la_raiz_se_arma_con_join()
    {
        Assert.Equal(Path.Join(Path.GetFullPath(_carpeta), "interfaces", "corresponsal"),
            RutaDentro.De(_carpeta, "interfaces", "corresponsal"));
    }

    [Fact]
    public void El_horario_del_job_sale_de_msdb()
    {
        Escribir("job.jsonl", "[\"job\", \"frecuencia\", \"intervalo\", \"hora\"]\n[\"BFN - conciliacion nocturna\", \"4\", \"1\", \"23:30\"]\n");
        Assert.Equal(new TimeOnly(23, 30), Assert.Single(new UniversoEnArchivos(_carpeta).Horario()).Hora);
    }
}
