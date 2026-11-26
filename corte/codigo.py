"""Inventario de salidas DESDE EL CÓDIGO (primera fuente del ADR 0014): todo objeto que existe en el código del
legado, con lo que lee, lo que escribe (directo y a través de lo que llama y de los triggers que dispara), sus efectos
fuera de la base y si usa reloj o SQL dinámico. Determinista: el mismo código da el mismo JSON, byte a byte.

Objetos: procedimientos, vistas, triggers y funciones de `legado/sql/`, los jobs de msdb que crean esos scripts (con
sus pasos), las interfaces de entrada (`legado/generador/interfaces.py`) y la pantalla con lo que llama
(`legado/pantalla/`). Las tablas no son objetos de la puerta (sus datos los cubren la carga y los totales del corte),
pero se listan con quién las lee y quién las escribe: es la lista de escritores de la paridad de estado (ADR 0015).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from corte import fuentes
from corte.sql import SUBSISTEMAS_EXTERNOS, Analisis, analizar, leer_scripts, relativa
from radiografia.tsql import fichas

RAIZ = Path(__file__).resolve().parents[1]
SQL = RAIZ / 'legado' / 'sql'
PANTALLA = RAIZ / 'legado' / 'pantalla'
INTERFACES = RAIZ / 'legado' / 'generador' / 'interfaces.py'
PRINCIPAL = 'BFN_DIVISAS'
ORDEN_TIPOS = ('procedimiento', 'vista', 'trigger', 'funcion', 'job', 'interfaz', 'pantalla')


@dataclass
class _Nodo:
    """Un objeto del inventario con su análisis propio (sin cerrar)."""
    id: str
    tipo: str
    fuente: str
    propio: Analisis
    extra: dict = field(default_factory=dict)


def inventario(sql: Path = SQL, pantalla: Path = PANTALLA, interfaces: Path = INTERFACES, raiz: Path = RAIZ) -> dict:
    codigo = leer_scripts(sorted(sql.glob('*.sql')), raiz, PRINCIPAL)
    conocidos = codigo.conocidos()
    nodos: dict[str, _Nodo] = {}
    disparadores: dict[str, list[tuple[str, set[str]]]] = {}

    for m in codigo.modulos:
        analisis = analizar(fichas(m.texto), conocidos, m.base, PRINCIPAL, m.inicio_cuerpo)
        extra = {}
        if m.tipo == 'trigger':
            extra = {'tabla': m.tabla, 'eventos': list(m.eventos), 'momento': m.momento}
            disparadores.setdefault(m.tabla or '', []).append((m.id, set(m.eventos)))
        nodos[m.id] = _Nodo(m.id, m.tipo, f'{m.archivo}:{m.linea}', analisis, extra)

    for job in codigo.jobs:
        propio, pasos = Analisis(), []
        for paso in job.pasos:
            analisis = Analisis()
            subsistema = paso['subsistema'].upper()
            if subsistema == 'TSQL':
                analisis = analizar(fichas(paso['comando']), conocidos, paso['base'] or 'master', PRINCIPAL)
            else:
                analisis.efectos.add(SUBSISTEMAS_EXTERNOS.get(subsistema, f'subsistema {paso["subsistema"]}'))
            propio.unir(analisis)
            pasos.append({'paso': paso['paso'], 'subsistema': paso['subsistema'], 'base': paso['base'],
                          'comando': paso['comando'], 'fuente': f'{job.archivo}:{paso["linea"]}',
                          '_analisis': analisis})
        for h in job.horarios:
            propio.reloj.add(f'horario «{h["horario"]}» (frecuencia {h["frecuencia"]}, {h["hora"]})')
        id_ = f'job:{job.nombre}'
        nodos[id_] = _Nodo(id_, 'job', f'{job.archivo}:{job.linea}', propio,
                           {'descripcion': job.descripcion, 'pasos': pasos, 'horarios': job.horarios})

    for interfaz in fuentes.interfaces_de(interfaces, raiz):
        propio = Analisis(efectos={f'archivos: {patron}' for patron in interfaz.archivos})
        id_ = f'interfaz:{interfaz.funcion}'
        nodos[id_] = _Nodo(id_, 'interfaz', f'{interfaz.archivo}:{interfaz.linea}', propio,
                           {'nombre': interfaz.nombre, 'direccion': 'entrada', 'carpeta': interfaz.carpeta,
                            'archivos': interfaz.archivos})

    rutas_pantalla = sorted(pantalla.glob('*.py'))
    consultas = fuentes.consultas_de(rutas_pantalla, raiz, conocidos, PRINCIPAL)
    propio = Analisis()
    for c in consultas:
        propio.unir(c.analisis)
    id_ = f'pantalla:{relativa(pantalla, raiz)}'
    nodos[id_] = _Nodo(id_, 'pantalla', id_.split(':', 1)[1], propio,
                       {'consultas': [{'fuente': f'{c.archivo}:{c.linea}', 'llama': sorted(c.analisis.llama),
                                       'lee': sorted(c.analisis.lee)} for c in consultas]})

    objetos = [_objeto(n, nodos, disparadores) for n in sorted(
        nodos.values(), key=lambda n: (ORDEN_TIPOS.index(n.tipo), n.id))]
    return {
        'generado_por': 'python -m corte.escribir (desde el código; no editar a mano)',
        'base': PRINCIPAL,
        'fuentes': {'sql': [relativa(p, raiz) for p in sorted(sql.glob('*.sql'))],
                    'pantalla': [relativa(p, raiz) for p in rutas_pantalla],
                    'interfaces': relativa(interfaces, raiz)},
        'por_tipo': {t: sum(1 for o in objetos if o['tipo'] == t) for t in ORDEN_TIPOS},
        'objetos': objetos,
        'escritores': _escritores(objetos),
        'tablas': _tablas(codigo.tablas, objetos),
    }


def _cerrar(id_: str, nodos: dict[str, _Nodo], disparadores: dict) -> dict:
    """Lo que el objeto hace en total: lo suyo, lo de lo que llama y lo de los triggers que disparan sus escrituras
    (y las de lo que llama), hasta un punto fijo."""
    lee: set[str] = set()
    escribe: dict[str, set[str]] = {}
    efectos: set[str] = set()
    reloj: set[str] = set()
    dinamico: set[str] = set()
    llamados: set[str] = set()
    disparados: set[str] = set()
    visitados, pendientes = {id_}, [id_]
    while pendientes:
        actual = nodos[pendientes.pop()]
        a = actual.propio
        lee |= a.lee
        for tabla, eventos in a.escribe.items():
            escribe.setdefault(tabla, set()).update(eventos)
        efectos |= a.efectos
        dinamico |= {f'{d} ({actual.id})' for d in a.sql_dinamico}
        reloj |= {r if actual.id == id_ else f'{r} ({actual.id})' for r in a.reloj}
        for llamado in sorted(a.llama):
            if llamado in nodos and llamado not in visitados:
                visitados.add(llamado)
                llamados.add(llamado)
                pendientes.append(llamado)
        for tabla, eventos in sorted(a.escribe.items()):
            for trigger, sus_eventos in disparadores.get(tabla, []):
                if trigger not in visitados and eventos & sus_eventos:
                    visitados.add(trigger)
                    disparados.add(trigger)
                    pendientes.append(trigger)
    return {'lee': sorted(lee), 'escribe': {t: sorted(e) for t, e in sorted(escribe.items())},
            'llama': sorted(llamados), 'dispara': sorted(disparados), 'efectos_externos': sorted(efectos),
            'reloj': sorted(reloj), 'sql_dinamico': sorted(dinamico)}


def _objeto(n: _Nodo, nodos: dict[str, _Nodo], disparadores: dict) -> dict:
    a = n.propio
    efectivo = _cerrar(n.id, nodos, disparadores)
    if n.tipo == 'interfaz':
        acceso = 'entrada'
    else:
        acceso = 'escribe' if efectivo['escribe'] else ('lee' if efectivo['lee'] else 'ninguno')
    objeto = {
        'id': n.id, 'tipo': n.tipo, 'fuente': n.fuente, 'acceso': acceso,
        'lee': sorted(a.lee), 'escribe': {t: sorted(e) for t, e in sorted(a.escribe.items())},
        'llama': sorted(a.llama), 'efectos_externos': sorted(a.efectos),
        'reloj': sorted(a.reloj), 'sql_dinamico': sorted(a.sql_dinamico),
        'desde_sql_dinamico': sorted(a.desde_sql_dinamico), 'identidad': sorted(a.identidad),
        'transaccion': sorted(a.transaccion), 'temporales': sorted(a.temporales),
        'efectivo': efectivo,
    }
    for clave, valor in n.extra.items():
        if clave == 'pasos':
            valor = [_paso(p, n.id, nodos, disparadores) for p in valor]
        objeto[clave] = valor
    return objeto


def _paso(paso: dict, job: str, nodos: dict[str, _Nodo], disparadores: dict) -> dict:
    """Un paso de job con su cierre propio (lo que hace ese paso, no el job entero)."""
    a: Analisis = paso['_analisis']
    temporal = f'{job}/paso:{paso["paso"]}'
    nodos[temporal] = _Nodo(temporal, 'paso', paso['fuente'], a)
    try:
        efectivo = _cerrar(temporal, nodos, disparadores)
    finally:
        del nodos[temporal]
    return {'paso': paso['paso'], 'subsistema': paso['subsistema'], 'base': paso['base'], 'comando': paso['comando'],
            'fuente': paso['fuente'], 'llama': sorted(a.llama), 'lee': sorted(a.lee),
            'escribe': {t: sorted(e) for t, e in sorted(a.escribe.items())}, 'efectos_externos': sorted(a.efectos),
            'acceso': 'escribe' if efectivo['escribe'] else ('lee' if efectivo['lee'] else 'ninguno'),
            'efectivo': efectivo}


def _escritores(objetos: list[dict]) -> list[str]:
    """Lo que escribe (ADR 0015): procedimientos, triggers, funciones y PASOS de job cuyo efecto total escribe."""
    resultado = [o['id'] for o in objetos if o['tipo'] in ('procedimiento', 'trigger', 'funcion')
                 and o['acceso'] == 'escribe']
    for o in objetos:
        if o['tipo'] == 'job':
            resultado += [f'{o["id"]}/paso:{p["paso"]}' for p in o['pasos'] if p['acceso'] == 'escribe']
    return resultado


def _tablas(tablas, objetos: list[dict]) -> dict:
    resultado = {}
    for t in sorted(tablas, key=lambda x: x.id):
        leen, escriben = set(), set()
        for o in objetos:
            unidades = [(o['id'], o)] + [(f'{o["id"]}/paso:{p["paso"]}', p) for p in o.get('pasos', [])]
            for id_, u in unidades:
                if o['tipo'] == 'job' and id_ == o['id']:
                    continue                    # el job escribe por sus pasos
                if t.id in u['lee']:
                    leen.add(id_)
                if t.id in u['escribe']:
                    escriben.add(id_)
        resultado[t.id] = {'fuente': f'{t.archivo}:{t.linea}', 'identidad': t.identidad, 'leen': sorted(leen),
                           'escriben': sorted(escriben)}
    return resultado
