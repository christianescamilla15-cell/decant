"""Parser DETERMINISTA del T-SQL del legado para el inventario de salidas (ADR 0014).

No es un parser completo de T-SQL: reusa el analizador léxico de la radiografía (`radiografia.tsql`, que ya separa
comentarios, cadenas y paréntesis) y, sobre sus fichas, lee:

- qué objetos crean los scripts, en el orden en que el legado los ejecuta (`legado/sql/*.sql`, con su `USE`):
  procedimientos, vistas, triggers (con su tabla y eventos), funciones, tablas y los jobs de msdb (`sp_add_job*`);
- de cada módulo o paso de job: qué tablas o vistas LEE (fuentes de FROM/JOIN/USING), qué ESCRIBE y con qué evento
  (INSERT, UPDATE, DELETE, MERGE, TRUNCATE, SELECT/OUTPUT INTO, resolviendo el alias de `UPDATE o … FROM`), a quién
  LLAMA (EXEC y funciones), sus efectos FUERA de la base (correo, arranque de jobs, servidores enlazados, otra base,
  archivos, sistema operativo), si usa el RELOJ del servidor, SQL DINÁMICO, `@@IDENTITY` y transacciones propias.

Lo que se arma como texto y corre con `sp_executesql` o `EXEC(…)` también se lee: el texto de sus literales se
analiza con las mismas reglas y lo que aparece SÓLO ahí queda marcado («en SQL dinámico»). Es la trampa r3-T2: el
reloj vive dentro de una cadena.

Límites declarados: un nombre sin esquema que no es un objeto conocido se ignora (CTE, cursores, `inserted`); el SQL
dinámico armado con variables que no son literales del propio módulo no se puede leer (queda la marca
`sql_dinamico` y, en el CI, lo que el servidor ejecutó de verdad).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from radiografia.patrones import fin_de_sentencia
from radiografia.tsql import INICIO_SENTENCIA, RELOJ, Ficha, cierre, fichas, inicia_sentencia, nombre_objeto

# El mismo separador de lotes que usa el cargador del legado (`legado.conexion.lotes`): una línea con sólo GO.
_GO = re.compile(r'^\s*GO\s*$', re.IGNORECASE | re.MULTILINE)

TIPOS_MODULO = {'PROCEDURE': 'procedimiento', 'PROC': 'procedimiento', 'VIEW': 'vista', 'TRIGGER': 'trigger',
                'FUNCTION': 'funcion'}

# Procedimientos del sistema con efecto fuera de la base (por su último nombre, en minúsculas).
EFECTOS_DE_PROCEDIMIENTO = {
    'sp_send_dbmail': 'correo', 'xp_sendmail': 'correo', 'sp_notify_operator': 'correo',
    'sp_start_job': 'arranca un job', 'sp_stop_job': 'detiene un job',
    'xp_cmdshell': 'sistema operativo', 'sp_oacreate': 'objeto COM', 'sp_oamethod': 'objeto COM',
    'xp_fileexist': 'archivos', 'xp_dirtree': 'archivos', 'xp_create_subdir': 'archivos', 'xp_delete_file': 'archivos',
    'sp_addlinkedserver': 'servidor enlazado', 'sp_trace_create': 'archivos',
}
# Funciones de fila que salen de la base.
FUNCIONES_EXTERNAS = {'OPENQUERY': 'servidor enlazado', 'OPENDATASOURCE': 'servidor enlazado',
                      'OPENROWSET': 'servidor enlazado'}
# Sentencias de job que no son T-SQL: cada subsistema es un efecto fuera de la base.
SUBSISTEMAS_EXTERNOS = {'CMDEXEC': 'sistema operativo', 'POWERSHELL': 'sistema operativo', 'SSIS': 'paquete SSIS',
                        'ANALYSISCOMMAND': 'servidor de análisis', 'ANALYSISQUERY': 'servidor de análisis'}
PROCEDIMIENTOS_DE_JOB = {'sp_add_job', 'sp_add_jobstep', 'sp_add_jobschedule', 'sp_update_job', 'sp_update_jobstep'}

_UNION = frozenset(('INNER', 'LEFT', 'RIGHT', 'FULL', 'OUTER', 'CROSS', 'JOIN', 'APPLY'))
_FIN_DEL_FROM = frozenset(('WHERE', 'GROUP', 'ORDER', 'HAVING', 'UNION', 'EXCEPT', 'INTERSECT', 'OPTION', 'FOR',
                           'WINDOW'))
_NO_ES_FUENTE = _UNION | _FIN_DEL_FROM | INICIO_SENTENCIA | frozenset((
    'ON', 'AS', 'PIVOT', 'UNPIVOT', 'TABLESAMPLE', 'OUTPUT', 'LOOP', 'HASH', 'REMOTE', 'MERGE'))
_TRANSACCION = frozenset(('TRAN', 'TRANSACTION', 'DISTRIBUTED'))
CATALOGO = frozenset(('sys', 'information_schema'))


@dataclass(frozen=True)
class Lote:
    archivo: str          # ruta relativa a la raíz del repo
    linea: int            # línea del archivo donde empieza el lote
    texto: str


@dataclass
class Analisis:
    lee: set[str] = field(default_factory=set)
    escribe: dict[str, set[str]] = field(default_factory=dict)      # tabla → eventos
    temporales: set[str] = field(default_factory=set)
    llama: set[str] = field(default_factory=set)                    # procedimientos y funciones
    efectos: set[str] = field(default_factory=set)
    reloj: set[str] = field(default_factory=set)
    sql_dinamico: set[str] = field(default_factory=set)
    identidad: set[str] = field(default_factory=set)
    transaccion: set[str] = field(default_factory=set)
    desde_sql_dinamico: set[str] = field(default_factory=set)

    def escribir(self, tabla: str, evento: str) -> None:
        self.escribe.setdefault(tabla, set()).add(evento)

    def unir(self, otro: Analisis, dinamico: bool = False) -> None:
        nuevas = (otro.lee | set(otro.escribe) | otro.llama) - (self.lee | set(self.escribe) | self.llama)
        self.lee |= otro.lee
        for tabla, eventos in otro.escribe.items():
            self.escribe.setdefault(tabla, set()).update(eventos)
        self.temporales |= otro.temporales
        self.llama |= otro.llama
        self.efectos |= otro.efectos
        self.identidad |= otro.identidad
        self.transaccion |= otro.transaccion
        if dinamico:
            self.reloj |= {f'{r} (en SQL dinámico)' for r in otro.reloj}
            self.desde_sql_dinamico |= nuevas
        else:
            self.reloj |= otro.reloj
            self.sql_dinamico |= otro.sql_dinamico


@dataclass
class Modulo:
    id: str
    tipo: str
    archivo: str
    linea: int
    base: str
    texto: str            # el lote completo (cabecera incluida)
    inicio_cuerpo: int    # índice de la primera ficha del cuerpo
    tabla: str | None = None          # sólo triggers
    eventos: tuple[str, ...] = ()     # sólo triggers
    momento: str | None = None        # sólo triggers: AFTER o INSTEAD OF


@dataclass
class Job:
    nombre: str
    archivo: str
    linea: int
    pasos: list[dict] = field(default_factory=list)
    horarios: list[dict] = field(default_factory=list)
    descripcion: str | None = None


@dataclass
class Tabla:
    id: str
    archivo: str
    linea: int
    identidad: bool


@dataclass
class Codigo:
    """Lo que crean los scripts del legado."""
    principal: str
    modulos: list[Modulo]
    jobs: list[Job]
    tablas: list[Tabla]

    def conocidos(self) -> dict[str, str]:
        resultado = {t.id: 'tabla' for t in self.tablas}
        resultado.update({m.id: m.tipo for m in self.modulos})
        return resultado


# ── lotes y objetos ──────────────────────────────────────────────────────────────────────────────────────────

def lotes(texto: str, archivo: str) -> list[Lote]:
    """Separa un script en lotes por las líneas `GO`, conservando la línea donde empieza cada uno."""
    resultado: list[Lote] = []
    inicio = 0
    for m in _GO.finditer(texto):
        _agregar(resultado, archivo, texto, inicio, m.start())
        inicio = m.end()
    _agregar(resultado, archivo, texto, inicio, len(texto))
    return resultado


def _agregar(resultado: list[Lote], archivo: str, texto: str, a: int, b: int) -> None:
    if texto[a:b].strip():
        resultado.append(Lote(archivo, texto.count('\n', 0, a) + 1, texto[a:b]))


def relativa(ruta: Path, raiz: Path) -> str:
    """Ruta relativa al repo; una copia fuera del repo (p. ej. un SQL sembrado en una prueba) queda absoluta."""
    ruta, raiz = ruta.resolve(), raiz.resolve()
    return (ruta.relative_to(raiz) if ruta.is_relative_to(raiz) else ruta).as_posix()


def leer_scripts(rutas: list[Path], raiz: Path, principal: str = 'BFN_DIVISAS') -> Codigo:
    """Objetos que crean los scripts, en orden de nombre (el orden en que `python -m legado esquema` los corre, con
    UNA conexión: el `USE` de un script sigue valiendo en el siguiente)."""
    base = 'master'
    modulos: list[Modulo] = []
    jobs: dict[str, Job] = {}
    tablas: list[Tabla] = []
    for ruta in sorted(rutas, key=lambda r: r.name):
        for lote in lotes(ruta.read_text(encoding='utf-8'), relativa(ruta, raiz)):
            fs = fichas(lote.texto)
            if not fs:
                continue
            modulo = _modulo(fs, lote, base, principal)
            if modulo is not None:
                modulos.append(modulo)
                continue
            tablas.extend(_tablas(fs, lote, base, principal))
            _jobs(fs, lote, jobs)
            for i, f in enumerate(fs):
                if f.es('USE') and f.nivel == 0 and i + 1 < len(fs) and fs[i + 1].tipo == 'ident':
                    base = fs[i + 1].texto
    return Codigo(principal, modulos, list(jobs.values()), tablas)


def _linea(lote: Lote, f: Ficha) -> int:
    return lote.linea + f.linea - 1


def _modulo(fs: list[Ficha], lote: Lote, base: str, principal: str) -> Modulo | None:
    j = 1
    if fs[0].es('CREATE'):
        if len(fs) > 2 and fs[1].es('OR') and fs[2].es('ALTER'):
            j = 3
    elif not fs[0].es('ALTER'):
        return None
    if j >= len(fs) or fs[j].mayus not in TIPOS_MODULO or fs[j].tipo != 'ident':
        return None
    tipo = TIPOS_MODULO[fs[j].mayus]
    crudo, k = nombre_objeto(fs, j + 1)
    if crudo is None:
        return None
    id_, _ = identificador(crudo, base, principal)
    modulo = Modulo(id_, tipo, lote.archivo, _linea(lote, fs[0]), base, lote.texto, _inicio_cuerpo(fs, k))
    if tipo == 'trigger' and k < len(fs) and fs[k].es('ON'):
        tabla, k2 = nombre_objeto(fs, k + 1)
        modulo.tabla = identificador(tabla, base, principal)[0] if tabla else None
        cabecera = fs[k2:modulo.inicio_cuerpo]
        modulo.momento = 'INSTEAD OF' if any(f.es('INSTEAD') for f in cabecera) else 'AFTER'
        modulo.eventos = tuple(sorted({f.mayus for f in cabecera if f.es('INSERT', 'UPDATE', 'DELETE')}))
    return modulo


def _inicio_cuerpo(fs: list[Ficha], desde: int) -> int:
    """Primera ficha después del `AS` que abre el cuerpo (no el `@p AS int` de un parámetro ni `EXECUTE AS`)."""
    for i in range(desde, len(fs)):
        f = fs[i]
        if f.es('AS') and f.nivel == 0 and fs[i - 1].tipo != 'variable' and not fs[i - 1].es('EXECUTE', 'EXEC'):
            return i + 1
    return len(fs)


def _tablas(fs: list[Ficha], lote: Lote, base: str, principal: str) -> list[Tabla]:
    resultado = []
    for i, f in enumerate(fs):
        if f.es('CREATE') and inicia_sentencia(fs, i) and i + 2 < len(fs) and fs[i + 1].es('TABLE'):
            crudo, k = nombre_objeto(fs, i + 2)
            if not crudo or crudo.startswith('#'):
                continue
            fin = cierre(fs, k) if k < len(fs) and fs[k].texto == '(' else k
            identidad = any(x.es('IDENTITY') for x in fs[k:fin + 1])
            resultado.append(Tabla(identificador(crudo, base, principal)[0], lote.archivo, _linea(lote, f), identidad))
    return resultado


def _jobs(fs: list[Ficha], lote: Lote, jobs: dict[str, Job]) -> None:
    for i, f in enumerate(fs):
        if not (f.es('EXEC', 'EXECUTE') and inicia_sentencia(fs, i)):
            continue
        crudo, k = nombre_objeto(fs, i + 1)
        if not crudo or crudo.split('.')[-1].lower() not in PROCEDIMIENTOS_DE_JOB:
            continue
        procedimiento = crudo.split('.')[-1].lower()
        args = argumentos(fs, k, fin_de_sentencia(fs, i))
        nombre = args.get('@job_name')
        if not isinstance(nombre, str):
            continue
        job = jobs.setdefault(nombre, Job(nombre, lote.archivo, _linea(lote, f)))
        if procedimiento in ('sp_add_job', 'sp_update_job'):
            job.descripcion = args.get('@description', job.descripcion)
        elif procedimiento in ('sp_add_jobstep', 'sp_update_jobstep'):
            job.pasos.append({'paso': args.get('@step_name'), 'subsistema': str(args.get('@subsystem', 'TSQL')),
                              'base': args.get('@database_name'), 'comando': args.get('@command', ''),
                              'linea': _linea(lote, f)})
        else:
            job.horarios.append({'horario': args.get('@name'), 'frecuencia': args.get('@freq_type'),
                                 'intervalo': args.get('@freq_interval'),
                                 'hora': _hora(args.get('@active_start_time'))})


def _hora(valor) -> str | None:
    return f'{valor // 10000:02d}:{valor // 100 % 100:02d}' if isinstance(valor, int) else None


def argumentos(fs: list[Ficha], desde: int, fin: int) -> dict:
    """Argumentos con nombre de un EXEC: `@nombre = valor` (cadena sin comillas, número entero o palabra)."""
    resultado: dict = {}
    k = desde
    while k + 2 < min(fin, len(fs)):
        if fs[k].tipo == 'variable' and fs[k + 1].texto == '=':
            valor = fs[k + 2]
            if valor.tipo == 'cadena':
                resultado[fs[k].texto.lower()] = desentrecomillar(valor.texto)
            elif valor.tipo == 'numero' and valor.texto.isdigit():
                resultado[fs[k].texto.lower()] = int(valor.texto)
            else:
                resultado[fs[k].texto.lower()] = valor.texto
            k += 3
        else:
            k += 1
    return resultado


def desentrecomillar(cadena: str) -> str:
    texto = cadena[1:] if cadena[:1] in 'Nn' else cadena
    return texto[1:-1].replace("''", "'")


def identificador(crudo: str, base: str, principal: str) -> tuple[str, str | None]:
    """Nombre normalizado de un objeto y, si sale de la base principal, el efecto externo.

    `dbo.x`/`x`/`BFN_DIVISAS.dbo.x` → `dbo.x`; `otra.dbo.x` → `otra.dbo.x` + «otra base: otra»;
    `srv.base.dbo.x` → «servidor enlazado: srv»."""
    partes = crudo.split('.')
    if len(partes) >= 4:
        return '.'.join(partes[-4:]).lower(), f'servidor enlazado: {partes[-4]}'
    if len(partes) == 3:
        if partes[0].lower() == principal.lower():
            return f'{partes[1]}.{partes[2]}'.lower(), None
        return crudo.lower(), f'otra base: {partes[0]}'
    if len(partes) == 1:
        partes = ['dbo', partes[0]]
    nombre = '.'.join(partes).lower()
    return (nombre if base.lower() == principal.lower() else f'{base}.{nombre}'.lower()), None


# ── análisis de un módulo ────────────────────────────────────────────────────────────────────────────────────

def analizar(fs: list[Ficha], conocidos: dict[str, str], base: str, principal: str, desde: int = 0,
             dinamico: bool = False) -> Analisis:
    """Lo que hace el código de las fichas `fs[desde:]`."""
    a = Analisis()
    consumidas: set[int] = set()        # FROM de un DELETE e INTO de un MERGE: son su destino, no una lectura

    def referencia(crudo: str) -> str | None:
        """Id del objeto, o None si no es un objeto (nombre sin esquema que no se conoce: CTE, cursor, inserted)."""
        if crudo.startswith('#'):
            a.temporales.add(crudo.lower())
            return None
        id_, efecto = identificador(crudo, base, principal)
        if efecto:
            a.efectos.add(efecto)
        if id_.split('.')[-2] in CATALOGO:
            return None                          # catálogo del sistema: metadatos, no datos del legado
        if id_ in conocidos or '.' in crudo:
            return id_
        return None

    for i in range(desde, len(fs)):
        f = fs[i]
        if f.tipo == 'variable' and f.mayus == '@@IDENTITY':
            a.identidad.add('@@IDENTITY')
            continue
        if f.tipo != 'ident':
            continue
        siguiente = fs[i + 1] if i + 1 < len(fs) else None
        abre = siguiente is not None and siguiente.texto == '('
        if f.mayus in RELOJ and (abre or f.mayus == 'CURRENT_TIMESTAMP'):
            a.reloj.add(f.mayus)
        elif f.mayus in ('SCOPE_IDENTITY', 'IDENT_CURRENT') and abre:
            a.identidad.add(f.mayus)
        elif f.mayus in FUNCIONES_EXTERNAS and abre:
            bulk = i + 2 < len(fs) and fs[i + 2].es('BULK')
            a.efectos.add('archivos (OPENROWSET BULK)' if bulk else f'{FUNCIONES_EXTERNAS[f.mayus]} ({f.mayus})')
        elif f.es('BULK') and siguiente is not None and siguiente.es('INSERT'):
            a.efectos.add('archivos (BULK INSERT)')
        elif f.es('BACKUP', 'RESTORE') and inicia_sentencia(fs, i):
            a.efectos.add(f'archivos ({f.mayus})')
        elif f.es('BEGIN', 'SAVE') and siguiente is not None and siguiente.mayus in _TRANSACCION:
            a.transaccion.add(f'{f.mayus} {siguiente.mayus}')
        elif f.es('COMMIT', 'ROLLBACK') and inicia_sentencia(fs, i):
            a.transaccion.add(f.mayus)
        elif f.es('EXEC', 'EXECUTE') and inicia_sentencia(fs, i):
            _exec(fs, i, a, conocidos, referencia)
        elif f.es('INSERT') and siguiente is not None and siguiente.tipo == 'ident' and not siguiente.es('INTO'):
            id_ = referencia(nombre_objeto(fs, i + 1)[0] or '')
            if id_:
                a.escribir(id_, 'INSERT')
        elif f.es('INTO') and i not in consumidas:
            _into(fs, i, a, referencia)
        elif f.es('UPDATE', 'DELETE') and inicia_sentencia(fs, i) and not abre and not (
                siguiente is not None and siguiente.es('STATISTICS', 'SET')):
            _destino_con_alias(fs, i, a, referencia, consumidas)
        elif f.es('MERGE') and inicia_sentencia(fs, i):
            _merge(fs, i, a, referencia, consumidas)
        elif f.es('TRUNCATE') and siguiente is not None and siguiente.es('TABLE'):
            id_ = referencia(nombre_objeto(fs, i + 2)[0] or '')
            if id_:
                a.escribir(id_, 'TRUNCATE')
        elif f.es('DROP', 'ALTER') and inicia_sentencia(fs, i) and siguiente is not None and siguiente.es('TABLE'):
            id_ = referencia(nombre_objeto(fs, i + 2)[0] or '')
            if id_:
                a.escribir(id_, 'DDL')
        elif f.es('FROM', 'USING') and i not in consumidas:
            for crudo, es_funcion in _fuentes(fs, i, _fin_del_from(fs, i)):
                id_ = referencia(crudo)
                if id_:
                    (a.llama if es_funcion else a.lee).add(id_)
        elif _no_es_continuacion(fs, i) and siguiente is not None and siguiente.texto == '.':
            crudo, k = nombre_objeto(fs, i)
            if crudo and k < len(fs) and fs[k].texto == '(':
                id_ = referencia(crudo)        # función escalar calificada: dbo.fn(…)
                if id_ and conocidos.get(id_) == 'funcion':
                    a.llama.add(id_)

    if a.sql_dinamico and not dinamico:
        texto = ' '.join(desentrecomillar(f.texto) for f in fs[desde:] if f.tipo == 'cadena')
        a.unir(analizar(fichas(texto), conocidos, base, principal, dinamico=True), dinamico=True)
    for i in range(desde, len(fs)):         # 4 partes en cualquier lugar: servidor enlazado
        if fs[i].tipo == 'ident' and _no_es_continuacion(fs, i):
            crudo, _ = nombre_objeto(fs, i)
            if crudo and crudo.count('.') >= 3:
                a.efectos.add(f'servidor enlazado: {crudo.split(".")[0]}')
    return a


def _no_es_continuacion(fs: list[Ficha], i: int) -> bool:
    return i == 0 or not (fs[i - 1].tipo == 'op' and fs[i - 1].texto == '.')


def _exec(fs: list[Ficha], i: int, a: Analisis, conocidos: dict[str, str], referencia) -> None:
    k = i + 1
    if k + 1 < len(fs) and fs[k].tipo == 'variable' and fs[k + 1].texto == '=':
        k += 2                                   # EXEC @resultado = dbo.p
    if k >= len(fs):
        return
    f = fs[k]
    if f.texto == '(':
        a.sql_dinamico.add('EXEC(…)')
        fin = cierre(fs, k)
        if fin + 2 < len(fs) and fs[fin + 1].es('AT') and fs[fin + 2].tipo == 'ident':
            a.efectos.add(f'servidor enlazado: {fs[fin + 2].texto}')
        return
    if f.tipo == 'variable':
        a.sql_dinamico.add('EXEC @variable')
        return
    if f.tipo != 'ident' or f.es('AS'):         # EXECUTE AS USER = …
        return
    crudo, _ = nombre_objeto(fs, k)
    ultimo = crudo.split('.')[-1].lower()
    if ultimo == 'sp_executesql':
        a.sql_dinamico.add('sp_executesql')
        return
    if ultimo in EFECTOS_DE_PROCEDIMIENTO:
        a.efectos.add(f'{EFECTOS_DE_PROCEDIMIENTO[ultimo]} ({ultimo})')
        return
    id_ = referencia(crudo)
    a.llama.add(id_ or crudo.lower())


def _into(fs: list[Ficha], i: int, a: Analisis, referencia) -> None:
    if i + 1 >= len(fs) or fs[i + 1].tipo != 'ident':
        return                                   # INTO @variable (FETCH, OUTPUT INTO @t)
    id_ = referencia(nombre_objeto(fs, i + 1)[0] or '')
    if id_:
        a.escribir(id_, 'INSERT')


def _saltar_top(fs: list[Ficha], k: int) -> int:
    if k + 1 < len(fs) and fs[k].es('TOP') and fs[k + 1].texto == '(':
        return cierre(fs, k + 1) + 1
    return k


def _destino_con_alias(fs: list[Ficha], i: int, a: Analisis, referencia, consumidas: set[int]) -> None:
    """UPDATE/DELETE: el destino puede ser un ALIAS del FROM de la misma sentencia (`UPDATE o … FROM t o`)."""
    evento = fs[i].mayus
    k = _saltar_top(fs, i + 1)
    if evento == 'DELETE' and k < len(fs) and fs[k].es('FROM'):
        consumidas.add(k)
        k += 1
    if k >= len(fs) or fs[k].tipo != 'ident':
        return                                   # UPDATE @tabla_variable
    crudo, sig = nombre_objeto(fs, k)
    fin = fin_de_sentencia(fs, i)
    if '.' not in crudo:
        for j in range(sig, fin):
            if fs[j].es('FROM') and fs[j].nivel == fs[i].nivel and j not in consumidas:
                alias = {al.lower(): c for c, al in _fuentes_con_alias(fs, j, _fin_del_from(fs, j)) if al}
                crudo = alias.get(crudo.lower(), crudo)
                break
    id_ = referencia(crudo)
    if id_:
        a.escribir(id_, evento)


def _merge(fs: list[Ficha], i: int, a: Analisis, referencia, consumidas: set[int]) -> None:
    k = _saltar_top(fs, i + 1)
    if k < len(fs) and fs[k].es('INTO'):
        consumidas.add(k)
        k += 1
    if k < len(fs) and fs[k].tipo == 'ident':
        id_ = referencia(nombre_objeto(fs, k)[0] or '')
        if id_:
            for evento in ('INSERT', 'UPDATE', 'DELETE'):
                a.escribir(id_, evento)


def _fin_del_from(fs: list[Ficha], i: int) -> int:
    nivel = fs[i].nivel
    for k in range(i + 1, len(fs)):
        f = fs[k]
        if f.nivel < nivel or (f.nivel == nivel and f.tipo == 'op' and f.texto in (';', ')')):
            return k
        if f.nivel != nivel or f.tipo != 'ident':
            continue
        if f.mayus in _FIN_DEL_FROM and not (f.es('FOR') and k + 1 < len(fs) and fs[k + 1].es('SYSTEM_TIME')):
            return k
        if inicia_sentencia(fs, k):
            return k
    return len(fs)


def _fuentes_con_alias(fs: list[Ficha], desde: int, fin: int) -> list[tuple[str, str | None]]:
    """(nombre crudo, alias) de cada tabla o vista con nombre del FROM que empieza en `desde`."""
    nivel = fs[desde].nivel
    resultado: list[tuple[str, str | None]] = []
    k, esperando = desde + 1, True
    while k < fin:
        f = fs[k]
        if f.nivel != nivel:
            k += 1
            continue
        if esperando:
            esperando = False
            if f.tipo == 'ident' and f.mayus not in _NO_ES_FUENTE:
                crudo, k = nombre_objeto(fs, k)
                if k < fin and fs[k].texto == '(':
                    resultado.append((crudo, '('))        # función con valores de tabla
                    k = cierre(fs, k) + 1
                    continue
                if k < fin and fs[k].es('AS'):
                    k += 1
                alias = None
                if k < fin and fs[k].tipo == 'ident' and fs[k].nivel == nivel and fs[k].mayus not in _NO_ES_FUENTE:
                    alias = fs[k].texto
                    k += 1
                resultado.append((crudo, alias))
                continue
        elif f.texto == ',' or f.es('JOIN', 'APPLY'):
            esperando = True
        k += 1
    return resultado


def _fuentes(fs: list[Ficha], desde: int, fin: int) -> list[tuple[str, bool]]:
    """(nombre crudo, ¿es función?) de las fuentes con nombre de un FROM o USING."""
    return [(crudo, alias == '(') for crudo, alias in _fuentes_con_alias(fs, desde, fin)]
