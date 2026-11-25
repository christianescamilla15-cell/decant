using Decant.Application.Abstracciones;
using Decant.Application.Carga;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Conciliacion;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;

namespace Decant.Application.Motor;

/// <summary>
/// «Medir el motor»: el replay alimentado SÓLO del universo. Las operaciones se conciertan en el orden en que
/// llegaron (su identidad), y después corre una línea de tiempo con las altas y re-registros de órdenes, las
/// confirmaciones del buzón (llave real: UETR del bloque 3, respaldo :21:) y las noches del job, con el reloj de cada
/// noche inyectado. Con una bandera apagada, su acción sólo se marca.
/// </summary>
public sealed record ReproducirUniverso(OpcionesDelMotor Opciones, string Origen) : ISolicitud<ResumenDeReplay>;

public sealed record ResumenDeReplay(
    int Operaciones, int Documentos, int Registros, int ReRegistros, int Confirmaciones,
    int ConfirmacionesConSegundosDelRespaldo, int Liquidaciones, int Descartadas, int Huerfanas, int Noches,
    int Vencidas, int Conciliadas, int Marcas, DateTimeOffset FinDelUniverso, DateTimeOffset Limite,
    IReadOnlyDictionary<string, int> Errores);

public sealed class ReproducirUniversoManejador(IUniverso universo, IAlmacenTobe almacen, IClock relojDelSistema)
    : IManejador<ReproducirUniverso, ResumenDeReplay>
{
    public const string ReglaVencimiento = "R10-vencimiento";
    public const string ReglaConciliacion = "R07-conciliacion";

    private enum Tipo
    {
        Registro = 1,
        Confirmacion = 2,
        Noche = 3,
    }

    public async Task<ResumenDeReplay> ManejarAsync(ReproducirUniverso solicitud, CancellationToken ct)
    {
        var banderas = solicitud.Opciones.Banderas;
        var inicioCorrida = relojDelSistema.AhoraUtc;
        var errores = new Dictionary<string, int>(StringComparer.Ordinal);
        void Contar(Error e) => errores[e.Codigo] = errores.GetValueOrDefault(e.Codigo) + 1;

        // 1. operaciones, en orden de llegada: el folio FX es el consumible en ese orden
        var consecutivos = new Consecutivos(universo.Series());
        var operaciones = new Dictionary<long, Operacion>();
        var primerDia = DateOnly.MaxValue;
        foreach (var entrada in universo.Operaciones())
        {
            var datos = Entradas.Operacion(entrada);
            if (!datos.EsExito)
            {
                Contar(datos.Error!);
                continue;
            }

            var operacion = Operacion.Concertar(entrada.Id, consecutivos.Tomar(Consecutivos.SerieOperaciones),
                datos.Valor);
            if (!operacion.EsExito)
            {
                Contar(operacion.Error!);
                continue;
            }

            operaciones[entrada.Id] = operacion.Valor;
            var dia = DateOnly.FromDateTime(entrada.FechaOperacionLocal);
            primerDia = dia < primerDia ? dia : primerDia;
        }

        // 2. línea de tiempo
        var eventos = new List<(DateTimeOffset Instante, Tipo Tipo, long Orden, object Carga)>();
        DateTimeOffset? anterior = null;
        var primerRegistro = new Dictionary<string, DateTimeOffset>(StringComparer.Ordinal);
        foreach (var fila in universo.RegistrosDeOrden().OrderBy(f => f.Id))
        {
            var orden = Entradas.Orden(fila, anterior,
                primerRegistro.TryGetValue(fila.Uetr, out var primero) ? primero : null);
            if (!orden.EsExito)
            {
                Contar(orden.Error!);
                continue;
            }

            anterior = orden.Valor.Registro;
            primerRegistro.TryAdd(fila.Uetr, orden.Valor.Registro);
            eventos.Add((orden.Valor.Registro, Tipo.Registro, fila.Id, (fila, orden.Valor.Uetr, orden.Valor.Datos)));
        }

        var segundos = new Dictionary<string, DateTime>(StringComparer.Ordinal);
        foreach (var partida in universo.PartidasDelCorresponsal())
        {
            segundos.TryAdd(Entradas.ReferenciaDelCorresponsal(partida.Referencia), partida.FechaHoraLocal);
        }

        var confirmaciones = 0;
        var conSegundos = 0;
        long secuencia = 0;
        foreach (var mensaje in universo.MensajesDelBuzon())
        {
            var leida = Mt910.Leer(mensaje);
            if (!leida.EsExito)
            {
                Contar(leida.Error!);
                continue;
            }

            var confirmacion = leida.Valor;
            if (segundos.TryGetValue(confirmacion.TrnCorresponsal, out var exacta))
            {
                var precisa = confirmacion.ConSegundos(exacta);
                if (precisa.EsExito)
                {
                    confirmacion = precisa.Valor;
                    conSegundos++;
                }
                else
                {
                    Contar(precisa.Error!);
                }
            }

            confirmaciones++;
            eventos.Add((confirmacion.Instante, Tipo.Confirmacion, secuencia++, confirmacion));
        }

        var fin = eventos.Count == 0 ? DateTimeOffset.MinValue : eventos.Max(e => e.Instante);
        var limite = solicitud.Opciones.Hasta is { } hasta && hasta < fin ? hasta : fin;
        var horario = universo.Horario();
        var noches = 0;
        if (horario.Count > 0 && primerDia != DateOnly.MaxValue)
        {
            var hora = horario[0].Hora;
            for (var dia = primerDia; ; dia = dia.AddDays(1))
            {
                var noche = Zonas.AInstante(dia.ToDateTime(hora), Zonas.CiudadDeMexico);
                if (noche > limite)
                {
                    break;
                }

                eventos.Add((noche, Tipo.Noche, dia.DayNumber, noche));
            }
        }

        eventos.Sort((a, b) =>
        {
            var c = a.Instante.CompareTo(b.Instante);
            if (c == 0)
            {
                c = a.Tipo.CompareTo(b.Tipo);
            }

            return c == 0 ? a.Orden.CompareTo(b.Orden) : c;
        });

        // 3. procesar
        var reloj = new RelojDeReplay(DateTimeOffset.MinValue);
        var documentos = new Dictionary<Guid, OrdenDePago>();
        var enviadas = new HashSet<Guid>();
        var liquidadas = new HashSet<Guid>();
        var evaluadasVencimiento = new HashSet<Guid>();
        var marcadas = new Dictionary<(string Regla, Guid Caso), Marca>();
        var descartadas = new List<LiquidacionDescartada>();
        int registros = 0, reRegistros = 0, liquidaciones = 0, huerfanas = 0, vencidas = 0, conciliadas = 0;
        foreach (var (instante, tipo, _, carga) in eventos)
        {
            if (instante > limite)
            {
                break;
            }

            switch (tipo)
            {
                case Tipo.Registro:
                {
                    var (fila, uetr, datos) = ((RegistroDeEntrada, Guid, DatosDeOrden))carga;
                    if (!operaciones.TryGetValue(fila.OperacionId, out var operacion))
                    {
                        Contar(new Error("orden_sin_operacion", fila.Id.ToString()));
                        continue;
                    }

                    registros++;
                    if (documentos.TryGetValue(uetr, out var existente))
                    {
                        var r = existente.ReRegistrar(datos, operacion.MontoMxn, instante, fila.Id);
                        if (r.EsExito)
                        {
                            reRegistros++;
                        }
                        else
                        {
                            Contar(r.Error!);
                        }
                    }
                    else
                    {
                        var folio = consecutivos.Tomar(Consecutivos.SerieOrdenes);
                        documentos[uetr] = OrdenDePago.Registrar(uetr, folio, fila.OperacionId, datos,
                            operacion.MontoMxn, instante, fila.Id);
                        enviadas.Add(uetr);
                    }

                    break;
                }

                case Tipo.Confirmacion:
                {
                    var c = (ConfirmacionDelCorresponsal)carga;
                    if (!documentos.TryGetValue(c.Uetr, out var documento))
                    {
                        huerfanas++;
                        descartadas.Add(Descartada(c, "sin_documento"));
                        continue;
                    }

                    if (documento.Datos.ReferenciaMt103 != c.ReferenciaMt103)
                    {
                        Contar(new Error("referencia_21_no_cruza", c.Uetr.ToString()));
                    }

                    var r = documento.RegistrarLiquidacion(c);
                    if (r.EsExito)
                    {
                        liquidaciones++;
                        enviadas.Remove(c.Uetr);
                        liquidadas.Add(c.Uetr);
                    }
                    else
                    {
                        descartadas.Add(Descartada(c, $"documento {EstatusDeOrden.Codigo(documento.Estatus)}"));
                    }

                    break;
                }

                case Tipo.Noche:
                {
                    reloj.Ajustar(instante);
                    noches++;
                    var ahora = reloj.AhoraUtc;
                    foreach (var uetr in liquidadas.ToList())
                    {
                        var documento = documentos[uetr];
                        var decision = documento.EvaluarConciliacion()!;
                        if (banderas.ConciliarAutomatico)
                        {
                            documento.Conciliar(decision);
                            liquidadas.Remove(uetr);
                            conciliadas++;
                        }
                        else
                        {
                            // sólo marca: el documento sigue LIQUIDADO; se evalúa una vez y sale del barrido
                            marcadas.TryAdd((ReglaConciliacion, uetr), new Marca(ReglaConciliacion, uetr.ToString(),
                                ahora, decision.Veredicto == EstatusOrden.Conciliada,
                                $"{EstatusDeOrden.Codigo(decision.Veredicto)} horas={decision.Horas} " +
                                $"abonado={decision.Abonado} principal={decision.Principal}"));
                            liquidadas.Remove(uetr);
                        }
                    }

                    foreach (var uetr in enviadas.ToList())
                    {
                        var documento = documentos[uetr];
                        evaluadasVencimiento.Add(uetr);
                        if (!documento.DebeVencer(ahora))
                        {
                            continue;
                        }

                        if (banderas.VencerAutomatico)
                        {
                            documento.Vencer();
                            enviadas.Remove(uetr);
                            vencidas++;
                        }
                        else
                        {
                            // sólo marca: sigue ENVIADA (una confirmación tardía todavía entraría)
                            marcadas.TryAdd((ReglaVencimiento, uetr), new Marca(ReglaVencimiento, uetr.ToString(),
                                ahora, true, $"enviada {documento.Datos.FechaEnvio:o}"));
                            enviadas.Remove(uetr);
                        }
                    }

                    break;
                }
            }
        }

        if (!banderas.VencerAutomatico)
        {
            // ✘: evaluadas al menos una noche y nunca habrían vencido
            foreach (var uetr in evaluadasVencimiento.Where(u => !marcadas.ContainsKey((ReglaVencimiento, u))))
            {
                marcadas[(ReglaVencimiento, uetr)] = new Marca(ReglaVencimiento, uetr.ToString(), limite, false,
                    $"no vencería; quedó {EstatusDeOrden.Codigo(documentos[uetr].Estatus)}");
            }
        }

        var estado = new EstadoTobe(
            new Corrida("replay", VersionDeReglas.Actual, inicioCorrida, limite, banderas, solicitud.Origen),
            universo.Monedas(), consecutivos.Siguientes, operaciones.Values.OrderBy(o => o.Id).ToList(),
            documentos.Values.ToList(), descartadas, marcadas.Values.ToList());
        await almacen.GuardarAsync(estado, ct);
        return new ResumenDeReplay(operaciones.Count, documentos.Count, registros, reRegistros, confirmaciones,
            conSegundos, liquidaciones, descartadas.Count - huerfanas, huerfanas, noches, vencidas, conciliadas,
            marcadas.Count, fin, limite, errores);
    }

    private static LiquidacionDescartada Descartada(ConfirmacionDelCorresponsal c, string motivo) =>
        new(c.Uetr, c.ReferenciaMt103, c.TrnCorresponsal, c.Instante, c.Abono, c.Comision, motivo);
}
