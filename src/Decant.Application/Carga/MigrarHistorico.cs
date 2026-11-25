using Decant.Application.Abstracciones;
using Decant.Application.Puertos;
using Decant.Domain.Comun;
using Decant.Domain.Divisas;
using Decant.Domain.Pagos;
using Decant.Domain.Reproceso;

namespace Decant.Application.Carga;

/// <summary>Carga histórica: el legado tal cual al TO-BE, por columna (entradas del universo, resultados del
/// oráculo), con los parches documentados y sin recalcular nada.</summary>
public sealed record MigrarHistorico(string Origen) : ISolicitud<ResumenDeCarga>;

public sealed record ResumenDeCarga(
    int Monedas, int Operaciones, int Documentos, int Registros, int PartidasDelCliente,
    int PartidasDelCorresponsal, int PartidasDelClienteDeRegistrosReemplazados, IReadOnlyDictionary<string, int> Errores);

public sealed class MigrarHistoricoManejador(
    IUniverso universo, IOraculoHistorico oraculo, IAlmacenTobe almacen, IClock reloj)
    : IManejador<MigrarHistorico, ResumenDeCarga>
{
    private const string Reemplazada = "REEMPLAZADA";

    public async Task<ResumenDeCarga> ManejarAsync(MigrarHistorico solicitud, CancellationToken ct)
    {
        var errores = new Dictionary<string, int>(StringComparer.Ordinal);
        void Contar(Error e) => errores[e.Codigo] = errores.GetValueOrDefault(e.Codigo) + 1;

        var inicio = reloj.AhoraUtc;
        var calculadas = oraculo.Operaciones().ToDictionary(o => o.Id);
        var operaciones = new List<Operacion>();
        foreach (var entrada in universo.Operaciones())
        {
            var datos = Entradas.Operacion(entrada);
            if (!datos.EsExito || !calculadas.TryGetValue(entrada.Id, out var calculada))
            {
                Contar(datos.Error ?? new Error("operacion_sin_resultado", entrada.Id.ToString()));
                continue;
            }

            // tipo_cambio es MIXTA: del universo si el cajero lo tecleó; del oráculo si lo calculó el legado
            var tipoDeCambio = entrada.TipoCambioTecleado ?? calculada.TipoCambioCalculado;
            if (tipoDeCambio is null)
            {
                Contar(new Error("tipo_de_cambio_sin_origen", entrada.Id.ToString()));
                continue;
            }

            operaciones.Add(new Operacion(entrada.Id, calculada.Folio, datos.Valor, tipoDeCambio.Value,
                calculada.MontoMxn));
        }

        var filas = universo.RegistrosDeOrden().ToList();
        var resultados = oraculo.Ordenes().ToDictionary(o => o.Id);
        var uetrPorFila = new Dictionary<long, Guid>();
        var porDocumento = new Dictionary<Guid, List<(RegistroDeEntrada Fila, DatosDeOrden Datos, DateTimeOffset Registro)>>();
        DateTimeOffset? anterior = null;
        var primerRegistro = new Dictionary<string, DateTimeOffset>(StringComparer.Ordinal);
        var registroPorFila = new Dictionary<long, DateTimeOffset>();
        foreach (var fila in filas.OrderBy(f => f.Id))
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
            registroPorFila[fila.Id] = orden.Valor.Registro;
            uetrPorFila[fila.Id] = orden.Valor.Uetr;
            if (!porDocumento.TryGetValue(orden.Valor.Uetr, out var lista))
            {
                porDocumento[orden.Valor.Uetr] = lista = [];
            }

            lista.Add((fila, orden.Valor.Datos, orden.Valor.Registro));
        }

        var clientePorFila = oraculo.PartidasDelCliente().GroupBy(p => p.OrdenId)
            .ToDictionary(g => g.Key, g => g.ToList());
        var entradasCorresponsal = universo.PartidasDelCorresponsal().ToDictionary(p => p.Id);
        var corresponsalPorFila = new Dictionary<long, List<Partida>>();
        foreach (var calculada in oraculo.PartidasDelCorresponsal())
        {
            if (!entradasCorresponsal.TryGetValue(calculada.Id, out var entrada))
            {
                Contar(new Error("partida_corresponsal_sin_entrada", calculada.Id.ToString()));
                continue;
            }

            if (!corresponsalPorFila.TryGetValue(calculada.OrdenId, out var lista))
            {
                corresponsalPorFila[calculada.OrdenId] = lista = [];
            }

            lista.Add(new Partida(calculada.Renglon, calculada.Concepto, CharLegado.SinRelleno(calculada.Moneda),
                entrada.Monto, Zonas.AInstante(entrada.FechaHoraLocal, Zonas.NuevaYork),
                Entradas.ReferenciaDelCorresponsal(entrada.Referencia)));
        }

        var documentos = new List<OrdenDePago>();
        var registros = 0;
        var partidasCliente = 0;
        var partidasCorresponsal = 0;
        var deReemplazadas = 0;
        foreach (var (uetr, lista) in porDocumento)
        {
            var vigentes = lista.Where(x => resultados[x.Fila.Id].Estatus != Reemplazada).ToList();
            if (vigentes.Count != 1)
            {
                Contar(new Error("documento_sin_una_fila_vigente", uetr.ToString()));
                continue;
            }

            var vigente = vigentes[0];
            var resultado = resultados[vigente.Fila.Id];
            if (lista.Any(x => resultados[x.Fila.Id].Folio != resultado.Folio))
            {
                Contar(new Error("reregistro_con_otro_folio", uetr.ToString()));
            }

            var estatus = EstatusDeOrden.DesdeCodigo(resultado.Estatus);
            if (!estatus.EsExito)
            {
                Contar(estatus.Error!);
                continue;
            }

            var historia = lista.OrderBy(x => x.Fila.Id)
                .Select((x, i) => new RegistroDeOrden(i + 1, x.Registro, x.Fila.Id)).ToList();
            // la hora de la partida es la del registro de su fila (sp_registrar_orden): se toma ESE instante
            var cliente = clientePorFila.GetValueOrDefault(vigente.Fila.Id, [])
                .Select(p => new Partida(p.Renglon, p.Concepto, CharLegado.SinRelleno(p.Moneda), p.Monto,
                    p.FechaHoraLocal == vigente.Fila.FechaRegistroLocal
                        ? registroPorFila[vigente.Fila.Id]
                        : Zonas.AInstante(p.FechaHoraLocal, Zonas.CiudadDeMexico), p.Referencia)).ToList();
            var corresponsal = corresponsalPorFila.GetValueOrDefault(vigente.Fila.Id, []);
            if (lista.Any(x => x.Fila.Id != vigente.Fila.Id && corresponsalPorFila.ContainsKey(x.Fila.Id)))
            {
                Contar(new Error("liquidacion_en_fila_reemplazada", uetr.ToString()));
            }

            deReemplazadas += lista.Where(x => x.Fila.Id != vigente.Fila.Id)
                .Sum(x => clientePorFila.GetValueOrDefault(x.Fila.Id, []).Count);
            documentos.Add(OrdenDePago.Rehidratar(uetr, resultado.Folio, vigente.Fila.OperacionId, vigente.Datos,
                estatus.Valor, resultado.Horas, historia, cliente, corresponsal));
            registros += historia.Count;
            partidasCliente += cliente.Count;
            partidasCorresponsal += corresponsal.Count;
        }

        var monedas = universo.Monedas();
        var estado = new EstadoTobe(
            new Corrida("migracion", VersionDeReglas.Actual, inicio, null, null, solicitud.Origen),
            monedas, oraculo.Consecutivos(), operaciones, documentos, [], []);
        await almacen.GuardarAsync(estado, ct);
        return new ResumenDeCarga(monedas.Count, operaciones.Count, documentos.Count, registros, partidasCliente,
            partidasCorresponsal, deReemplazadas, errores);
    }
}
