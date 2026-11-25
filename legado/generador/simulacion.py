"""Simulación DETERMINISTA de tres años del back-office de divisas del Banco Ficticio del Norte.

Una semilla fija produce siempre los mismos datos (mismo hash), y cada fila resulta de simular el CÓDIGO del
legado (los procedimientos de `legado/sql/05_procedimientos.sql`) sobre una línea de tiempo en UTC:

    operación → orden de pago (alta y re-registro cada mañana) → liquidación del corresponsal → job nocturno

Lo ocurrido antes de la foto del respaldo se carga en bloque; lo ocurrido después (el «delta del mismo día»)
sale como guion de llamadas a los mismos procedimientos, que ejecuta `legado/vivo`.
"""
from __future__ import annotations

import bisect
import hashlib
import math
import random
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from . import catalogos as cat
from . import interfaces
from .zonas import CDMX, NUEVA_YORK, UTC, a_utc, local

D2 = Decimal('0.01')
D6 = Decimal('0.000001')
UNO = Decimal('1')

COLUMNAS = {
    'moneda': ('codigo', 'numerico', 'nombre', 'decimales', 'activa'),
    'folio': ('serie', 'siguiente', 'actualizado'),
    'operacion': ('id', 'folio', 'fecha_operacion', 'sucursal', 'canal', 'cliente', 'cuenta_clabe', 'tipo', 'moneda',
                  'monto_divisa', 'tipo_cambio', 'tipo_cambio_referencia', 'monto_mxn', 'estatus'),
    'orden_pago': ('id', 'operacion_id', 'folio', 'uetr', 'referencia_mt103', 'fecha_registro', 'fecha_envio',
                   'fecha_valor', 'bic_corresponsal', 'bic_intermediario', 'beneficiario', 'cuenta_beneficiario',
                   'moneda', 'monto', 'gastos', 'codigo_proposito', 'estatus', 'horas_liquidacion'),
    'partida_solicitada': ('id', 'orden_id', 'renglon', 'concepto', 'moneda', 'monto', 'fecha_hora', 'referencia'),
    'partida_liquidada': ('id', 'orden_id', 'renglon', 'concepto', 'moneda', 'monto', 'fecha_hora', 'referencia'),
    'bitacora': ('id', 'tabla', 'llave', 'accion', 'estatus_anterior', 'estatus_nuevo', 'usuario', 'fecha'),
}
# Orden de carga (padres antes que hijos).
TABLAS = tuple(COLUMNAS)


def q2(valor: Decimal) -> Decimal:
    """Redondeo de SQL Server al convertir a decimal(…, 2): mitad lejos del cero."""
    return valor.quantize(D2, rounding=ROUND_HALF_UP)


def q6(valor: Decimal) -> Decimal:
    return valor.quantize(D6, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Config:
    semilla: int = 20231229
    inicio: date = date(2021, 1, 1)
    # Día de negocio del respaldo FECHADO. La foto se toma a las 06:00 (hora local), antes de que abra el día.
    fecha_respaldo: date = date(2023, 12, 29)
    # Medido, no adivinado: ver legado/VOLUMEN.md.
    operaciones_por_dia: int = 400
    hora_respaldo: time = time(6, 0)
    hora_congelamiento: time = time(18, 0)
    hora_fin: time = time(19, 0)

    @property
    def respaldo(self) -> datetime:
        return a_utc(datetime.combine(self.fecha_respaldo, self.hora_respaldo))

    @property
    def congelamiento(self) -> datetime:
        return a_utc(datetime.combine(self.fecha_respaldo, self.hora_congelamiento))

    @property
    def fin(self) -> datetime:
        return a_utc(datetime.combine(self.fecha_respaldo, self.hora_fin))


class Operacion:
    __slots__ = ('seq', 'insercion', 'fecha_local', 'sucursal', 'canal', 'cliente', 'clabe', 'tipo', 'moneda',
                 'monto', 'tc', 'tc_ref', 'monto_mxn', 'estatus', 'id', 'folio', 'orden_archivo', 'cliente_original',
                 'reenvio', 'ref_sucursal')


class Documento:
    """Una orden de pago como DOCUMENTO (llave natural: uetr). El legado la registra una o varias veces."""
    __slots__ = ('seq', 'op', 'uetr', 'referencia', 't_registro', 't_envio', 'fecha_valor', 'bic', 'bic_int',
                 'beneficiario', 'cuenta', 'moneda', 'monto', 'gastos', 'proposito', 't_liquidacion', 'abono',
                 'comision', 'ref_corresponsal', 'aceptada', 't_vencimiento', 't_conciliacion', 'mananas',
                 'folio', 'filas', 'estado')


@dataclass
class Datos:
    config: Config
    tablas: dict[str, list[tuple]]
    pasos: list[dict]
    operaciones: list[Operacion] = field(repr=False)
    documentos: list[Documento] = field(repr=False)
    interfaces: dict[str, str] = field(repr=False, default_factory=dict)
    choques: dict[str, list] = field(default_factory=dict)

    def conteos(self) -> dict[str, int]:
        return {t: len(filas) for t, filas in self.tablas.items()}

    def huellas(self) -> dict[str, str]:
        """sha256 por tabla (y del guion del delta) sobre una serialización canónica."""
        resultado = {}
        for tabla, filas in self.tablas.items():
            h = hashlib.sha256()
            for fila in filas:
                h.update('|'.join('\\N' if v is None else str(v) for v in fila).encode('utf-8'))
                h.update(b'\n')
            resultado[tabla] = h.hexdigest()
        h = hashlib.sha256()
        for paso in self.pasos:
            h.update(repr(sorted(paso.items())).encode('utf-8'))
        resultado['delta'] = h.hexdigest()
        h = hashlib.sha256()
        for ruta in sorted(self.interfaces):
            h.update(ruta.encode('utf-8') + b'\0' + self.interfaces[ruta].encode('utf-8'))
        resultado['interfaces'] = h.hexdigest()
        return resultado

    def huella(self) -> str:
        return hashlib.sha256(repr(sorted(self.huellas().items())).encode('utf-8')).hexdigest()


# ── tipos de cambio ──────────────────────────────────────────────────────────────────────────────────────────

def _interpolar(anclas, dia: date) -> float:
    for (d0, v0), (d1, v1) in zip(anclas, anclas[1:]):
        if d0 <= dia <= d1:
            return v0 + (v1 - v0) * (dia - d0).days / max((d1 - d0).days, 1)
    return anclas[-1][1]


def _tasas(cfg: Config, rng: random.Random) -> dict[date, dict[str, Decimal]]:
    """Tipo de cambio de referencia (pesos por unidad) de cada moneda, por día."""
    dias = (cfg.fecha_respaldo - cfg.inicio).days + 1
    ruido = {c[0]: 0.0 for c in cat.MONEDAS}
    tasas: dict[date, dict[str, Decimal]] = {}
    for k in range(dias):
        dia = cfg.inicio + timedelta(days=k)
        for codigo in ruido:
            ruido[codigo] = ruido[codigo] * 0.97 + rng.gauss(0, 0.004)
        usd_mxn = _interpolar(cat.USD_MXN, dia) * (1 + ruido['USD'])
        del_dia = {}
        for codigo, _num, _nom, _dec, ini, fin in cat.MONEDAS:
            if ini is None:
                continue
            valor_usd = ini + (fin - ini) * k / max(dias - 1, 1)
            if codigo != 'USD':
                valor_usd *= 1 + ruido[codigo]
            del_dia[codigo] = q6(Decimal(repr(usd_mxn * valor_usd)))
        tasas[dia] = del_dia
    return tasas


def _valor_usd(codigo: str, k: int, dias: int) -> float:
    for c, _num, _nom, _dec, ini, fin in cat.MONEDAS:
        if c == codigo:
            return ini + (fin - ini) * k / max(dias - 1, 1)
    raise KeyError(codigo)


# ── operaciones ──────────────────────────────────────────────────────────────────────────────────────────────

# Peso relativo de cada hora local en la banca en línea (noche baja, pero no cero: así hay operaciones en la
# 1:00–1:59 que se repite el día que termina el horario de verano).
_PESO_HORA_EN_LINEA = (0.35, 0.40, 0.25, 0.15, 0.15, 0.2, 0.4, 0.7, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
                       0.9, 0.8, 0.8, 0.7, 0.6, 0.5, 0.4)


def _clientes(rng: random.Random, cuantos: int = 6000):
    pool = []
    for _ in range(cuantos):
        if rng.random() < 0.25:
            nombre = rng.choice(cat.EMPRESAS)
        else:
            nombre = f'{rng.choice(cat.NOMBRES)} {rng.choice(cat.APELLIDOS)} {rng.choice(cat.APELLIDOS)}'
        cuerpo = cat.BANCO_CLABE + rng.choice(cat.PLAZAS) + ''.join(str(rng.randrange(10)) for _ in range(11))
        pool.append((nombre, cuerpo + cat.digito_clabe(cuerpo)))
    return pool


def _instante_en_linea(rng: random.Random, dia: date) -> datetime:
    inicio = a_utc(datetime.combine(dia, time(0)))
    fin = a_utc(datetime.combine(dia + timedelta(days=1), time(0)))
    segundos = int((fin - inicio).total_seconds())
    while True:
        candidato = inicio + timedelta(seconds=rng.randrange(segundos))
        hora = candidato.astimezone(CDMX).hour
        if rng.random() < _PESO_HORA_EN_LINEA[hora]:
            return candidato.replace(second=0)


def _operaciones(cfg: Config, rng: random.Random, tasas) -> list[Operacion]:
    clientes = _clientes(rng)
    pesos_cliente = [1 / (i + 1) ** 0.6 for i in range(len(clientes))]
    acumulado_cliente = list(_acumular(pesos_cliente))
    monedas = [m for m, _ in cat.PESO_MONEDA]
    acumulado_moneda = list(_acumular([p for _, p in cat.PESO_MONEDA]))
    dias = (cfg.fecha_respaldo - cfg.inicio).days + 1
    ops: list[Operacion] = []
    seq = 0
    for k in range(dias):
        dia = cfg.inicio + timedelta(days=k)
        dow = dia.weekday()
        factor = (1.15, 1.15, 1.15, 1.15, 1.15, 0.55, 0.30)[dow]
        crecimiento = 0.85 + 0.30 * k / max(dias - 1, 1)
        n = max(0, round(cfg.operaciones_por_dia * factor * crecimiento * rng.gauss(1, 0.12)))
        if dow < 5:
            canales = (('VENTANILLA', 0.45), ('EN_LINEA', 0.40), ('ARCHIVO', 0.15))
        elif dow == 5:
            canales = (('VENTANILLA', 0.50), ('EN_LINEA', 0.50))
        else:
            canales = (('EN_LINEA', 1.0),)
        for _ in range(n):
            op = Operacion()
            op.seq = seq
            seq += 1
            canal = _canal(rng.random(), canales)
            op.canal = canal
            if canal == 'VENTANILLA':
                fin_h = 13 if dow == 5 else 17
                hora = datetime.combine(dia, time(9)) + timedelta(minutes=rng.randrange((fin_h - 9) * 60))
                op.insercion = a_utc(hora)
                op.sucursal = rng.choice(cat.SUCURSALES)
            elif canal == 'EN_LINEA':
                op.insercion = _instante_en_linea(rng, dia)
                op.sucursal = cat.SUCURSAL_EN_LINEA
            else:
                # el sistema de la sucursal manda la hora redondeada a la hora; el archivo se carga a las 22:00
                hora = datetime.combine(dia, time(9 + rng.randrange(8)))
                op.fecha_local = hora
                op.insercion = a_utc(datetime.combine(dia, time(22)))
                op.sucursal = rng.choice(cat.SUCURSALES)
            if canal != 'ARCHIVO':
                op.fecha_local = local(op.insercion)
            # el archivo de sucursales llega ordenado por sucursal y hora: así se asignan sus ids
            op.orden_archivo = (op.sucursal, op.fecha_local, seq) if canal == 'ARCHIVO' else ('', datetime.min, seq)
            nombre, clabe = clientes[_elegir(rng, acumulado_cliente)]
            if canal != 'EN_LINEA':
                nombre = nombre.upper()
            op.cliente_original = nombre
            op.reenvio = None
            op.ref_sucursal = None
            if canal == 'ARCHIVO' and date(2021, 3, 1) <= dia <= date(2022, 6, 30):
                # la interfaz de sucursales leyó como latin-1 archivos que venían en UTF-8
                nombre = nombre.encode('utf-8').decode('latin-1')
            op.cliente = nombre
            op.tipo = 'V' if rng.random() < 0.60 else 'C'
            moneda = monedas[_elegir(rng, acumulado_moneda)]
            if moneda == 'HRK' and dia >= cat.FIN_HRK:
                moneda = 'EUR'
            op.moneda = moneda
            efectivo = canal == 'VENTANILLA' and rng.random() < 0.6
            op.clabe = 'NA' if efectivo else clabe
            usd = min(max(math.exp(rng.gauss(math.log(2200), 1.05)), 20.0), 400000.0)
            op.monto = q2(Decimal(repr(usd / _valor_usd(moneda, k, dias))))
            referencia = tasas[dia][moneda]
            if canal == 'VENTANILLA' and rng.random() < 0.30:
                # el cajero teclea el tipo de cambio y no captura la referencia (queda 0 en la base)
                op.tc_ref = None
                op.tc = (referencia * (Decimal('1.004') if op.tipo == 'V' else Decimal('0.996'))).quantize(
                    Decimal('0.0001'), rounding=ROUND_HALF_UP)
            else:
                op.tc_ref = referencia
                op.tc = q6(referencia * (Decimal('1.0035') if op.tipo == 'V' else Decimal('0.9965')))
            op.monto_mxn = q2(op.monto * op.tc)
            op.estatus = 'CANCELADA' if rng.random() < 0.008 else 'CONCERTADA'
            op.id = op.folio = None
            ops.append(op)
    return ops


def _canal(r: float, canales: tuple[tuple[str, float], ...]) -> str:
    acumulado = 0.0
    for nombre, peso in canales:
        acumulado += peso
        if r < acumulado:
            return nombre
    return canales[-1][0]


def _acumular(pesos):
    total = 0.0
    for p in pesos:
        total += p
        yield total


def _elegir(rng: random.Random, acumulado: list[float]) -> int:
    return min(bisect.bisect_right(acumulado, rng.random() * acumulado[-1]), len(acumulado) - 1)


# ── documentos (órdenes de pago) ─────────────────────────────────────────────────────────────────────────────

def _siguiente_habil(dia: date) -> date:
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


def _abrir_nueva_york(instante: datetime, rng: random.Random) -> datetime:
    """El corresponsal liquida en días hábiles de 08:00 a 18:00, hora de Nueva York."""
    ny = instante.astimezone(NUEVA_YORK)
    if ny.weekday() < 5 and 8 <= ny.hour < 18:
        return instante
    dia = ny.date() + timedelta(days=1) if ny.hour >= 18 else ny.date()
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    apertura = datetime.combine(dia, time(8)).replace(tzinfo=NUEVA_YORK).astimezone(UTC)
    return apertura + timedelta(minutes=rng.randrange(150), seconds=rng.randrange(60))


def _noche(instante: datetime) -> datetime:
    """Primera corrida del job (23:30 hora local) a partir de un instante."""
    hora = local(instante)
    noche = datetime.combine(hora.date(), time(23, 30))
    if hora >= noche:
        noche += timedelta(days=1)
    return a_utc(noche)


def _documentos(cfg: Config, rng: random.Random, ops: list[Operacion], dias: int) -> list[Documento]:
    docs: list[Documento] = []
    pesos_prop = list(_acumular([p for _, p in cat.PROPOSITOS]))
    cuentas = {}
    for op in ops:
        if op.tipo != 'V' or op.estatus != 'CONCERTADA':
            continue
        probabilidad = {'EN_LINEA': 0.85, 'VENTANILLA': 0.35, 'ARCHIVO': 0.70}[op.canal]
        if rng.random() >= probabilidad:
            continue
        d = Documento()
        d.seq = len(docs)
        d.op = op
        d.uetr = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        d.t_registro = (op.insercion + timedelta(minutes=1 + rng.randrange(12), seconds=rng.randrange(60)))
        d.t_envio = d.t_registro + timedelta(seconds=rng.randrange(90))
        envio = local(d.t_envio)
        valor = envio.date() + timedelta(days=1) if envio.hour >= 14 else envio.date()
        d.fecha_valor = _siguiente_habil(valor)
        d.moneda = op.moneda
        d.monto = op.monto
        d.bic = cat.CORRESPONSAL[op.moneda]
        d.bic_int = rng.choice(cat.INTERMEDIARIOS) if rng.random() < 0.15 else None
        d.beneficiario = rng.choice(cat.BENEFICIARIOS[op.moneda])
        if d.beneficiario not in cuentas:
            prefijo = {'USD': '', 'CAD': ''}.get(op.moneda, d.bic[4:6])
            cuentas[d.beneficiario] = prefijo + ''.join(str(rng.randrange(10)) for _ in range(18))
        d.cuenta = cuentas[d.beneficiario]
        r = rng.random()
        d.gastos = 'OUR' if r < 0.30 else ('SHA' if r < 0.85 else 'BEN')
        d.proposito = cat.PROPOSITOS[_elegir(rng, pesos_prop)][0] if rng.random() < 0.93 else None

        # liquidación del corresponsal
        r = rng.random()
        if r < 0.004:
            d.t_liquidacion = None
        else:
            if r < 0.72:
                horas = rng.uniform(0.5, 6)
            elif r < 0.92:
                horas = rng.uniform(6, 30)
            elif r < 0.984:
                horas = rng.uniform(30, 70)
            else:
                horas = rng.uniform(70, 120)
            bruto = d.t_envio + timedelta(seconds=int(horas * 3600))
            d.t_liquidacion = _abrir_nueva_york(bruto, rng)
        valor_usd = _valor_usd(op.moneda, (local(op.insercion).date() - cfg.inicio).days, dias)
        if d.gastos == 'OUR':
            comision = Decimal(0)
        elif op.moneda == 'JPY':
            comision = Decimal(round(rng.uniform(10, 45) / valor_usd))
        else:
            comision = q2(Decimal(repr(rng.uniform(10, 45) / valor_usd)))
        principal = d.monto
        if op.moneda == 'JPY':
            # el corresponsal abona yenes enteros (ISO 4217: el yen no tiene decimales)
            principal = principal.to_integral_value(rounding=ROUND_DOWN)
        # el corresponsal nunca cobra más de la mitad de lo que abona (órdenes de pocos dólares)
        tope = (principal / 2).to_integral_value(rounding=ROUND_DOWN) if op.moneda == 'JPY' else q2(principal / 2)
        comision = min(comision, tope)
        abono = principal - comision
        if rng.random() < 0.012:
            descuento = Decimal(round(rng.uniform(1, 25) / valor_usd)) if op.moneda == 'JPY' else q2(
                Decimal(repr(rng.uniform(1, 25) / valor_usd)))
            abono -= max(descuento, D2)
        d.abono = abono
        d.comision = comision
        d.ref_corresponsal = 'FICT' + ''.join(str(rng.randrange(10)) for _ in range(12))

        # vencimiento: la regla del job compara la hora local de envío contra GETDATE() - 3 días
        envio_local = local(d.t_envio)
        noche = datetime.combine((envio_local + timedelta(days=3)).date(), time(23, 30))
        if noche - timedelta(days=3) <= envio_local:
            noche += timedelta(days=1)
        d.t_vencimiento = a_utc(noche)
        d.aceptada = d.t_liquidacion is not None and d.t_liquidacion < d.t_vencimiento
        d.t_conciliacion = _noche(d.t_liquidacion) if d.aceptada else None

        # re-registro: cada mañana hábil a las 07:00 la interfaz vuelve a dar de alta lo que sigue enviado
        limite = d.t_liquidacion if d.aceptada else d.t_vencimiento
        manana = datetime.combine(local(d.t_registro).date(), time(7))
        if local(d.t_registro) >= manana:
            manana += timedelta(days=1)
        d.mananas = []
        while a_utc(manana) < limite:
            if manana.weekday() < 5:          # la interfaz sólo corre en días hábiles
                d.mananas.append(manana)
            manana += timedelta(days=1)
        d.folio = None
        d.filas = []
        d.estado = None
        docs.append(d)

    # referencia :20: por día de envío, en orden de registro
    por_dia: dict[date, int] = {}
    for d in sorted(docs, key=lambda x: (x.t_registro, x.seq)):
        dia = local(d.t_envio).date()
        por_dia[dia] = por_dia.get(dia, 0) + 1
        d.referencia = f'BFN{dia:%y%m%d}{por_dia[dia]:06d}'
    return docs


# ── ensamblado: línea de tiempo → filas (antes del respaldo) y guion del delta (después) ───────────────────────

def _comision(monto_mxn: Decimal) -> Decimal:
    comision = (monto_mxn * Decimal('0.0025')).quantize(D2, rounding=ROUND_DOWN)   # ROUND(x, 2, 1): trunca
    return max(comision, Decimal('150.00'))


def _horas(envio_local: datetime, ultima_ny: datetime) -> Decimal:
    """DATEDIFF(minute, fecha_envio, DATEADD(hour, -1, ultima)) / 60.0, convertido a decimal(9,2)."""
    a = envio_local.replace(second=0, microsecond=0)
    b = (ultima_ny - timedelta(hours=1)).replace(second=0, microsecond=0)
    minutos = int((b - a).total_seconds() // 60)
    return q2(Decimal(minutos) / Decimal(60))


def _fmt(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def generar(cfg: Config | None = None) -> Datos:
    cfg = cfg or Config()
    rng = random.Random(cfg.semilla)
    dias = (cfg.fecha_respaldo - cfg.inicio).days + 1
    tasas = _tasas(cfg, rng)
    ops = _operaciones(cfg, rng, tasas)
    _reenvio_tardio(cfg, ops)
    docs = _documentos(cfg, rng, ops, dias)

    # eventos: (instante, prioridad, desempate, tipo, carga)
    eventos = []
    for op in ops:
        eventos.append((op.insercion, 0, op.orden_archivo, 'op', op))
    mananas: dict[datetime, list[Documento]] = {}
    for d in docs:
        eventos.append((d.t_registro, 1, (d.seq,), 'alta', (d, d.t_registro)))
        for m in d.mananas:
            mananas.setdefault(m, []).append(d)
        if d.aceptada:
            eventos.append((d.t_liquidacion, 2, (d.seq,), 'liquidacion', d))
    for m, lista in mananas.items():
        for pos, d in enumerate(sorted(lista, key=lambda x: x.uetr)):
            instante = a_utc(m) + timedelta(seconds=2 * pos)
            eventos.append((instante, 1, (pos,), 'alta', (d, instante)))
    noches: dict[datetime, tuple[list, list]] = {}
    for d in docs:
        if d.aceptada:
            noches.setdefault(d.t_conciliacion, ([], []))[0].append(d)
        else:
            noches.setdefault(d.t_vencimiento, ([], []))[1].append(d)
    for instante, (conciliar, vencer) in noches.items():
        eventos.append((instante, 3, (0,), 'noche', (conciliar, vencer)))
    eventos.sort(key=lambda e: (e[0], e[1], e[2]))

    filas = {t: [] for t in TABLAS}
    pasos: list[dict] = []
    folios = {'FX': 1, 'OP': 1}
    ultimo_folio = {'FX': None, 'OP': None}
    sig = {'operacion': 1, 'orden_pago': 1, 'partida_solicitada': 1, 'partida_liquidada': 1, 'bitacora': 1}

    def bitacora(llave, accion, antes, despues, usuario, instante):
        filas['bitacora'].append([sig['bitacora'], 'orden_pago', llave, accion, antes, despues, usuario,
                                  local(instante)])
        sig['bitacora'] += 1

    def cambiar(d: Documento, nuevo: str, usuario: str, instante: datetime, horas=None):
        fila = d.filas[-1]
        antes = fila[16]
        fila[16] = nuevo
        if horas is not None:
            fila[17] = horas
        bitacora(fila[0], 'U', antes, nuevo, usuario, instante)

    for instante, _prio, _des, tipo, carga in eventos:
        if instante >= cfg.fin:
            break
        fase = 'antes' if instante < cfg.respaldo else (
            'delta' if instante < cfg.congelamiento else 'posterior_congelamiento')
        if tipo == 'alta':
            d, momento = carga
            if momento != d.t_registro and d.estado != 'ENVIADA':
                continue        # el corresponsal ya lo liquidó a las 07:00:xx: la interfaz ya no lo reenvía
            d.estado = 'ENVIADA'
        elif tipo == 'liquidacion':
            carga.estado = 'LIQUIDADA'
        if fase != 'antes':
            pasos.extend(_paso(tipo, carga, fase, instante))
            continue
        if tipo == 'op':
            op = carga
            op.id = sig['operacion']
            sig['operacion'] += 1
            op.folio = f'FX-{folios["FX"]:09d}'
            folios['FX'] += 1
            ultimo_folio['FX'] = instante
            filas['operacion'].append((op.id, op.folio, op.fecha_local, op.sucursal, op.canal, op.cliente, op.clabe,
                                       op.tipo, op.moneda, op.monto, op.tc,
                                       op.tc_ref if op.tc_ref is not None else Decimal('0.000000'),
                                       op.monto_mxn, op.estatus))
        elif tipo == 'alta':
            d, momento = carga
            if d.folio is None:
                d.folio = f'OP-{folios["OP"]:09d}'
                folios['OP'] += 1
                ultimo_folio['OP'] = instante
            anterior = d.filas[-1] if d.filas else None
            registro = local(momento)
            fila = [sig['orden_pago'], d.op.id, d.folio, d.uetr, d.referencia, registro, local(d.t_envio),
                    d.fecha_valor, d.bic, d.bic_int or 'NA', d.beneficiario, d.cuenta, d.moneda, d.monto, d.gastos,
                    d.proposito, 'ENVIADA', None]
            sig['orden_pago'] += 1
            d.filas.append(fila)
            filas['orden_pago'].append(fila)
            bitacora(fila[0], 'I', None, 'ENVIADA', 'svc_interfaz', instante)
            if anterior is not None:
                anterior[16] = 'REEMPLAZADA'
                bitacora(anterior[0], 'U', 'ENVIADA', 'REEMPLAZADA', 'svc_interfaz', instante)
            comision = _comision(d.op.monto_mxn)
            renglones = [(1, 'PRINCIPAL', d.moneda, d.monto), (2, 'COMISION', 'MXN', comision),
                         (3, 'IVA', 'MXN', q2(comision * Decimal('0.16')))]
            if d.gastos == 'OUR':
                renglones.append((4, 'GASTOS_OUR', 'USD', Decimal('25.00')))
            for renglon, concepto, moneda, monto in renglones:
                filas['partida_liquidada'].append((sig['partida_liquidada'], fila[0], renglon, concepto, moneda,
                                                   monto, registro, d.folio))
                sig['partida_liquidada'] += 1
        elif tipo == 'liquidacion':
            d = carga
            orden = d.filas[-1][0]
            hora_ny = local(d.t_liquidacion, NUEVA_YORK)
            filas['partida_solicitada'].append((sig['partida_solicitada'], orden, 1, 'ABONO', d.moneda, d.abono,
                                                hora_ny, d.ref_corresponsal))
            sig['partida_solicitada'] += 1
            if d.comision > 0:
                filas['partida_solicitada'].append((sig['partida_solicitada'], orden, 2, 'COMISION_CORRESPONSAL',
                                                    d.moneda, d.comision, hora_ny, d.ref_corresponsal))
                sig['partida_solicitada'] += 1
            cambiar(d, 'LIQUIDADA', 'svc_swift', instante)
        else:
            conciliar, vencer = carga
            for d in sorted(conciliar, key=lambda x: x.filas[-1][0]):
                principal = d.monto
                abonado = d.abono + d.comision
                horas = _horas(local(d.t_envio), local(d.t_liquidacion, NUEVA_YORK))
                cambiar(d, 'CONCILIADA' if abonado == principal else 'DIFERENCIA', 'svc_agente', instante, horas)
            for d in sorted(vencer, key=lambda x: x.filas[-1][0]):
                cambiar(d, 'VENCIDA', 'svc_agente', instante)

    filas['moneda'] = [(c, n, nom, dec, 0 if c == 'HRK' and cfg.fecha_respaldo >= cat.BAJA_HRK else 1)
                       for c, n, nom, dec, _i, _f in cat.MONEDAS]
    filas['folio'] = [('FX', folios['FX'], local(ultimo_folio['FX'])),
                      ('OP', folios['OP'], local(ultimo_folio['OP']))]
    tablas = {t: [tuple(f) for f in filas[t]] for t in TABLAS}
    pasos = _con_catalogo(cfg, pasos)
    archivos = {**interfaces.buzon_corresponsal(docs, cfg.fin), **interfaces.archivo_sucursales(ops, cfg.fin)}
    # Choque de S3: documentos que el legado registra DESPUÉS del congelamiento y que el TO-BE también capturará.
    choques = {'tobe_tambien_captura': [p['args']['uetr'] for p in pasos
                                        if p['fase'] == 'posterior_congelamiento' and p['accion'] == 'orden']}
    return Datos(cfg, tablas, pasos, ops, docs, archivos, choques)


def _reenvio_tardio(cfg: Config, ops: list[Operacion]) -> None:
    """La sucursal con más operaciones de AYER no pudo mandar su archivo a las 22:00 y lo reenvía HOY a las 09:40,
    después del respaldo: altas nuevas (ids mayores al corte) con fecha de negocio ANTERIOR al corte."""
    ayer = cfg.fecha_respaldo - timedelta(days=1)
    del_dia = [op for op in ops if op.canal == 'ARCHIVO' and op.fecha_local.date() == ayer]
    if not del_dia:
        return
    conteo = Counter(op.sucursal for op in del_dia)
    sucursal = min(conteo, key=lambda s: (-conteo[s], s))
    llegada = a_utc(datetime.combine(cfg.fecha_respaldo, time(9, 40)))
    for op in del_dia:
        if op.sucursal == sucursal:
            op.insercion = llegada
            op.reenvio = llegada


def _paso(tipo: str, carga, fase: str, instante: datetime) -> list[dict]:
    """Evento posterior al respaldo → llamada a un procedimiento del legado (la ejecuta legado/vivo)."""
    base = {'fase': fase, 'instante_utc': instante.isoformat(), 'hora_local': local(instante).isoformat()}
    if tipo == 'op':
        op = carga
        return [dict(base, accion='operacion', ref=f'op:{op.seq}', args={
            'fecha_operacion': _fmt(op.fecha_local), 'sucursal': op.sucursal, 'canal': op.canal,
            'cliente': op.cliente, 'cuenta_clabe': None if op.clabe == 'NA' else op.clabe, 'tipo': op.tipo,
            'moneda': op.moneda, 'monto_divisa': _fmt(op.monto),
            'tipo_cambio_referencia': _fmt(op.tc_ref) if op.tc_ref is not None else None,
            'tipo_cambio': None if op.tc_ref is not None else _fmt(op.tc)})]
    if tipo == 'alta':
        d, momento = carga
        operacion = d.op.id if d.op.id is not None else f'op:{d.op.seq}'
        return [dict(base, accion='orden', ref=f'doc:{d.uetr}', args={
            'operacion_id': operacion, 'uetr': d.uetr, 'referencia_mt103': d.referencia,
            'fecha_registro': _fmt(local(momento)), 'fecha_envio': _fmt(local(d.t_envio)),
            'fecha_valor': _fmt(d.fecha_valor), 'bic_corresponsal': d.bic, 'bic_intermediario': d.bic_int,
            'beneficiario': d.beneficiario, 'cuenta_beneficiario': d.cuenta, 'moneda': d.moneda,
            'monto': _fmt(d.monto), 'gastos': d.gastos, 'codigo_proposito': d.proposito,
            'reregistro': momento != d.t_registro})]
    if tipo == 'liquidacion':
        d = carga
        return [dict(base, accion='liquidacion', ref=f'doc:{d.uetr}', args={
            'uetr': d.uetr, 'referencia': d.ref_corresponsal, 'fecha_hora': _fmt(local(d.t_liquidacion, NUEVA_YORK)),
            'abono': _fmt(d.abono), 'comision': _fmt(d.comision) if d.comision > 0 else None})]
    return []          # el job de la noche del corte cae fuera de la ventana


def _con_catalogo(cfg: Config, pasos: list[dict]) -> list[dict]:
    """Cambios de catálogo del mismo día, después del respaldo (el banco da de alta la leone nueva)."""
    instante = a_utc(datetime.combine(cfg.fecha_respaldo, time(9, 15)))
    base = {'fase': 'delta', 'instante_utc': instante.isoformat(), 'hora_local': local(instante).isoformat()}
    cambios = [dict(base, accion='alta_moneda', ref='moneda:SLE',
                    args={'codigo': 'SLE', 'numerico': '925', 'nombre': 'Leone de Sierra Leona', 'decimales': 2}),
               dict(base, accion='baja_moneda', ref='moneda:SLL', args={'codigo': 'SLL'})]
    resultado = [p for p in pasos if p['instante_utc'] < base['instante_utc']]
    resultado += cambios
    resultado += [p for p in pasos if p['instante_utc'] >= base['instante_utc']]
    return resultado
