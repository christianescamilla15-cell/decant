"""Cifras de control POR DOCUMENTO (criterios 7 y 8 del plan de S3, ADR 0016). Sin base: aquí están la forma canónica,
las huellas, la clasificación de lo que viaja y la conciliación; las filas las lee `corte/medir.py`.

**Documento** = la unidad de negocio, con su llave de negocio (documento + sucursal):
- la orden de pago: `(uetr, sucursal de su operación)`. Un re-registro (otra fila, otro id, el MISMO documento) no
  es otro documento: es un registro más de su historia, y el registro anterior sale;
- la operación de divisas: `(folio FX, sucursal)`.

**Huella sha256 por documento**, sobre su forma canónica: los valores tal como los guarda el legado (sólo se quita
el relleno de los `char(n)`, que es del tipo y no del dato), SIN ids internos, porque el id cambia con cada
re-registro y el documento no. Se agrega por tipo + estado + mes: documentos, montos por moneda y la huella del
grupo (sha256 de las líneas `documento|sucursal|huella`, ordenadas). Los totales globales no ven un documento que
cambia de mes; el grupo sí.

**Mes** = el de la fecha de negocio local: `fecha_operacion` de la operación y el PRIMER registro de la orden (estable
ante los re-registros). La grieta del plan es calcularlo en UTC: lo de la noche del último día cae en el mes siguiente.

**Destino** de cada documento (uno y sólo uno; cargado + no viaja = origen, también por grupo):
- `cargado`: viaja, con su estado AL CONGELAMIENTO (el estatus se reconstruye con la bitácora; lo escrito después es
  del barrido posterior al corte);
- `pendiente`: el documento sólo existe después del congelamiento (todas sus filas son posteriores): lo arbitra el
  barrido posterior al corte; migrarlo duplicaría lo que el TO-BE ya capturó;
- `duplicado`: su llave tiene más de un registro vigente al congelamiento;
- `sin_detalle`: la orden vigente no trae sus partidas del cliente;
- `dato_sucio`: falla una regla de integridad (sin registro vigente, operación o moneda que no existen, re-registro
  con otro folio, liquidación sobre un registro reemplazado).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import NamedTuple
from zoneinfo import ZoneInfo

CDMX = ZoneInfo('America/Mexico_City')
CARGADO = 'cargado'
MOTIVOS = ('pendiente', 'sin_detalle', 'duplicado', 'dato_sucio')
DESTINOS = (CARGADO, *MOTIVOS)
REEMPLAZADA = 'REEMPLAZADA'
# El estatus que sólo pone el job nocturno: al ponerlo también escribe horas_liquidacion, que la bitácora no guarda.
DEL_JOB = ('CONCILIADA', 'DIFERENCIA')
CSV_COLUMNAS = ('tipo', 'documento', 'sucursal', 'estado', 'mes', 'destino', 'huella')
MUESTRA = 50


class Operacion(NamedTuple):
    id: int
    folio: str
    fecha_operacion: datetime
    sucursal: str
    canal: str
    cliente: str
    cuenta_clabe: str
    tipo: str
    moneda: str
    monto_divisa: Decimal
    tipo_cambio: Decimal
    tipo_cambio_referencia: Decimal
    monto_mxn: Decimal
    estatus: str


class Registro(NamedTuple):
    """Una fila de `dbo.orden_pago` (un registro del documento), con el estatus de la foto que se mide."""
    id: int
    operacion_id: int
    folio: str
    uetr: str
    referencia_mt103: str
    fecha_registro: datetime
    fecha_envio: datetime
    fecha_valor: date
    bic_corresponsal: str
    bic_intermediario: str
    beneficiario: str
    cuenta_beneficiario: str
    moneda: str
    monto: Decimal
    gastos: str
    codigo_proposito: str | None
    estatus: str
    horas_liquidacion: Decimal | None


class Partida(NamedTuple):
    id: int
    orden_id: int
    renglon: int
    concepto: str
    moneda: str
    monto: Decimal
    fecha_hora: datetime
    referencia: str


@dataclass(frozen=True, slots=True)
class Documento:
    tipo: str
    documento: str
    sucursal: str
    estado: str
    fecha: datetime              # fecha de negocio local que decide el mes
    huella: str
    montos: tuple[tuple[str, Decimal], ...]
    destino: str
    motivo: str = ''

    @property
    def llave(self) -> tuple[str, str, str]:
        return (self.tipo, self.documento, self.sucursal)

    @property
    def mes(self) -> str:
        return mes(self.fecha)

    @property
    def mes_utc(self) -> str:
        return mes(self.fecha, utc=True)


def mes(fecha: datetime, utc: bool = False) -> str:
    """Mes de negocio (hora de la Ciudad de México) o, para la grieta, el del mismo instante en UTC."""
    if utc:
        fecha = fecha.replace(tzinfo=CDMX).astimezone(timezone.utc)
    return f'{fecha.year:04d}-{fecha.month:02d}'


# ── forma canónica y huella ─────────────────────────────────────────────────────────────────────────────────────

def _canonico(valor):
    if isinstance(valor, Decimal):
        return format(valor, 'f')                       # conserva la escala del tipo: 10.50 no es 10.5
    if isinstance(valor, datetime):
        return valor.isoformat(sep=' ', timespec='milliseconds')
    if isinstance(valor, date):
        return valor.isoformat()
    raise TypeError(f'sin forma canónica: {type(valor).__name__}')


def huella(campos: dict) -> str:
    texto = json.dumps(campos, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=_canonico)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _char(valor: str | None) -> str | None:
    """Quita el relleno de un `char(n)`: es del tipo, no del dato (ADR 0007, parche `char:n`)."""
    return None if valor is None else valor.rstrip(' ')


def documento_de_operacion(op: Operacion, tope: int, monedas: frozenset[str]) -> Documento:
    campos = {'tipo': 'operacion', 'folio': op.folio, 'sucursal': _char(op.sucursal),
              'fecha_operacion': op.fecha_operacion, 'canal': op.canal, 'cliente': op.cliente,
              'cuenta_clabe': op.cuenta_clabe, 'tipo_operacion': _char(op.tipo), 'moneda': _char(op.moneda),
              'monto_divisa': op.monto_divisa, 'tipo_cambio': op.tipo_cambio,
              'tipo_cambio_referencia': op.tipo_cambio_referencia, 'monto_mxn': op.monto_mxn, 'estatus': op.estatus}
    if op.id > tope:
        destino, motivo = 'pendiente', 'registrada después del congelamiento'
    elif _char(op.moneda) not in monedas:
        destino, motivo = 'dato_sucio', f'moneda fuera del catálogo: {_char(op.moneda)}'
    else:
        destino, motivo = CARGADO, ''
    return Documento('operacion', op.folio, _char(op.sucursal), op.estatus, op.fecha_operacion, huella(campos),
                     (('MXN', op.monto_mxn),), destino, motivo)


@dataclass
class Contexto:
    """Lo que una orden necesita de las demás tablas, ya leído."""
    operaciones: dict[int, tuple[str, str]]              # id → (folio FX, sucursal)
    monedas: frozenset[str]
    congelamiento: dict[str, int]                        # tabla → MAX(id) al congelamiento
    partidas_cliente: dict[int, list[Partida]] = field(default_factory=dict)        # por orden_id
    partidas_corresponsal: dict[int, list[Partida]] = field(default_factory=dict)   # por orden_id


def llave_de_orden(r: Registro, ctx: Contexto) -> tuple[str, str]:
    return (_char(r.uetr), ctx.operaciones.get(r.operacion_id, ('', ''))[1])


def _partidas(partidas: Iterable[Partida]) -> list[list]:
    return sorted([p.renglon, p.concepto, _char(p.moneda), p.monto, p.fecha_hora, p.referencia] for p in partidas)


def documento_de_orden(registros: list[Registro], ctx: Contexto) -> Documento:
    """Los registros de UNA llave de negocio → el documento, con su destino."""
    registros = sorted(registros, key=lambda r: r.id)
    tope = ctx.congelamiento['dbo.orden_pago']
    tope_corresponsal = ctx.congelamiento['dbo.partida_solicitada']
    tope_cliente = ctx.congelamiento['dbo.partida_liquidada']
    uetr, sucursal = llave_de_orden(registros[0], ctx)
    foto = [r for r in registros if r.id <= tope]
    if not foto:                                         # todo es posterior: se describe como está ahora
        foto, tope = registros, max(r.id for r in registros)
        tope_cliente = tope_corresponsal = float('inf')
    vigentes = [r for r in foto if r.estatus != REEMPLAZADA]
    vigente = vigentes[-1] if vigentes else foto[-1]
    cliente = [p for p in ctx.partidas_cliente.get(vigente.id, []) if p.id <= tope_cliente]
    corresponsal = [p for p in ctx.partidas_corresponsal.get(vigente.id, []) if p.id <= tope_corresponsal]
    if registros[0].id > ctx.congelamiento['dbo.orden_pago']:
        destino, motivo = 'pendiente', 'registrada después del congelamiento'
    elif len(vigentes) > 1:
        destino, motivo = 'duplicado', f'{len(vigentes)} registros vigentes: ids {[r.id for r in vigentes]}'
    elif not vigentes:
        destino, motivo = 'dato_sucio', 'ningún registro vigente'
    elif vigente.operacion_id not in ctx.operaciones:
        destino, motivo = 'dato_sucio', f'operación {vigente.operacion_id} inexistente'
    elif _char(vigente.moneda) not in ctx.monedas:
        destino, motivo = 'dato_sucio', f'moneda fuera del catálogo: {_char(vigente.moneda)}'
    elif len({r.folio for r in foto}) > 1:
        destino, motivo = 'dato_sucio', f're-registro con otro folio: {sorted({r.folio for r in foto})}'
    elif any(p.id <= tope_corresponsal for r in foto if r.id != vigente.id
             for p in ctx.partidas_corresponsal.get(r.id, [])):
        destino, motivo = 'dato_sucio', 'liquidación sobre un registro reemplazado'
    elif not cliente:
        destino, motivo = 'sin_detalle', 'el registro vigente no trae partidas del cliente'
    else:
        destino, motivo = CARGADO, ''
    operacion = ctx.operaciones.get(vigente.operacion_id, (None, ''))[0]
    campos = {'tipo': 'orden', 'uetr': uetr, 'sucursal': sucursal, 'folio': vigente.folio, 'operacion': operacion,
              'registros': len(foto), 'primer_registro': foto[0].fecha_registro,
              'referencia_mt103': vigente.referencia_mt103, 'fecha_registro': vigente.fecha_registro,
              'fecha_envio': vigente.fecha_envio, 'fecha_valor': vigente.fecha_valor,
              'bic_corresponsal': _char(vigente.bic_corresponsal),
              'bic_intermediario': _char(vigente.bic_intermediario), 'beneficiario': vigente.beneficiario,
              'cuenta_beneficiario': vigente.cuenta_beneficiario, 'moneda': _char(vigente.moneda),
              'monto': vigente.monto, 'gastos': _char(vigente.gastos),
              'codigo_proposito': _char(vigente.codigo_proposito), 'estatus': vigente.estatus,
              'horas_liquidacion': vigente.horas_liquidacion,
              'partidas_cliente': _partidas(cliente), 'partidas_corresponsal': _partidas(corresponsal)}
    primero = min(r.fecha_registro for r in registros)
    return Documento('orden', uetr, sucursal, vigente.estatus, primero, huella(campos),
                     ((_char(vigente.moneda), vigente.monto),), destino, motivo)


def documentos_de_orden(registros: Iterable[Registro], ctx: Contexto) -> list[Documento]:
    por_llave: dict[tuple[str, str], list[Registro]] = defaultdict(list)
    for r in registros:
        por_llave[llave_de_orden(r, ctx)].append(r)
    return [documento_de_orden(regs, ctx) for _llave, regs in sorted(por_llave.items())]


# ── estatus en una foto pasada, con la bitácora ─────────────────────────────────────────────────────────────────

def estatus_en(actual: dict[int, str], cambios: Iterable[tuple[int, int, str | None, str | None]]) -> dict[int, str]:
    """El estatus de cada registro en una foto pasada: el actual, deshecho con los cambios («U») que la bitácora anotó
    DESPUÉS de esa foto (`cambios` = (id de bitácora, llave, estatus anterior, estatus nuevo)).

    Falla si la bitácora no explica el estatus actual (un cambio sin bitácora) o si deshace un cambio del job nocturno:
    ése también escribe horas_liquidacion, que la bitácora no guarda, y la foto no se podría reconstruir."""
    resultado = dict(actual)
    for id_bitacora, llave, anterior, nuevo in sorted(cambios, reverse=True):
        if llave not in resultado:
            continue
        if resultado[llave] != nuevo:
            raise ValueError(f'la bitácora {id_bitacora} dice que la orden {llave} pasó a {nuevo}, pero estaba en '
                             f'{resultado[llave]}: hay un cambio sin bitácora')
        if nuevo in DEL_JOB:
            raise ValueError(f'la bitácora {id_bitacora} concilia la orden {llave} después de la foto: '
                             'horas_liquidacion cambió y la bitácora no guarda su valor anterior')
        resultado[llave] = anterior
    return resultado


# ── agregados por tipo + estado + mes ───────────────────────────────────────────────────────────────────────────

class _Acumulado:
    __slots__ = ('documentos', 'montos', 'lineas')

    def __init__(self):
        self.documentos = 0
        self.montos: dict[str, Decimal] = defaultdict(Decimal)
        self.lineas: list[str] = []

    def sumar(self, d: Documento) -> None:
        self.documentos += 1
        for moneda, monto in d.montos:
            self.montos[moneda] += monto
        self.lineas.append(f'{d.documento}|{d.sucursal}|{d.huella}')

    def cerrar(self) -> dict:
        return {'documentos': self.documentos,
                'montos': {m: format(v, 'f') for m, v in sorted(self.montos.items())},
                'huella': hashlib.sha256('\n'.join(sorted(self.lineas)).encode('utf-8')).hexdigest()}


def agregar(documentos: Iterable[Documento], utc: bool = False) -> dict:
    """Cifras por tipo (totales globales) y por tipo + estado + mes, cada una con su origen, lo cargado y lo que no
    viaja por motivo. `utc=True` reproduce la grieta: el mismo documento, el mes de su instante en UTC."""
    tipos: dict[str, dict[str, _Acumulado]] = defaultdict(lambda: defaultdict(_Acumulado))
    grupos: dict[tuple[str, str, str], dict[str, _Acumulado]] = defaultdict(lambda: defaultdict(_Acumulado))
    for d in documentos:
        grupo = (d.tipo, d.estado, d.mes_utc if utc else d.mes)
        for destino in ('origen', d.destino):
            tipos[d.tipo][destino].sumar(d)
            grupos[grupo][destino].sumar(d)

    def bloque(acumulados: dict[str, _Acumulado], todos: bool) -> dict:
        vacio = _Acumulado()
        b = {'origen': acumulados['origen'].cerrar(), CARGADO: acumulados.get(CARGADO, vacio).cerrar()}
        b['no_viaja'] = {m: acumulados[m].cerrar() for m in MOTIVOS if todos or m in acumulados}
        return b

    return {
        'mes': 'utc' if utc else 'local',
        'tipos': {t: bloque(tipos[t], True) for t in sorted(tipos)},
        'grupos': [{'tipo': t, 'estado': e, 'mes': m, **bloque(grupos[(t, e, m)], False)}
                   for t, e, m in sorted(grupos)],
    }


def cuadre(cifras: dict) -> list[str]:
    """cargado + no viaja = origen, en documentos y en montos, por tipo y por grupo. Vacío = cuadra."""
    faltas = []
    bloques = [(f'tipo {t}', b) for t, b in cifras['tipos'].items()]
    bloques += [(f"{g['tipo']} · {g['estado']} · {g['mes']}", g) for g in cifras['grupos']]
    for nombre, b in bloques:
        partes = [b[CARGADO], *b['no_viaja'].values()]
        documentos = sum(p['documentos'] for p in partes)
        montos: dict[str, Decimal] = defaultdict(Decimal)
        for p in partes:
            for moneda, monto in p['montos'].items():
                montos[moneda] += Decimal(monto)
        if documentos != b['origen']['documentos'] or _sin_ceros(montos) != _sin_ceros(b['origen']['montos']):
            faltas.append(f"{nombre}: cargado + no viaja = {documentos} documentos y {dict(_sin_ceros(montos))}; "
                          f"origen = {b['origen']['documentos']} y {b['origen']['montos']}")
    return faltas


def _sin_ceros(montos: dict) -> dict[str, Decimal]:
    return {m: Decimal(v) for m, v in montos.items() if Decimal(v) != 0}


def diferencias(a: dict, b: dict) -> dict:
    """Qué cambia entre dos cifras (origen contra destino, o contra un control): por tipo (totales globales del
    origen) y por grupo tipo + estado + mes."""
    globales = []
    for tipo in sorted(set(a['tipos']) | set(b['tipos'])):
        x, y = a['tipos'].get(tipo, {}).get('origen'), b['tipos'].get(tipo, {}).get('origen')
        if x != y:
            globales.append({'tipo': tipo, 'a': x, 'b': y,
                             'distinto': sorted(k for k in ('documentos', 'montos', 'huella')
                                                if (x or {}).get(k) != (y or {}).get(k))})
    ga = {(g['tipo'], g['estado'], g['mes']): g['origen'] for g in a['grupos']}
    gb = {(g['tipo'], g['estado'], g['mes']): g['origen'] for g in b['grupos']}
    por_grupo = [{'tipo': t, 'estado': e, 'mes': m, 'a': ga.get((t, e, m)), 'b': gb.get((t, e, m))}
                 for t, e, m in sorted(set(ga) | set(gb)) if ga.get((t, e, m)) != gb.get((t, e, m))]
    return {'globales': globales, 'por_grupo': por_grupo}


def diferencias_por_documento(a: Iterable[Documento], b: Iterable[Documento]) -> dict:
    ha = {d.llave: d.huella for d in a}
    hb = {d.llave: d.huella for d in b}
    distintos = sorted(k for k in set(ha) & set(hb) if ha[k] != hb[k])
    solo_a, solo_b = sorted(set(ha) - set(hb)), sorted(set(hb) - set(ha))
    return {'distintos': len(distintos), 'solo_en_a': len(solo_a), 'solo_en_b': len(solo_b),
            'muestra_distintos': [list(k) for k in distintos[:MUESTRA]],
            'muestra_solo_en_a': [list(k) for k in solo_a[:MUESTRA]],
            'muestra_solo_en_b': [list(k) for k in solo_b[:MUESTRA]]}


def duplicados_por_documento(documentos: Iterable[Documento]) -> list[str]:
    """Llaves de negocio con más de un registro vigente, o que aparecen dos veces: debe ser 0."""
    vistas: dict[tuple[str, str, str], int] = defaultdict(int)
    nombradas = set()
    for d in documentos:
        vistas[d.llave] += 1
        if d.destino == 'duplicado':
            nombradas.add(d.llave)
    nombradas |= {k for k, n in vistas.items() if n > 1}
    return ['/'.join(k) for k in sorted(nombradas)]


# ── conciliación del delta por llave de negocio (criterio 7) ────────────────────────────────────────────────────

class Vigencia(NamedTuple):
    """Un registro de orden en una foto: su id, su llave de negocio y su estatus EN esa foto."""
    id: int
    llave: tuple[str, str]
    estatus: str


def conciliar(al_corte: Iterable[Vigencia], delta: Iterable[Vigencia], por: str) -> dict:
    """Une lo que trae la carga histórica (la foto del corte, con su estatus de ENTONCES) con lo que trae el delta
    (las filas nuevas, ids > corte, con su estatus al congelamiento).

    - `por='llave'`: la llave de negocio decide. Si el delta trae registros de un documento, ésos lo describen y los
      del corte SALEN (el pendiente re-registrado el día del corte reaparece con id nuevo y el MISMO documento).
    - `por='id'` (control negativo): se unen por id. El delta por id sólo trae altas, así que el registro viejo, que
      en el corte estaba vigente, se queda vigente: el documento queda dos veces.

    Duplicado = una llave con más de un registro vigente después de unir."""
    al_corte, delta = list(al_corte), list(delta)
    if por == 'id':
        unidos = {r.id: r for r in al_corte} | {r.id: r for r in delta}
        vigentes = [r for r in unidos.values() if r.estatus != REEMPLAZADA]
        salen: list[int] = []
    elif por == 'llave':
        con_delta = {r.llave for r in delta}
        salen = sorted(r.id for r in al_corte if r.llave in con_delta and r.estatus != REEMPLAZADA)
        vigentes = [r for r in al_corte if r.llave not in con_delta and r.estatus != REEMPLAZADA]
        vigentes += [r for r in delta if r.estatus != REEMPLAZADA]
    else:
        raise ValueError(f'conciliar por {por!r}: sólo «llave» o «id»')
    por_llave: dict[tuple[str, str], list[int]] = defaultdict(list)
    for r in vigentes:
        por_llave[r.llave].append(r.id)
    duplicados = {k: sorted(v) for k, v in sorted(por_llave.items()) if len(v) > 1}
    return {'por': por, 'documentos': len(por_llave), 'registros_que_salen': len(salen),
            'muestra_registros_que_salen': salen[:MUESTRA], 'duplicados': len(duplicados),
            'muestra_duplicados': [{'documento': k[0], 'sucursal': k[1], 'ids': v}
                                   for k, v in list(duplicados.items())[:MUESTRA]],
            'llaves_duplicadas': ['/'.join(k) for k in duplicados]}


# ── controles negativos de las cifras ───────────────────────────────────────────────────────────────────────────

def alterar_un_centavo(registros: list[Registro]) -> list[Registro]:
    """El mismo documento con el monto de su registro vigente un centavo arriba."""
    vigente = max((r for r in registros if r.estatus != REEMPLAZADA), key=lambda r: r.id)
    return [r._replace(monto=r.monto + Decimal('0.01')) if r.id == vigente.id else r for r in registros]


def duplicar_vigente(registros: list[Registro], nuevo_id: int) -> list[Registro]:
    """Un segundo registro vigente del mismo documento (la misma llave de negocio con otro id)."""
    vigente = max((r for r in registros if r.estatus != REEMPLAZADA), key=lambda r: r.id)
    return [*registros, vigente._replace(id=nuevo_id)]


def sustituir(documentos: list[Documento], nuevo: Documento) -> list[Documento]:
    return [nuevo if d.llave == nuevo.llave else d for d in documentos]


def renglones_csv(documentos: Iterable[Documento]) -> Iterable[str]:
    yield ','.join(CSV_COLUMNAS) + '\n'
    for d in sorted(documentos, key=lambda d: d.llave):
        for valor in (d.documento, d.sucursal, d.estado):
            if ',' in valor or '\n' in valor:
                raise ValueError(f'valor que no cabe en el CSV: {valor!r}')
        yield f'{d.tipo},{d.documento},{d.sucursal},{d.estado},{d.mes},{d.destino},{d.huella}\n'
