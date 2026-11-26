"""Delta del MISMO día tras el congelamiento (S3 paso 4; ADR 0013 y 0016; criterios 5, 7, 8 y 12). Sin base: aquí
están qué entra, cómo se derivan los cambios sobre las filas del corte, el catálogo, la reversa, las guardas y las
comparaciones; la lectura y la escritura las hace `corte/runbook_delta.py`.

- **Base:** el destino que deja la carga histórica ya cerrada (36 meses, `setval`, folios con margen, llaves foráneas).
- **Qué entra, POR ID:** en las 5 tablas con identidad, los ids entre el corte (MAX(id) del respaldo) y el
  congelamiento (MAX(id) de la foto del legado vivo), los dos medidos por dos caminos en el paso 2. Nunca por fecha: la
  sucursal que reenvía su archivo fechado hacia atrás deja altas con id nuevo y fecha vieja, y un delta por fecha las
  pierde. La selección se compara contra el rango de la identidad y lo que falta se nombra.
- **Cambios sobre filas ≤ corte:** los dice la bitácora posterior al corte y hasta el congelamiento: re-registros (la
  fila vieja pasa a REEMPLAZADA) y liquidaciones (ENVIADA → LIQUIDADA); si el job conciliara, también
  `horas_liquidacion`. Van como UPDATE de las columnas que el legado escribe sobre una orden ya registrada (`MUTABLES`)
  y de nada más. Se comprueban fila por fila contra el origen: las filas distintas son EXACTAMENTE las que la bitácora
  anota, el valor del destino es el primer «anterior» de su cadena y el del origen, el último «nuevo».
- **El estado es el del congelamiento:** lo que la bitácora anotó DESPUÉS se deshace (`cifras.estatus_en`) y queda,
  con las filas de id > congelamiento, para el barrido posterior al corte.
- **Catálogo:** las monedas de la foto del congelamiento contra las del destino: altas (INSERT) y la columna que el
  legado cambia (`activa`). Otra columna distinta, o una moneda que desaparece, detiene el delta.
- **Conciliación por llave de negocio (uetr + sucursal):** el re-registro trae id nuevo, el registro viejo sale
  (REEMPLAZADA) y queda un solo registro vigente por documento. Se comprueba en el destino.
- **Reversa:** generada ANTES de aplicar: los rangos que se borran, los VALORES PREVIOS de cada fila actualizada y de
  cada moneda, las secuencias, los folios y la huella previa del destino.
- **Lo derivado por id** (correcciones o enriquecimientos aplicados después de cargar) se RE-ARMA después del delta y
  de su reversa, nunca se reusa: `DERIVADOS`. Hoy el destino no tiene nada derivado: el gancho corre vacío.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import NamedTuple

from corte import carga, cifras
from corte.carga import CON_IDENTIDAD, TABLAS

MUESTRA = 20

# Columnas que el legado escribe sobre una fila YA registrada (legado/sql/05_procedimientos.sql y legado/vivo), las
# únicas que el delta puede actualizar:
# - orden_pago: sp_registrar_orden (REEMPLAZADA), sp_registrar_liquidacion (LIQUIDADA) y el job: sp_conciliar
#   (CONCILIADA o DIFERENCIA, con horas_liquidacion) y el vencimiento (VENCIDA);
# - moneda: la baja (UPDATE dbo.moneda SET activa = 0).
# `operacion.estatus` también lo escribe un procedimiento (sp_reflejar_estatus_operacion), pero sin bitácora: no se
# puede derivar. Si corriera dentro de la ventana, lo ven las cifras por documento (límite declarado).
MUTABLES: dict[str, tuple[str, ...]] = {'orden_pago': ('estatus', 'horas_liquidacion'), 'moneda': ('activa',)}

# Al insertar, primero lo referenciado (las llaves foráneas del cierre ya están puestas); al borrar, al revés.
ORDEN_INSERTAR = tuple(t.nombre for t in CON_IDENTIDAD)
ORDEN_BORRAR = tuple(reversed(ORDEN_INSERTAR))

# ── consultas al ORIGEN (el legado vivo, SQL Server). Literales ─────────────────────────────────────────────────

# Los «U» de orden_pago posteriores al corte (también los posteriores al congelamiento: ésos se separan aquí).
CAMBIOS = """SELECT id, llave, estatus_anterior, estatus_nuevo FROM dbo.bitacora
WHERE tabla = N'orden_pago' AND accion = 'U' AND id > %(corte)s ORDER BY id"""

# Las órdenes posteriores al congelamiento: quedan fuera del delta y van listadas para el barrido.
ORDENES_POSTERIORES = """SELECT id, uetr, folio, fecha_registro, estatus FROM dbo.orden_pago
WHERE id > %(congelamiento)s ORDER BY id"""
OPERACIONES_POSTERIORES = """SELECT id, folio, sucursal, fecha_operacion FROM dbo.operacion
WHERE id > %(congelamiento)s ORDER BY id"""
POSTERIORES: dict[str, str] = {
    'partida_solicitada': 'SELECT id FROM dbo.partida_solicitada WHERE id > %(congelamiento)s ORDER BY id',
    'partida_liquidada': 'SELECT id FROM dbo.partida_liquidada WHERE id > %(congelamiento)s ORDER BY id',
    'bitacora': 'SELECT id FROM dbo.bitacora WHERE id > %(congelamiento)s ORDER BY id',
}


# ── el congelamiento ────────────────────────────────────────────────────────────────────────────────────────────

def congelamiento(medido: dict, vivo: dict) -> tuple[dict[str, int], list[str]]:
    """El congelamiento por tabla: el MAX(id) medido en el paso 2 (`corte/cifras/corte.json`) y el de la foto del vivo
    de ESTA corrida tienen que ser el mismo; si no, el legado que se lee no es el que se midió."""
    del_paso_2 = {t.removeprefix('dbo.'): v['por_identidad']['congelamiento'] for t, v in medido['tablas'].items()
                  if v.get('por_identidad')}
    de_la_foto = {t: (vivo.get('al_congelamiento', {}).get(t) or {}).get('max_id') for t in del_paso_2}
    faltas = [f'{t}: el congelamiento medido en el paso 2 es {n} y la foto del vivo dice {de_la_foto[t]}'
              for t, n in sorted(del_paso_2.items()) if de_la_foto[t] != n]
    return del_paso_2, faltas


def guarda_del_corte(maximos: dict[str, int], corte: dict[str, int]) -> list[str]:
    """Sólo ids > corte: el destino tiene que llegar EXACTAMENTE al corte. Si ya llega más lejos, el delta (o parte de
    él) ya entró y repetirlo duplicaría; si no llega, la base no está cerrada."""
    return [f'{t}: el destino llega al id {maximos[t]} y el corte es {corte[t]}'
            for t in ORDEN_INSERTAR if maximos[t] != corte[t]]


# ── cambios sobre las filas del corte, por la bitácora ──────────────────────────────────────────────────────────

class Cambio(NamedTuple):
    bitacora: int
    llave: int
    anterior: str | None
    nuevo: str | None


def cambios_por_bitacora(filas: Iterable[tuple], corte: dict[str, int], tope: dict[str, int]) -> dict:
    """Los «U» de orden_pago con id de bitácora > corte → por fila de la orden:
    - `al_corte`: filas ≤ corte cambiadas hasta el congelamiento (lo que el delta ACTUALIZA), con su cadena;
    - `del_delta`: filas del delta (corte < id ≤ congelamiento) cambiadas el mismo día (entran ya con su estado);
    - `posteriores`: cambios anotados DESPUÉS del congelamiento sobre filas ≤ congelamiento (los deshace la foto y
      quedan para el barrido). Los de filas posteriores al congelamiento ni se miran: esas filas no entran.
    Una cadena rota (el «anterior» de un paso no es el «nuevo» del anterior) es una falta."""
    al_corte: dict[int, list[Cambio]] = {}
    del_delta: dict[int, list[Cambio]] = {}
    posteriores: list[Cambio] = []
    faltas: list[str] = []
    for c in sorted(Cambio(int(b), int(llave), a, n) for b, llave, a, n in filas):
        if c.bitacora <= corte['bitacora'] or c.llave > tope['orden_pago']:
            continue
        if c.bitacora > tope['bitacora']:
            posteriores.append(c)
            continue
        cadena = (al_corte if c.llave <= corte['orden_pago'] else del_delta).setdefault(c.llave, [])
        if cadena and cadena[-1].nuevo != c.anterior:
            faltas.append(f'orden {c.llave}: la bitácora {c.bitacora} dice {c.anterior} → {c.nuevo}, pero el paso '
                          f'anterior ({cadena[-1].bitacora}) la dejó en {cadena[-1].nuevo}: cadena rota')
        cadena.append(c)
    return {'al_corte': al_corte, 'del_delta': del_delta, 'posteriores': posteriores, 'faltas': faltas}


def resumen_de_cambios(cambios: dict) -> dict:
    """Cuántas filas cambian y a qué estado final, por grupo."""
    def conteo(grupo: dict[int, list[Cambio]]) -> dict[str, int]:
        resultado: dict[str, int] = {}
        for cadena in grupo.values():
            resultado[str(cadena[-1].nuevo)] = resultado.get(str(cadena[-1].nuevo), 0) + 1
        return dict(sorted(resultado.items()))
    return {'al_corte': conteo(cambios['al_corte']), 'del_delta': conteo(cambios['del_delta']),
            'posteriores': len(cambios['posteriores'])}


def al_congelamiento(filas: list[tuple], posteriores: Iterable[Cambio]) -> tuple[list[tuple], list[str]]:
    """Las filas de orden_pago tal como estaban al congelamiento: el estatus actual, deshecho con los cambios que la
    bitácora anotó después (`cifras.estatus_en`). Si uno de ésos es del job, `horas_liquidacion` no se puede
    reconstruir y es una falta (no se reconstruye mal)."""
    i = TABLAS['orden_pago'].nombres.index('estatus')
    actual = {f[0]: f[i] for f in filas}
    try:
        foto = cifras.estatus_en(actual, [tuple(c) for c in posteriores])
    except ValueError as error:
        return filas, [str(error)]
    return [(*f[:i], foto[f[0]], *f[i + 1:]) for f in filas], []


def actualizaciones(origen: Iterable[tuple], destino: Iterable[tuple], al_corte: dict[int, list[Cambio]]
                    ) -> tuple[dict[int, dict], list[str]]:
    """Filas ≤ corte de orden_pago: el origen AL CONGELAMIENTO contra el destino (la foto del corte). Las filas
    distintas tienen que ser exactamente las que la bitácora anota, distintas sólo en `MUTABLES`, con el valor del
    destino igual al primer «anterior» de su cadena y el del origen igual al último «nuevo». Devuelve, por id, los
    valores nuevos de las columnas mutables."""
    nombres = TABLAS['orden_pago'].nombres
    mutables = MUTABLES['orden_pago']
    i = nombres.index('estatus')
    o = {f[0]: f for f in origen}
    d = {f[0]: f for f in destino}
    faltas: list[str] = []
    if set(o) != set(d):
        faltas.append(f'orden_pago ≤ corte: {len(set(o) - set(d))} ids sólo en el origen '
                      f'{sorted(set(o) - set(d))[:MUESTRA]} y {len(set(d) - set(o))} sólo en el destino '
                      f'{sorted(set(d) - set(o))[:MUESTRA]}')
    distintas = sorted(k for k in set(o) & set(d) if o[k] != d[k])
    actualizar: dict[int, dict] = {}
    for k in distintas:
        columnas = [n for n, a, b in zip(nombres, o[k], d[k]) if a != b]
        fuera = [c for c in columnas if c not in mutables]
        if k not in al_corte:
            faltas.append(f'orden {k}: cambió {columnas} ({d[k][i]} → {o[k][i]}) y la bitácora no lo anota')
            continue
        if fuera:
            faltas.append(f'orden {k}: cambió {fuera}, que el legado no escribe sobre una orden ya registrada')
        actualizar[k] = {c: o[k][nombres.index(c)] for c in mutables}
    for k, cadena in sorted(al_corte.items()):
        if k not in d or k not in o:
            continue
        if d[k][i] != cadena[0].anterior:
            faltas.append(f'orden {k}: el destino la tiene en {d[k][i]} y la bitácora {cadena[0].bitacora} parte de '
                          f'{cadena[0].anterior}: el destino no está en la foto del corte')
        if o[k][i] != cadena[-1].nuevo:
            faltas.append(f'orden {k}: la bitácora la deja en {cadena[-1].nuevo} y el origen al congelamiento dice '
                          f'{o[k][i]}')
    return actualizar, faltas


# ── catálogo ────────────────────────────────────────────────────────────────────────────────────────────────────

def catalogo(foto: list | None, destino: Iterable[tuple], vivo: Iterable[tuple]) -> dict:
    """Las monedas al congelamiento (la foto del vivo) contra el destino: altas y cambios de `activa`. Lo que cambió
    después del congelamiento (el legado de ahora contra la foto) queda para el barrido."""
    t = TABLAS['moneda']
    if foto is None:
        return {'insertar': [], 'actualizar': {}, 'posteriores': [], 'faltas': [
            'la foto del congelamiento no trae el catálogo: corre de nuevo `python -m legado.vivo` (lo anota desde '
            'S3, paso 4)']}
    cong = {f[0]: tuple(f) for f in foto}
    d = {f[0]: tuple(f) for f in destino}
    v = {f[0]: tuple(f) for f in vivo}
    faltas = [f'moneda {c}: está en el destino y no en el congelamiento (el legado no borra monedas)'
              for c in sorted(set(d) - set(cong))]
    actualizar = {}
    for c in sorted(set(d) & set(cong)):
        if d[c] == cong[c]:
            continue
        columnas = [n for n, a, b in zip(t.nombres, d[c], cong[c]) if a != b]
        fuera = [x for x in columnas if x not in MUTABLES['moneda']]
        if fuera:
            faltas.append(f'moneda {c}: cambió {fuera}, que el legado no actualiza')
        actualizar[c] = {x: cong[c][t.nombres.index(x)] for x in MUTABLES['moneda']}
    posteriores = sorted(c for c in set(cong) | set(v) if cong.get(c) != v.get(c))
    return {'insertar': [cong[c] for c in sorted(set(cong) - set(d))], 'actualizar': actualizar,
            'posteriores': posteriores, 'faltas': faltas}


# ── la selección: por id, nunca por fecha ───────────────────────────────────────────────────────────────────────

def comparar_seleccion(por_id: Iterable[int], seleccion: Iterable[int], nombres: dict[int, str] | None = None) -> dict:
    """La selección de un delta contra el rango de la identidad: lo que le falta y lo que le sobra, nombrado."""
    a, b = set(por_id), set(seleccion)
    nombres = nombres or {}

    def nombrar(ids):
        return [f'{i} ({nombres[i]})' if i in nombres else str(i) for i in sorted(ids)]
    return {'faltan': len(a - b), 'sobran': len(b - a), 'muestra_faltan': nombrar(a - b)[:MUESTRA],
            'muestra_sobran': nombrar(b - a)[:MUESTRA], 'coincide': a == b}


def con_seleccion(d: dict, tabla: str, ids: Iterable[int], nombre: str) -> dict:
    """El mismo plan con el lote de UNA tabla tomado por otra selección (el control del delta por fecha): sólo las filas
    del rango que la selección trae, y los ids que trae de más quedan anotados para que la comparación los nombre."""
    elegidos = sorted(set(ids))
    dentro = set(elegidos)
    lote = [f for f in d['lotes'][tabla] if f[0] in dentro]
    otro = {**d, 'seleccion': nombre, 'seleccion_ids': {**d.get('seleccion_ids', {}), tabla: elegidos},
            'lotes': {**d['lotes'], tabla: lote},
            'rangos': {**d['rangos'], tabla: {**d['rangos'][tabla], 'filas': len(lote)}},
            'huellas_origen': {**d['huellas_origen'], tabla: carga.huella_de_filas(TABLAS[tabla], lote)}}
    otro['sha'] = plan_sha(otro)
    return otro


# ── folios: 0 choques ───────────────────────────────────────────────────────────────────────────────────────────

def choques_de_folio(siguiente: dict[str, int], ya_usados: dict[str, int], en_destino: dict[str, int | None],
                     posteriores: dict[str, list[str]] | None = None) -> list[str]:
    """El folio que el TO-BE numeraría (`siguiente` del destino) contra el último que YA se usó: por el legado (su
    `siguiente` de ahora menos uno, también después del congelamiento) y en el destino. Cada serie con choque se nombra
    con el rango y, si los hay, los folios posteriores al congelamiento que caen dentro."""
    faltas = []
    for serie in sorted(siguiente):
        ultimo = max(ya_usados.get(serie, 1) - 1, en_destino.get(serie) or 0)
        if siguiente[serie] <= ultimo:
            dentro = [f for f in (posteriores or {}).get(serie, [])
                      if (carga.numero_de_folio(f, serie) or 0) >= siguiente[serie]]
            faltas.append(f'folio {serie}: el TO-BE numeraría desde {serie}-{siguiente[serie]:09d} y ya se usó hasta '
                          f'{serie}-{ultimo:09d}: {ultimo - siguiente[serie] + 1:,} folios chocan'
                          + (f', entre ellos los posteriores al congelamiento {dentro}' if dentro else ''))
    return faltas


# ── el plan del delta y su reversa ──────────────────────────────────────────────────────────────────────────────

def plan_sha(d: dict) -> str:
    """Lo que se aplica: rangos, la huella de cada lote, los valores nuevos de cada fila actualizada, el catálogo y las
    secuencias. Ata el ensayo con lo que se aplica."""
    contenido = {k: d[k] for k in ('corte', 'congelamiento', 'rangos', 'huellas_origen', 'actualizar', 'catalogo',
                                   'secuencias')}
    texto = json.dumps(contenido, sort_keys=True, ensure_ascii=False, default=_texto)
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()


def _texto(valor) -> str:
    if isinstance(valor, Decimal):
        return format(valor, 'f')
    if isinstance(valor, datetime):
        return valor.isoformat()
    raise TypeError(f'sin forma de texto: {type(valor).__name__}')


def reversa(d: dict, previa: dict, anteriores: dict) -> dict:
    """La reversa del delta, generada ANTES de aplicarlo: los rangos que se borran, los VALORES PREVIOS de cada fila
    que se actualiza (leídos del destino), las monedas que se dan de alta (se borran) o cambian (se restauran), las
    secuencias, los folios y la huella previa con la que debe quedar el destino."""
    return {
        'version': 1, 'plan_sha': d['sha'], 'generada_utc': datetime.now(timezone.utc).isoformat(),
        'borrar': {t: {'desde': r['desde'], 'hasta': r['hasta']} for t, r in d['rangos'].items() if r['filas']},
        'restaurar': {'orden_pago': {str(k): {c: _jsonable(v) for c, v in sorted(anteriores['orden_pago'][k].items())}
                                     for k in sorted(d['actualizar'])}},
        'catalogo': {'borrar': [f[0] for f in d['catalogo']['insertar']],
                     'restaurar': {c: {x: _jsonable(v) for x, v in anteriores['moneda'][c].items()}
                                   for c in sorted(d['catalogo']['actualizar'])}},
        'secuencias': previa['secuencias'],
        'folios': {s: v['siguiente'] for s, v in previa['folios'].items()},
        'huella_previa': {'tablas': previa['tablas'], 'secuencias': previa['secuencias'], 'folios': previa['folios']},
    }


def _jsonable(valor):
    return format(valor, 'f') if isinstance(valor, Decimal) else valor


def valor_de(tabla: str, columna: str, valor):
    """De la reversa guardada (JSON) al tipo de la columna: los decimales viajan como texto para no perder la escala."""
    tipo = next(c.tipo for c in TABLAS[tabla].columnas if c.nombre == columna)
    if valor is not None and tipo.startswith('decimal'):
        return Decimal(valor)
    return valor


def diferencias(previa: dict, ahora: dict) -> list[str]:
    """Qué cambió entre dos huellas del destino, también en los folios: vacío = es la misma."""
    faltas = carga.diferencias_de_huella(previa, ahora)
    a, b = previa.get('folios', {}), ahora.get('folios', {})
    faltas += [f'folio {s}: {a.get(s)} → {b.get(s)}' for s in sorted(set(a) | set(b)) if a.get(s) != b.get(s)]
    return faltas


# ── cifras de control contra las del paso 2 (criterio 8) ────────────────────────────────────────────────────────

_VACIO = cifras._Acumulado().cerrar()


def contra_el_paso_2(destino: dict, paso_2: dict) -> dict:
    """`destino` = `cifras.agregar(documentos del destino)`: todo lo que hay en el destino cae en «origen» y lo que
    además clasifica como cargado, en «cargado». `paso_2` = las cifras versionadas del paso 2. Por tipo y por cada grupo
    tipo + estado + mes:
    - lo del destino = lo CARGADO del paso 2 (documentos, montos por moneda y huella del grupo);
    - todo lo del destino clasifica como cargado (ningún duplicado, sin detalle ni dato sucio);
    - destino + lo que no viaja en el paso 2 = el origen del paso 2 (documentos y montos)."""
    faltas: list[str] = []
    pares = [(f'tipo {t}', destino['tipos'].get(t), paso_2['tipos'].get(t))
             for t in sorted(set(destino['tipos']) | set(paso_2['tipos']))]
    gd = {(g['tipo'], g['estado'], g['mes']): g for g in destino['grupos']}
    gp = {(g['tipo'], g['estado'], g['mes']): g for g in paso_2['grupos']}
    pares += [(' · '.join(k), gd.get(k), gp.get(k)) for k in sorted(set(gd) | set(gp))]
    distintos = []
    for nombre, d, p in pares:
        if p is None:
            faltas.append(f'{nombre}: está en el destino y no en el paso 2')
            distintos.append(nombre)
            continue
        en_destino = d['origen'] if d else _VACIO
        cargado_destino = d[cifras.CARGADO] if d else _VACIO
        if en_destino != p[cifras.CARGADO]:
            faltas.append(f"{nombre}: destino {en_destino['documentos']} documentos {en_destino['montos']} "
                          f"huella {en_destino['huella'][:12]} ≠ cargado del paso 2 {p[cifras.CARGADO]['documentos']} "
                          f"{p[cifras.CARGADO]['montos']} huella {p[cifras.CARGADO]['huella'][:12]}")
            distintos.append(nombre)
        if cargado_destino != en_destino:
            sobran = en_destino['documentos'] - cargado_destino['documentos']
            faltas.append(f'{nombre}: {sobran} documentos del destino no clasifican como cargados')
        documentos = en_destino['documentos'] + sum(b['documentos'] for b in p['no_viaja'].values())
        montos: dict[str, Decimal] = {}
        for bloque in (en_destino, *p['no_viaja'].values()):
            for moneda, monto in bloque['montos'].items():
                montos[moneda] = montos.get(moneda, Decimal(0)) + Decimal(monto)
        origen = {m: Decimal(v) for m, v in p['origen']['montos'].items()}
        if documentos != p['origen']['documentos'] or _sin_ceros(montos) != _sin_ceros(origen):
            faltas.append(f"{nombre}: destino + no viaja = {documentos} documentos; origen del paso 2 = "
                          f"{p['origen']['documentos']}")
    tipos = {t: {'destino': (destino['tipos'].get(t) or {}).get('origen', _VACIO)['documentos'],
                 'cargado_paso_2': b[cifras.CARGADO]['documentos'],
                 'no_viaja_paso_2': {m: v['documentos'] for m, v in b['no_viaja'].items()},
                 'origen_paso_2': b['origen']['documentos']} for t, b in sorted(paso_2['tipos'].items())}
    return {'tipos': tipos, 'grupos_comparados': len(set(gd) | set(gp)), 'grupos_distintos': distintos[:MUESTRA],
            'faltas': faltas, 'cuadra': not faltas}


def _sin_ceros(montos: dict[str, Decimal]) -> dict[str, Decimal]:
    return {m: v for m, v in montos.items() if v != 0}


# ── lo derivado por id se re-arma ───────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Derivado:
    """Algo que se calcula DESPUÉS de cargar y se indexa por id interno (una corrección, un enriquecimiento). Un
    re-registro cambia el id del documento: reusarlo apuntaría al registro viejo. `armar` lo reconstruye completo
    desde el destino (borrar y volver a calcular) y devuelve cuántas filas dejó."""
    nombre: str
    llave: str
    armar: Callable[[object], int]


# Hoy nada: el esquema `legado` guarda los valores CRUDOS y los parches del ADR 0007 se aplican de `legado` al TO-BE,
# fuera del corte. El gancho corre igual después del delta y de su reversa: registrar uno aquí basta para re-armarlo.
DERIVADOS: tuple[Derivado, ...] = ()


def rearmar(conexion, derivados: Iterable[Derivado] = DERIVADOS) -> dict[str, int]:
    """Re-arma TODO lo derivado (nunca un parche incremental sobre lo de antes) y devuelve las filas de cada uno."""
    return {d.nombre: d.armar(conexion) for d in derivados}
