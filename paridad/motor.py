"""Ejercicio 2, «MEDIR EL MOTOR»: el replay del TO-BE, alimentado SÓLO del universo hasta el corte medido, contra lo
que el legado calculó (el respaldo restaurado). Publica el % de coincidencia POR REGLA y arbitra cada diferencia.

Además:
- **Hipótesis y controles:** para las reglas con alternativa, el % de cada hipótesis sobre los mismos datos (la que no
  se eligió también se publica) y un control al azar (una regla inventada con la misma distribución).
- **Sólo marca:** con la bandera de una acción apagada, el motor deja ✔/✘ por caso; aquí se cruzan sus marcas con
  lo que el legado hizo, noche por noche, según su bitácora.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path

from legado.generador.zonas import CDMX, NUEVA_YORK, a_utc
from paridad import arbitraje
from paridad.formato import texto
from paridad.mapeo import aplicar, pisos_por_llegada
from universo.interfaces import leer_buzon

# ── lo que se compara ─────────────────────────────────────────────────────────────────────────────────────────

L_OPERACION = 'SELECT id, folio, tipo_cambio_referencia, tipo_cambio, monto_mxn FROM dbo.operacion'
T_OPERACION = 'SELECT id, folio, tipo_cambio, monto_mxn FROM decant.operacion'
L_ORDEN = ('SELECT id, uetr, folio, estatus, horas_liquidacion, fecha_registro, fecha_envio FROM dbo.orden_pago')
T_ORDEN = ('SELECT uetr, folio, estatus, horas_liquidacion, fecha_registro, fecha_envio, registros '
           'FROM decant.orden_pago')
T_ULTIMA = 'SELECT uetr, MAX(fecha_hora) FROM decant.partida_corresponsal GROUP BY uetr'
L_CLIENTE = ("SELECT p.uetr, l.renglon, l.concepto, l.moneda, l.monto, l.fecha_hora, l.referencia, p.id "
             "FROM dbo.partida_liquidada l JOIN dbo.orden_pago p ON p.id = l.orden_id WHERE p.estatus <> 'REEMPLAZADA'")
T_CLIENTE = 'SELECT uetr, renglon, concepto, moneda, monto, fecha_hora, referencia FROM decant.partida_cliente'
L_CORRESPONSAL = ('SELECT p.uetr, s.renglon, s.concepto, s.moneda, s.monto, s.fecha_hora, s.referencia '
                  'FROM dbo.partida_solicitada s JOIN dbo.orden_pago p ON p.id = s.orden_id')
T_CORRESPONSAL = ('SELECT uetr, renglon, concepto, moneda, monto, fecha_hora, referencia '
                  'FROM decant.partida_corresponsal')
L_FOLIO = 'SELECT serie, siguiente FROM dbo.folio'
T_FOLIO = 'SELECT serie, siguiente FROM decant.consecutivo'
T_DESCARTADAS = 'SELECT uetr, motivo, instante FROM decant.liquidacion_descartada'
L_COMISION = ("SELECT l.monto, o.monto_mxn FROM dbo.partida_liquidada l JOIN dbo.orden_pago p ON p.id = l.orden_id "
              "JOIN dbo.operacion o ON o.id = p.operacion_id WHERE l.concepto = 'COMISION' "
              "AND p.estatus <> 'REEMPLAZADA'")
L_BITACORA_JOB = ("SELECT p.uetr, b.estatus_nuevo, b.fecha FROM dbo.bitacora b JOIN dbo.orden_pago p ON p.id = b.llave "
                  "WHERE b.usuario = 'svc_agente'")
T_MARCAS = 'SELECT regla, caso, instante, cumple, detalle FROM decant.marca'

PARTIDA_CLIENTE = (('concepto', ()), ('moneda', ('char',)), ('monto', ()), ('fecha_hora', ('T5_cdmx_llegada',)),
                   ('referencia', ()))
PARTIDA_CORRESPONSAL = (('concepto', ()), ('moneda', ('char',)), ('monto', ()), ('fecha_hora', ('T5_ny',)),
                        ('referencia', ('ciega1_T3',)))


def _filas(cursor, consulta: str) -> list[tuple]:
    cursor.execute(consulta)
    return cursor.fetchall()


class Regla:
    def __init__(self, id_: str, nombre: str, origen: str):
        self.id, self.nombre, self.origen = id_, nombre, origen
        self.casos = self.coinciden = 0
        self.sobran = 0            # casos que sólo existen en el TO-BE
        self.diferencias: list[arbitraje.Diferencia] = []

    def caso(self, llave, legado, tobe, contexto: dict | None = None):
        self.casos += 1
        if texto(legado) == texto(tobe):
            self.coinciden += 1
        else:
            self.diferencias.append(arbitraje.Diferencia(self.id, str(llave), texto(legado), texto(tobe),
                                                         contexto or {}))

    def resumen(self, arbitros) -> dict:
        arbitrado = arbitraje.arbitrar(self.diferencias, arbitros)
        return {'regla': self.id, 'nombre': self.nombre, 'origen': self.origen, 'casos': self.casos,
                'coinciden': self.coinciden, 'sobran_en_tobe': self.sobran,
                'pct': round(100 * self.coinciden / self.casos, 2) if self.casos else None,
                'arbitraje': arbitrado}


# ── árbitros del motor ───────────────────────────────────────────────────────────────────────────────────────

def _horas_de_desfase(envio_utc, ultima_utc) -> Decimal:
    """Lo que el legado suma por suponer Nueva York siempre una hora adelante: (NY − CDMX) − 1 h."""
    ny = ultima_utc.astimezone(NUEVA_YORK).utcoffset()
    mx = envio_utc.astimezone(CDMX).utcoffset()
    return Decimal(int((ny - mx - timedelta(hours=1)).total_seconds()) // 60) / Decimal(60)


def _audita_t5(d: arbitraje.Diferencia) -> tuple[bool, str]:
    extra = _horas_de_desfase(d.contexto['envio_utc'], d.contexto['ultima_utc'])
    diferencia = Decimal(d.legado) - Decimal(d.tobe)
    ok = extra != 0 and diferencia == extra
    return ok, (f'legado − TO-BE = {diferencia} h; (NY − CDMX) − 1 h en esos instantes = {extra} h'
                + ('; hora repetida de la Ciudad de México' if d.contexto.get('envio_ambiguo') else ''))


def arbitros_del_motor(corte_utc) -> list[arbitraje.Arbitro]:
    return [
        arbitraje.Arbitro(
            'T5-desfase-fijo', arbitraje.DISCREPANCIA, 'ADR 0008',
            'el legado resta una hora fija a la hora de Nueva York; el TO-BE usa los instantes',
            aplica=lambda d: d.regla == 'R08' and d.legado is not None and d.tobe is not None,
            audita=_audita_t5,
            pregunta='¿Las horas de liquidación se calculan con el desfase real de Nueva York (TO-BE) o se conserva '
                     'la hora fija del legado (una hora de más entre marzo y noviembre desde 2023)?'),
        arbitraje.Arbitro(
            'avance', arbitraje.AVANCE, 'corte medido',
            'el valor del TO-BE sale de un evento del universo posterior al corte',
            aplica=lambda d: d.contexto.get('instante_evento') is not None,
            audita=lambda d: (d.contexto['instante_evento'] > corte_utc,
                              f"evento {d.contexto['instante_evento'].isoformat()} vs corte {corte_utc.isoformat()}")),
    ]


# ── medición ────────────────────────────────────────────────────────────────────────────────────────────────

def _instante(valor, zona):
    return a_utc(valor, zona).astimezone(timezone.utc)


def medir(cursor_legado, cursor_tobe, universo: Path, corte_utc) -> dict:
    r = {k: Regla(*v) for k, v in {
        'R01': ('R01', 'folio FX: consumible en orden de llegada', 'sp_registrar_operacion'),
        'R02': ('R02', 'tipo de cambio calculado (referencia × margen)', 'sp_registrar_operacion'),
        'R03': ('R03', 'monto en pesos ROUND(monto × tc, 2)', 'sp_registrar_operacion'),
        'R04': ('R04', 'folio OP: consumible por documento; el re-registro lo conserva', 'sp_registrar_orden'),
        'R05': ('R05', 'partidas del cliente (principal, comisión que trunca, IVA, gastos OUR)', 'sp_registrar_orden'),
        'R06': ('R06', 'partidas del corresponsal desde el buzón (llave UETR / :21:)', 'sp_registrar_liquidacion'),
        'R07': ('R07', 'estatus del documento (liquidación, D3, vencimiento con reloj inyectado, conciliación D2)',
                'sp_registrar_liquidacion + sp_conciliar'),
        'R08': ('R08', 'horas de liquidación con los instantes (T5)', 'sp_conciliar'),
        'R09': ('R09', 're-registro: registros por documento y fecha del más reciente', 'sp_registrar_orden'),
        'R11': ('R11', 'consecutivos al final (siguiente folio FX y OP)', 'dbo.folio'),
        'R12': ('R12', 'liquidaciones descartadas por llegar vencidas (D3, visibles en el TO-BE)',
                'sp_registrar_liquidacion'),
    }.items()}

    tobe_op = {f[0]: f for f in _filas(cursor_tobe, T_OPERACION)}
    for id_, folio, tc_ref, tc, pesos in _filas(cursor_legado, L_OPERACION):
        t = tobe_op.get(id_)
        r['R01'].caso(id_, folio, t and t[1])
        if tc_ref != 0:
            r['R02'].caso(id_, tc, t and t[2])
        r['R03'].caso(id_, pesos, t and t[3])
    del tobe_op

    tobe_orden = {str(f[0]): f for f in _filas(cursor_tobe, T_ORDEN)}
    ultima = {str(u): m for u, m in _filas(cursor_tobe, T_ULTIMA)}
    por_uetr: dict[str, list[tuple]] = defaultdict(list)
    filas_orden = _filas(cursor_legado, L_ORDEN)
    pisos = pisos_por_llegada([{'id': f[0], 'uetr': f[1], 'fecha_registro': f[5]} for f in filas_orden])
    for fila in filas_orden:
        por_uetr[fila[1].rstrip()].append(fila)
    ambiguas = 0
    for uetr, filas in por_uetr.items():
        vigente = [f for f in filas if f[3] != 'REEMPLAZADA'][0]
        t = tobe_orden.get(uetr)
        r['R04'].caso(uetr, vigente[2], t and t[1])
        r['R07'].caso(uetr, vigente[3], t and t[2])
        if vigente[4] is not None:
            envio_ambiguo = CDMX.utcoffset(vigente[6].replace(fold=0)) != CDMX.utcoffset(vigente[6].replace(fold=1))
            ambiguas += envio_ambiguo
            r['R08'].caso(uetr, vigente[4], t and t[3], {
                'envio_utc': t[5] if t else None, 'ultima_utc': ultima.get(uetr), 'envio_ambiguo': envio_ambiguo})
        ultimo = max(filas, key=lambda f: f[0])
        r['R09'].caso(uetr, f'{len(filas)}|{texto(pisos[ultimo[0]][1])}',
                      t and f'{t[6]}|{texto(t[4])}')
    del tobe_orden

    for regla, consulta_l, consulta_t, columnas in (('R05', L_CLIENTE, T_CLIENTE, PARTIDA_CLIENTE),
                                                    ('R06', L_CORRESPONSAL, T_CORRESPONSAL, PARTIDA_CORRESPONSAL)):
        tobe = {(str(f[0]), f[1]): f for f in _filas(cursor_tobe, consulta_t)}
        for fila in _filas(cursor_legado, consulta_l):
            llave = (fila[0].rstrip(), fila[1])
            piso = pisos[fila[7]][1] if len(fila) > 7 else None      # la partida del cliente es de SU registro
            esperado = '|'.join(texto(aplicar(p, v, piso)) or '∅' for (_, p), v in zip(columnas, fila[2:7]))
            t = tobe.get(llave)
            obtenido = '|'.join(texto(v) or '∅' for v in t[2:]) if t else None
            r[regla].caso(f'{llave[0]}/{llave[1]}', esperado, obtenido)
        r[regla].sobran = len(tobe) - r[regla].casos

    folios_tobe = dict(_filas(cursor_tobe, T_FOLIO))
    for serie, siguiente in _filas(cursor_legado, L_FOLIO):
        r['R11'].caso(serie.rstrip(), siguiente, folios_tobe.get(serie.rstrip()))

    # D3: las confirmaciones que el legado tiró (documento VENCIDO) están en el buzón; el TO-BE las debe registrar
    # como descartadas, y SÓLO ésas
    vencidas = {u for u, fs in por_uetr.items() if any(f[3] == 'VENCIDA' for f in fs)}
    tardias = set()
    for archivo in sorted((universo / 'interfaces' / 'corresponsal').glob('*.fin')):
        for c in leer_buzon(archivo.read_text(encoding='utf-8')):
            if c.uetr in vencidas and c.instante_utc <= corte_utc:
                tardias.add(c.uetr)
    descartadas = {str(u) for u, motivo, _ in _filas(cursor_tobe, T_DESCARTADAS) if motivo == 'documento VENCIDA'}
    for uetr in sorted(tardias | descartadas):
        r['R12'].caso(uetr, 'descartada' if uetr in tardias else None, 'descartada' if uetr in descartadas else None)

    arbitros = arbitros_del_motor(corte_utc)
    reglas = [x.resumen(arbitros) for x in r.values()]
    return {'reglas': reglas, 'hipotesis': hipotesis(cursor_legado, cursor_tobe, por_uetr),
            'notas': {'horas_con_envio_en_hora_repetida': ambiguas}}


# ── hipótesis y controles ────────────────────────────────────────────────────────────────────────────────────

def hipotesis(cursor_legado, cursor_tobe, por_uetr) -> list[dict]:
    resultado = []
    comisiones = _filas(cursor_legado, L_COMISION)

    def comision(pesos: Decimal, redondeo) -> Decimal:
        return max((pesos * Decimal('0.0025')).quantize(Decimal('0.01'), rounding=redondeo), Decimal('150.00'))

    for nombre, redondeo, elegida in (('trunca (ROUND(x, 2, 1))', ROUND_DOWN, True),
                                      ('redondea a la mitad', ROUND_HALF_UP, False)):
        n = sum(1 for monto, pesos in comisiones if comision(pesos, redondeo) == monto)
        resultado.append({'regla': 'R05 comisión (D1)', 'hipotesis': nombre, 'elegida': elegida,
                          'casos': len(comisiones), 'coinciden': n, 'pct': round(100 * n / len(comisiones), 2)})

    # control al azar: estatus inventado con la MISMA distribución del legado
    vigentes = [[f for f in fs if f[3] != 'REEMPLAZADA'][0][3] for fs in por_uetr.values()]
    distribucion = Counter(vigentes)
    azar = random.Random(20231229)
    inventados = azar.choices(list(distribucion), weights=list(distribucion.values()), k=len(vigentes))
    aciertos = sum(1 for a, b in zip(vigentes, inventados) if a == b)
    por_clase = {e: round(100 * sum(1 for a, b in zip(vigentes, inventados) if a == e and b == e) / n, 1)
                 for e, n in distribucion.items()}
    resultado.append({'regla': 'R07 estatus', 'hipotesis': 'CONTROL: al azar con la distribución del legado',
                      'elegida': False, 'casos': len(vigentes), 'coinciden': aciertos,
                      'pct': round(100 * aciertos / len(vigentes), 2), 'pct_por_clase': por_clase,
                      'lectura': 'con una clase dominante, el % global de una regla inventada es alto: por eso se '
                                 'publica también por clase'})
    return resultado


# ── sólo marca ───────────────────────────────────────────────────────────────────────────────────────────────

def solo_marca(cursor_legado, cursor_marcas, regla: str) -> dict:
    """Cruza las marcas ✔/✘ del motor (bandera apagada) con lo que el legado HIZO según su bitácora."""
    hecho: dict[str, tuple[str, object]] = {}
    for uetr, estatus, fecha in _filas(cursor_legado, L_BITACORA_JOB):
        hecho[uetr.rstrip()] = (estatus, _instante(fecha, CDMX))
    marcas = [(str(c), i, cumple, det) for reg, c, i, cumple, det in _filas(cursor_marcas, T_MARCAS) if reg == regla]
    coinciden, diferencias = 0, []
    for caso, instante, cumple, detalle in marcas:
        estatus, cuando = hecho.get(caso, (None, None))
        if regla.endswith('vencimiento'):
            esperado = (estatus == 'VENCIDA', cuando if estatus == 'VENCIDA' else None)
            obtenido = (cumple, instante if cumple else None)
        else:
            esperado = (estatus == 'CONCILIADA', cuando if estatus in ('CONCILIADA', 'DIFERENCIA') else None)
            obtenido = (cumple, instante)
        if esperado == obtenido:
            coinciden += 1
        elif len(diferencias) < 5:
            diferencias.append({'caso': caso, 'legado': [estatus, texto(cuando)],
                                'marca': ['✔' if cumple else '✘', texto(instante), detalle]})
    accion = 'VENCIDA' if regla.endswith('vencimiento') else ('CONCILIADA', 'DIFERENCIA')
    actuados = {u for u, (e, _) in hecho.items() if (e == accion if isinstance(accion, str) else e in accion)}
    sin_marca = len(actuados - {m[0] for m in marcas})
    return {'regla': regla, 'marcas': len(marcas), 'con_palomita': sum(1 for m in marcas if m[2]),
            'con_tache': sum(1 for m in marcas if not m[2]), 'coinciden_con_el_legado': coinciden,
            'pct': round(100 * coinciden / len(marcas), 2) if marcas else None,
            'actuados_por_el_legado_sin_marca': sin_marca, 'ejemplos_distintos': diferencias}
