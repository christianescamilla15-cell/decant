"""Paridad de ESTADO de los que escriben (S3 paso 5, ADR 0015; criterios 2 y 9 del plan). Sin base: aquí están los
escenarios, la copia temporal del legado, la guarda de `@@TRANCOUNT`, las verificaciones fijas, la comparación por
LLAVE DE NEGOCIO y su arbitraje, y el N de N. Lo que toca las bases lo hace `corte/estado_ci.py`.

- **Quiénes:** los escritores salen del inventario del CÓDIGO (`corte.codigo`): procedimientos, triggers y pasos de
  job. Hoy son 8. Cada uno tiene que correr en algún escenario (o dentro de otro: el disparador y el procedimiento que
  llama el paso del job) y el SERVIDOR tiene que decir que corrió (`sys.dm_exec_*_stats`). Si el inventario agrega uno
  sin escenario, o uno no corre, el N de N falla nombrándolo.
- **Dónde:** sobre el respaldo restaurado, en una transacción que se REVIERTE (`radiografia.veredictos.revertida`),
  incluidos los «sin ejecución observada». `GETDATE()` no se inyecta en el legado: lo que corre es una COPIA TEMPORAL
  en el esquema `estado` del respaldo (tablas con sus datos, índices y llaves; el disparador; los escritores), con el
  reloj leído de `SESSION_CONTEXT`. Nunca el original: los nombres `dbo.` de la copia apuntan a `estado.` y el servidor
  confirma que la copia no depende de ningún objeto de `dbo`.
- **Guarda:** `@@TRANCOUNT` antes y después de CADA llamada. Un procedimiento con su propio ROLLBACK se llevaría la
  transacción externa y el volcado saldría vacío sin avisar.
- **Entradas:** las llamadas reales del guion del día (la fase anterior al congelamiento), cada una con su instante;
  el paso del job, con el comando que guarda msdb, a la hora de su horario la noche del corte; los que el día no llama
  (la mesa y la contingencia), con los argumentos de una llamada real.
- **Comparación:** el efecto de cada etapa (lo que cambió, en las 7 tablas) en el legado y en el TO-BE, por llave de
  negocio: la operación por (folio, sucursal), la orden por (uetr, número de registro), sus partidas por renglón, la
  bitácora por lo que anota. Cada diferencia se arbitra con una explicación que se AUDITA; la que no se explica es
  defecto nuestro.
- **Verificaciones fijas:** todo id devuelto se cruza con la fila efectivamente insertada; toda escritura con JOIN se
  mide con sus datos 1:N.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from corte.carga import CON_IDENTIDAD, TABLAS, Tabla
from corte.sql import EFECTOS_DE_PROCEDIMIENTO, FUNCIONES_EXTERNAS
from radiografia.tsql import _FICHA as FICHA_TSQL
from radiografia.tsql import RELOJ as RELOJES

ESQUEMA = 'estado'                                 # la copia temporal, dentro del respaldo restaurado
CLAVE_RELOJ = 'decant.reloj'
RELOJ_SQL = f"CAST(SESSION_CONTEXT(N'{CLAVE_RELOJ}') AS datetime)"
# GETDATE() y CURRENT_TIMESTAMP devuelven la hora LOCAL del servidor como datetime: se inyectan. Los demás relojes
# (UTC, con zona o datetime2) no tienen equivalente con un solo valor: la copia se niega en vez de inventarlo.
INYECTABLES = frozenset(('GETDATE', 'CURRENT_TIMESTAMP'))
USUARIO = 'sa'                                     # SUSER_SNAME() de la sesión del arnés (en producción, cada login)
ORDEN_TABLAS = ('moneda', 'folio', 'operacion', 'orden_pago', 'partida_solicitada', 'partida_liquidada', 'bitacora')
MUESTRA = 10


class NoSeCopia(Exception):
    """La copia temporal no se puede hacer sin cambiar lo que el original hace (o sin tocar el original)."""


# ── escenarios ──────────────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Etapa:
    id: str
    escritor: str | None          # el del inventario que ejerce la etapa (None: DML directa del guion)
    que: str


@dataclass(frozen=True)
class Escenario:
    id: str
    titulo: str
    etapas: tuple[Etapa, ...]


JOB = 'job:BFN - conciliacion nocturna/paso:conciliar'
ESCENARIOS = (
    Escenario('A', 'el día del corte y su noche, con las llamadas reales del guion', (
        Etapa('A0', None, 'catálogo del guion: alta de SLE y baja de SLL (DML directa de sa; no es un escritor)'),
        Etapa('A1', 'dbo.sp_registrar_operacion', 'las operaciones del día, en el orden del guion'),
        Etapa('A2', 'dbo.sp_registrar_orden', 'las órdenes y los re-registros del día, en el orden del guion'),
        Etapa('A3', 'dbo.sp_registrar_liquidacion', 'las confirmaciones del corresponsal del día'),
        Etapa('A4', JOB, 'el comando del paso (msdb) a la hora de su horario, la noche del corte'))),
    Escenario('B', 'la mesa refleja en cada operación el estatus de su orden (sin ejecución observada)', (
        Etapa('B1', 'dbo.sp_reflejar_estatus_operacion', 'una llamada sobre el respaldo'),)),
    Escenario('C', 'alta manual de contingencia (sin ejecución observada)', (
        Etapa('C0', 'dbo.sp_registrar_operacion', 'la operación de esa orden, con su llamada real del guion'),
        Etapa('C1', 'dbo.sp_alta_manual_orden', 'la primera orden nueva del día, dada de alta a mano con los '
                                                'argumentos de su llamada real (la interfaz no corrió)'))),
)
# Los que corren DENTRO de otro: el servidor dice que corrieron (sus estadísticas), no una llamada del arnés.
ANIDADOS = {'dbo.tr_orden_pago_bitacora': 'lo dispara cada escritura de dbo.orden_pago (A2, A3, A4 y C1)',
            'dbo.sp_conciliar': 'lo llama el paso del job (A4)'}
ANIDADOS_EN = {'dbo.tr_orden_pago_bitacora': ('A2', 'A3', 'A4', 'C1'), 'dbo.sp_conciliar': ('A4',)}
# Qué tabla tiene la fila cuya identidad devuelve cada escritor por su parámetro OUTPUT (@id).
DEVUELVE = {'dbo.sp_registrar_operacion': 'operacion', 'dbo.sp_registrar_orden': 'orden_pago',
            'dbo.sp_alta_manual_orden': 'orden_pago'}
# El PARCHE del TO-BE aplicado a la copia del legado (controles de las trampas de r3): con él, el legado tiene que
# coincidir con el TO-BE. Texto exacto, que tiene que aparecer una sola vez en el original.
PARCHES = {
    'dbo.sp_reflejar_estatus_operacion': (
        'INNER JOIN dbo.operacion o ON o.id = p.operacion_id;',
        "INNER JOIN dbo.operacion o ON o.id = p.operacion_id AND p.estatus <> 'REEMPLAZADA';",
        'une sólo con la orden VIGENTE (lo que hace el TO-BE)'),
    'dbo.sp_alta_manual_orden': (
        'SET @id = @@IDENTITY;', 'SET @id = SCOPE_IDENTITY();',
        'devuelve la identidad de SU inserción (en el TO-BE, RETURNING id)'),
}
# Una VARIANTE del plan de la misma copia (no del original): «una orden cualquiera» del JOIN 1:N depende del plan, y
# la cifra de r3-T1 con ella. Sólo se mide; la comparación con el TO-BE es la de la copia tal cual.
VARIANTES_DE_PLAN = {
    'maxdop1': ('dbo.sp_reflejar_estatus_operacion',
                'INNER JOIN dbo.operacion o ON o.id = p.operacion_id;',
                'INNER JOIN dbo.operacion o ON o.id = p.operacion_id OPTION (MAXDOP 1);',
                'la misma sentencia sin paralelismo (OPTION (MAXDOP 1))'),
}
# El estatus que la mesa refleja en la operación (sp_reflejar_estatus_operacion); lo usa el árbitro del 1:N.
REFLEJO = {'CONCILIADA': 'PAGADA', 'DIFERENCIA': 'PAGADA', 'VENCIDA': 'RECHAZADA'}


def reflejado(estatus_orden: str) -> str:
    return REFLEJO.get(estatus_orden, 'EN_PROCESO')


def cubiertos() -> dict[str, str]:
    """Escritor → dónde corre (etapa o anidado)."""
    resultado: dict[str, str] = {}
    for s in ESCENARIOS:
        for e in s.etapas:
            if e.escritor:
                resultado.setdefault(e.escritor, e.id)
    resultado.update(ANIDADOS)
    return resultado


def n_de_n(escritores: list[str], evidencia: dict[str, dict]) -> dict:
    """N de N: cada escritor del inventario tiene escenario y el servidor dice que corrió al menos una vez. Falla
    nombrando al que falte (`evidencia[escritor]['ejecuciones']`)."""
    donde = cubiertos()
    sin_escenario = sorted(e for e in escritores if e not in donde)
    no_corrieron = sorted(e for e in escritores if e in donde and evidencia.get(e, {}).get('ejecuciones', 0) < 1)
    corridos = [e for e in escritores if e in donde and e not in no_corrieron]
    faltas = [f'{e}: el inventario lo tiene y ningún escenario lo corre' for e in sin_escenario]
    faltas += [f'{e}: tiene escenario ({donde[e]}) y el servidor no lo vio correr' for e in no_corrieron]
    return {'escritores': len(escritores), 'corridos': len(corridos), 'sin_escenario': sin_escenario,
            'no_corrieron': no_corrieron, 'faltas': faltas, 'verde': not faltas}


# ── efectos fuera de la base ────────────────────────────────────────────────────────────────────────────────────

# Cómo se neutraliza cada clase de efecto que el parser del inventario sabe ver (`corte.sql`). Los de procedimiento
# (EXEC) se EMULAN: la copia llama a un procedimiento de `estado` que sólo anota la llamada. Los de servidor enlazado
# u otra base no se pueden emular sin cambiar lo que el original lee: la copia se niega.
NO_EMULABLES = ('servidor enlazado', 'otra base', 'paquete SSIS', 'servidor de análisis')
NEUTRALIZACION = {efecto: 'emulado: la copia llama a estado.emulado_<procedimiento>, que sólo anota la llamada'
                  for efecto in set(EFECTOS_DE_PROCEDIMIENTO.values()) if efecto not in NO_EMULABLES}


def unidad(objetos: list[dict], escritor: str) -> dict:
    """El objeto del inventario de un escritor; el de un paso de job, con el job al que pertenece."""
    if '/paso:' in escritor:
        job, paso = escritor.split('/paso:')
        o = next(x for x in objetos if x['id'] == job)
        return {**next(p for p in o['pasos'] if p['paso'] == paso), 'id': escritor, 'tipo': 'paso', 'job': o,
                'sql_dinamico': []}
    return next(x for x in objetos if x['id'] == escritor)


def efectos_declarados(objetos: list[dict], escritores: list[str]) -> dict[str, dict]:
    """Por escritor: los efectos fuera de la base que el inventario le ve (con lo que llama y lo que dispara) y cómo se
    neutralizan en la corrida. Un efecto sin neutralización declarada detiene la corrida de ese objeto."""
    resultado = {}
    for e in escritores:
        o = unidad(objetos, e)
        efectos = sorted(set(o['efectivo']['efectos_externos']))
        decl = {}
        for efecto in efectos:
            clase = efecto.split(':')[0]
            decl[efecto] = NEUTRALIZACION.get(clase) or ('NO SE PUEDE EMULAR: la corrida se niega'
                                                         if any(clase.startswith(n) for n in NO_EMULABLES)
                                                         else 'SIN NEUTRALIZACIÓN DECLARADA: la corrida se niega')
        if o['tipo'] == 'paso':
            horarios = [r for r in o['job']['efectivo']['reloj'] if r.startswith('horario')]
            decl['arranque del job (su horario)'] = (
                f"neutralizado: el Agent del legado está apagado (MSSQL_AGENT_ENABLED=false) y el paso corre como su "
                f"comando T-SQL dentro de la transacción revertida, nunca con sp_start_job ({', '.join(horarios)})")
        resultado[e] = {'efectos': decl or {'ninguno': 'el inventario no le ve efectos fuera de la base'},
                        'se_niega': [k for k, v in decl.items() if 'se niega' in v]}
    return resultado


# ── la copia temporal ───────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class _Ficha:
    clase: str
    texto: str
    ini: int
    fin: int

    @property
    def nombre(self) -> str | None:
        if self.clase == 'ident':
            return self.texto
        if self.clase in ('corchete', 'comillas'):
            return self.texto[1:-1]
        return None


def _fichas(texto: str) -> list[_Ficha]:
    return [_Ficha(m.lastgroup, m.group(), m.start(), m.end()) for m in FICHA_TSQL.finditer(texto)
            if m.lastgroup not in ('espacio', 'comentario')]


def _es(f: _Ficha | None, *palabras: str) -> bool:
    return f is not None and f.nombre is not None and f.clase == 'ident' and f.texto.upper() in palabras


def _op(f: _Ficha | None, texto: str) -> bool:
    return f is not None and f.clase == 'operador' and f.texto == texto


@dataclass
class Copia:
    texto: str
    cuenta: Counter = field(default_factory=Counter)
    emulados: dict[str, list[str]] = field(default_factory=dict)      # procedimiento emulado → parámetros


def copiar(texto: str, objetos: set[str], esquema: str = ESQUEMA, parche: tuple[str, str] | None = None) -> Copia:
    """La copia de un módulo (o del comando de un paso) en `esquema`, sobre el texto ORIGINAL y por fichas (un nombre
    dentro de una cadena o de un comentario no se toca):
    - `CREATE OR ALTER` → `CREATE`;
    - cada `dbo.<objeto del inventario>` → `<esquema>.<objeto>` (tablas, procedimientos, disparador);
    - `GETDATE()` y `CURRENT_TIMESTAMP` → el reloj inyectado (`SESSION_CONTEXT`); otro reloj → se niega;
    - `EXEC <procedimiento con efecto fuera de la base>` → `EXEC <esquema>.emulado_<procedimiento>`;
    - un servidor enlazado (`OPENQUERY`…) o un nombre de tres partes → se niega.
    `parche` = (texto, reemplazo) se aplica ANTES, exacto y una sola vez (los controles de las trampas)."""
    if parche is not None:
        viejo, nuevo = parche
        if texto.count(viejo) != 1:
            raise NoSeCopia(f'el parche no aparece exactamente una vez: {viejo!r} ({texto.count(viejo)})')
        texto = texto.replace(viejo, nuevo)
    fs = _fichas(texto)
    cambios: list[tuple[int, int, str]] = []
    copia = Copia('')
    if len(fs) > 2 and _es(fs[0], 'CREATE') and _es(fs[1], 'OR') and _es(fs[2], 'ALTER'):
        cambios.append((fs[0].ini, fs[2].fin, 'CREATE'))
        copia.cuenta['cabecera'] += 1
    for i, f in enumerate(fs):
        siguiente = fs[i + 1] if i + 1 < len(fs) else None
        if f.nombre is not None and f.nombre.lower() == 'dbo' and _op(siguiente, '.') and i + 2 < len(fs):
            objeto = fs[i + 2].nombre
            if objeto is None or f'dbo.{objeto}'.lower() not in objetos:
                continue
            if i >= 2 and _op(fs[i - 1], '.') and fs[i - 2].nombre is not None:
                raise NoSeCopia(f'nombre de tres partes ({fs[i - 2].nombre}.dbo.{objeto}): la copia no puede '
                                'redirigirlo sin cambiar de base')
            cambios.append((f.ini, f.fin, esquema))
            copia.cuenta['nombres'] += 1
        elif f.clase == 'ident' and f.texto.upper() in RELOJES:
            if f.texto.upper() not in INYECTABLES:
                raise NoSeCopia(f'{f.texto}: un reloj que la copia no sabe inyectar con un solo valor')
            fin = f.fin
            if _op(siguiente, '(') and i + 2 < len(fs) and _op(fs[i + 2], ')'):
                fin = fs[i + 2].fin
            cambios.append((f.ini, fin, RELOJ_SQL))
            copia.cuenta['reloj'] += 1
        elif f.clase == 'ident' and f.texto.upper() in FUNCIONES_EXTERNAS:
            raise NoSeCopia(f'{f.texto}: servidor enlazado; no se emula sin cambiar lo que el original lee')
        elif _es(f, 'EXEC', 'EXECUTE') and siguiente is not None and siguiente.nombre is not None:
            j, partes = i + 1, [siguiente.nombre]
            while j + 2 < len(fs) and _op(fs[j + 1], '.') and fs[j + 2].nombre is not None:
                partes.append(fs[j + 2].nombre)
                j += 2
            procedimiento = partes[-1].lower()
            if EFECTOS_DE_PROCEDIMIENTO.get(procedimiento) in NO_EMULABLES:
                raise NoSeCopia(f'{procedimiento}: {EFECTOS_DE_PROCEDIMIENTO[procedimiento]}; no se emula')
            if procedimiento in EFECTOS_DE_PROCEDIMIENTO:
                parametros = _parametros_con_nombre(fs, j + 1)
                emulado = f'emulado_{procedimiento}'
                copia.emulados[emulado] = parametros
                cambios.append((siguiente.ini, fs[j].fin, f'{esquema}.{emulado}'))
                copia.cuenta['efectos emulados'] += 1
    resultado = texto
    for ini, fin, nuevo in sorted(cambios, reverse=True):
        resultado = resultado[:ini] + nuevo + resultado[fin:]
    copia.texto = resultado
    return copia


def _parametros_con_nombre(fs: list[_Ficha], desde: int) -> list[str]:
    """Los `@nombre =` de un EXEC hasta el fin de la sentencia; un argumento por posición no se puede emular."""
    nombres, k = [], desde
    while k < len(fs) and not _op(fs[k], ';') and not (fs[k].clase == 'ident' and fs[k].texto.upper() in (
            'EXEC', 'EXECUTE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'SET', 'IF', 'END', 'RETURN')):
        if fs[k].clase == 'variable' and k + 1 < len(fs) and _op(fs[k + 1], '='):
            nombres.append(fs[k].texto)
        elif fs[k].clase in ('cadena', 'numero', 'variable') and (k == desde or _op(fs[k - 1], ',')):
            raise NoSeCopia('un efecto fuera de la base llamado con argumentos por posición: no se emula')
        k += 1
    return nombres


def emulador(esquema: str, nombre: str, parametros: list[str], objeto: str) -> str:
    """El procedimiento que reemplaza al efecto: acepta los mismos parámetros con nombre y sólo anota la llamada."""
    if not re.fullmatch(r'emulado_\w+', nombre) or not all(re.fullmatch(r'@\w+', p) for p in parametros) \
            or not re.fullmatch(r'[\w.:/ -]+', objeto):
        raise NoSeCopia(f'emulador no válido: {nombre} {parametros}')
    firma = ', '.join(f'{p} sql_variant = NULL' for p in parametros)
    return (f'CREATE PROCEDURE {esquema}.{nombre} {firma} AS BEGIN SET NOCOUNT ON; '
            f"INSERT INTO {esquema}.efecto_emulado (objeto, efecto, instante) VALUES (N'{objeto}', N'{nombre}', "
            f'{RELOJ_SQL}); END')


EFECTO_EMULADO = (f'CREATE TABLE {ESQUEMA}.efecto_emulado (id int IDENTITY(1, 1) PRIMARY KEY, objeto sysname NOT NULL, '
                  'efecto sysname NOT NULL, instante datetime NULL)')


def ddl_tablas(lotes: list[str], tablas: set[str]) -> list[str]:
    """Los lotes de `legado/sql/02_tablas.sql` para la copia: sin `USE` y con las tablas en `estado`. Los nombres de
    las restricciones se conservan (viven en el esquema de su tabla)."""
    resultado = []
    for lote in lotes:
        fs = _fichas(lote)
        if not fs or _es(fs[0], 'USE'):
            continue
        resultado.append(copiar(lote, tablas).texto)
    return resultado


def copiar_datos(tabla: Tabla) -> str:
    """Los datos de una tabla del respaldo a su copia, con sus ids (y la identidad sigue en el mismo valor)."""
    columnas = ', '.join(f'[{c}]' for c in tabla.nombres)
    insertar = (f'INSERT INTO {ESQUEMA}.{tabla.nombre} WITH (TABLOCK) ({columnas}) '
                f'SELECT {columnas} FROM dbo.{tabla.nombre}')
    if tabla.identidad:
        return (f'SET IDENTITY_INSERT {ESQUEMA}.{tabla.nombre} ON; {insertar}; '
                f'SET IDENTITY_INSERT {ESQUEMA}.{tabla.nombre} OFF;')
    return insertar + ';'


# ── el volcado: lo que cambió (SQL Server, la copia contra el original) ────────────────────────────────────────────

def _binario(nombre: str, tipo: str) -> str | None:
    """Comparar texto en SQL Server ignora los espacios finales y las mayúsculas (intercalación CI_AS): la diferencia
    se busca también en los bytes."""
    tipo = tipo.lower()
    if tipo == 'sysname':
        return f'CAST([{nombre}] AS varbinary(256))'
    m = re.fullmatch(r'(n?)(?:var)?char\((\d+)\)', tipo)
    if m:
        return f'CAST([{nombre}] AS varbinary({int(m.group(2)) * (2 if m.group(1) else 1)}))'
    return None


def _proyeccion(t: Tabla) -> str:
    columnas = [f'[{c.nombre}]' for c in t.columnas]
    return ', '.join(columnas + [b for c in t.columnas if (b := _binario(c.nombre, c.tipo))])


# Consultas literales (sólo identificadores de la especificación cerrada `carga.TABLAS`).
DESPUES_MS = {t.nombre: f'SELECT {_proyeccion(t)} FROM {ESQUEMA}.{t.nombre} EXCEPT SELECT {_proyeccion(t)} '
                        f'FROM dbo.{t.nombre}' for t in TABLAS.values()}
ANTES_MS = {t.nombre: f'SELECT {_proyeccion(t)} FROM dbo.{t.nombre} EXCEPT SELECT {_proyeccion(t)} '
                      f'FROM {ESQUEMA}.{t.nombre}' for t in TABLAS.values()}
POR_LLAVE_MS = {t.nombre: f"SELECT {', '.join(f'[{c}]' for c in t.nombres)} FROM dbo.{t.nombre} "
                          f"WHERE [{t.nombres[0]}] IN (SELECT value FROM STRING_SPLIT(%s, ','))"
                for t in TABLAS.values()}
MAXIMOS_MS = 'SELECT ' + ', '.join(f'(SELECT MAX(id) FROM {ESQUEMA}.{t.nombre})' for t in CON_IDENTIDAD)
MAXIMOS_PG = 'SELECT ' + ', '.join(f'(SELECT max(id) FROM legado.{t.nombre})' for t in CON_IDENTIDAD)
IDENT_MS = {e: 'SELECT ' + ', '.join(f"IDENT_CURRENT(N'{e}.{t.nombre}')" for t in CON_IDENTIDAD)
            for e in ('dbo', ESQUEMA)}
RESEMBRAR_MS = {t.nombre: f"DBCC CHECKIDENT (N'{ESQUEMA}.{t.nombre}', RESEED, %s) WITH NO_INFOMSGS"
                for t in CON_IDENTIDAD}
ORDENES_MS = (f'SELECT o.id, o.uetr, o.n FROM (SELECT id, uetr, ROW_NUMBER() OVER (PARTITION BY uetr ORDER BY id) AS n '
              f'FROM {ESQUEMA}.orden_pago WHERE uetr IN (SELECT uetr FROM {ESQUEMA}.orden_pago WHERE id IN '
              f"(SELECT CAST(value AS int) FROM STRING_SPLIT(%s, ',')))) o "
              f"WHERE o.id IN (SELECT CAST(value AS int) FROM STRING_SPLIT(%s, ','))")
OPERACIONES_MS = (f'SELECT id, folio, sucursal FROM {ESQUEMA}.operacion WHERE id IN '
                  "(SELECT CAST(value AS int) FROM STRING_SPLIT(%s, ','))")


def filas_de_proyeccion(t: Tabla, filas: list[tuple]) -> dict:
    """Las filas de DESPUES_MS/ANTES_MS sin sus columnas binarias, por su llave."""
    n = len(t.columnas)
    return {f[0]: tuple(f[:n]) for f in filas}


@dataclass
class Efecto:
    """Lo que cambió en una tabla respecto al estado inicial (el respaldo): valores después, por llave."""
    despues: dict = field(default_factory=dict)     # llave → fila (insertadas y cambiadas)
    borradas: set = field(default_factory=set)      # llaves que ya no están


def efecto_de(t: Tabla, despues: list[tuple], antes: list[tuple]) -> Efecto:
    """De las dos diferencias de conjuntos (copia − original y original − copia) al efecto por llave."""
    d = filas_de_proyeccion(t, despues)
    a = filas_de_proyeccion(t, antes)
    return Efecto(d, set(a) - set(d))


# ── el guion: las llamadas reales del día ───────────────────────────────────────────────────────────────────────

def instante(texto: str) -> datetime:
    """El instante de una llamada, en hora local y al segundo (los dos motores lo guardan igual)."""
    return datetime.fromisoformat(texto).replace(tzinfo=None, microsecond=0)


def llamadas(guion: dict) -> dict[str, list[dict]]:
    """Las llamadas de la fase anterior al congelamiento, por etapa del escenario A (cada una con su instante local).
    Se conserva el orden del guion dentro de cada etapa; entre etapas, el día va por escritor: operaciones, órdenes y
    liquidaciones (ninguna liquidación del guion precede al registro de su orden y ningún re-registro sigue a una
    liquidación del mismo documento: el generador no los produce y la prueba lo verifica)."""
    etapas: dict[str, list[dict]] = {'A0': [], 'A1': [], 'A2': [], 'A3': []}
    destino = {'alta_moneda': 'A0', 'baja_moneda': 'A0', 'operacion': 'A1', 'orden': 'A2', 'liquidacion': 'A3'}
    for paso in guion['pasos']:
        if paso['fase'] != 'delta':
            continue
        etapas[destino[paso['accion']]].append({**paso, 'reloj': instante(paso['hora_local'])})
    return etapas


def noche_del_corte(guion: dict, objetos: list[dict]) -> datetime:
    """La noche del corte a la hora del horario del job (del inventario: «todas las noches 23:30»)."""
    job = next(o for o in objetos if o['tipo'] == 'job')
    horario = next(r for r in job['efectivo']['reloj'] if r.startswith('horario'))
    hora, minuto = (int(x) for x in re.search(r'(\d\d):(\d\d)\)', horario).groups())
    return datetime.combine(date.fromisoformat(guion['fecha_negocio']), datetime.min.time()).replace(
        hour=hora, minute=minuto)


def alta_manual(guion: dict) -> dict:
    """Los argumentos de la contingencia: la primera orden NUEVA del día (como si la interfaz no hubiera corrido y la
    mesa la diera de alta a mano), con su instante, y la llamada real de su operación si es del mismo día."""
    pasos = [p for p in guion['pasos'] if p['fase'] == 'delta']
    for paso in pasos:
        a = paso['args']
        if paso['accion'] == 'orden' and not a.get('reregistro'):
            operacion = None
            if isinstance(a['operacion_id'], str):
                operacion = next(p for p in pasos if p['accion'] == 'operacion' and p.get('ref') == a['operacion_id'])
                operacion = {**operacion, 'reloj': instante(operacion['hora_local'])}
            return {'orden': {**paso, 'reloj': instante(paso['hora_local'])}, 'operacion': operacion}
    raise NoSeCopia('el guion no trae una orden nueva')


# ── llave de negocio ────────────────────────────────────────────────────────────────────────────────────────────

def canonico(valor):
    """La forma con la que se comparan los valores de los dos motores (la de `corte/cifras.py`)."""
    if valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return '1' if valor else '0'
    if isinstance(valor, Decimal):
        return format(valor, 'f')
    if isinstance(valor, datetime):
        return valor.isoformat(sep=' ', timespec='milliseconds')
    if isinstance(valor, date):
        return valor.isoformat()
    return str(valor)


@dataclass
class Refs:
    """Las llaves de negocio de las filas a las que apuntan otras: orden id → (uetr, número de registro) y operación
    id → (folio, sucursal)."""
    orden: dict = field(default_factory=dict)
    operacion: dict = field(default_factory=dict)

    def unir(self, otro: Refs) -> None:
        self.orden.update(otro.orden)
        self.operacion.update(otro.operacion)


def llave(tabla: str, fila: tuple, refs: Refs) -> tuple:
    """La llave de negocio de una fila (sin ids): la que el TO-BE conoce. Su largo depende de la tabla: la operación
    (folio, sucursal), la orden (uetr, número de registro), la partida (uetr, número de registro, renglón), la bitácora
    (la orden y lo que anota) y los catálogos su código."""
    c = dict(zip(TABLAS[tabla].nombres, fila))
    if tabla == 'operacion':
        partes = [c['folio'], c['sucursal']]
    elif tabla == 'orden_pago':
        partes = list(refs.orden.get(c['id'], ('?', c['id'])))
    elif tabla in ('partida_solicitada', 'partida_liquidada'):
        partes = [*refs.orden.get(c['orden_id'], ('?', c['orden_id'])), c['renglon']]
    elif tabla == 'bitacora':
        orden = refs.orden.get(c['llave'], ('?', c['llave'])) if c['tabla'] == 'orden_pago' else c['llave']
        partes = [orden, c['accion'], c['estatus_anterior'], c['estatus_nuevo'], c['usuario'], canonico(c['fecha'])]
    else:
        partes = [c[TABLAS[tabla].nombres[0]]]
    return tuple(partes)


def valor(tabla: str, fila: tuple, refs: Refs) -> tuple:
    """Los valores de negocio de una fila: sin su id y con las referencias por su llave de negocio."""
    c = dict(zip(TABLAS[tabla].nombres, fila))
    fuera = {'id'}
    if tabla in ('partida_solicitada', 'partida_liquidada'):
        fuera.add('orden_id')
    if tabla == 'bitacora':
        fuera.add('llave')
    if tabla == 'orden_pago':
        c['operacion_id'] = refs.operacion.get(c['operacion_id'], ('?', c['operacion_id']))
    return tuple((k, canonico(v) if not isinstance(v, tuple) else v) for k, v in c.items() if k not in fuera)


@dataclass
class Lado:
    """Un lado (legado o TO-BE) en una etapa: el estado de las filas tocadas, por llave de negocio."""
    filas: dict = field(default_factory=dict)       # tabla → {llave: valores | None (borrada)}


def lado_de_etapa(previo: dict[str, Efecto], actual: dict[str, Efecto], inicial: dict[str, dict], refs: Refs,
                  otras: dict[str, set] | None = None) -> tuple[Lado, dict[str, set]]:
    """Lo que la ETAPA cambió en un lado (del efecto acumulado antes y después de ella) y, además, el valor en ese lado
    de las llaves que tocó el OTRO lado (`otras`, por llave del estado inicial), para poder compararlas. Devuelve
    también las llaves (ids) que tocó esta etapa."""
    lado, tocadas = Lado(), {}
    for t in ORDEN_TABLAS:
        p, a = previo.get(t, Efecto()), actual.get(t, Efecto())
        ids = {k for k in set(p.despues) | set(a.despues) | p.borradas | a.borradas
               if (k in a.borradas) != (k in p.borradas) or a.despues.get(k) != p.despues.get(k)}
        tocadas[t] = ids
        filas: dict = {}
        conteo: Counter = Counter()
        for k in sorted(ids | (otras or {}).get(t, set()), key=str):
            fila = None if k in a.borradas else a.despues.get(k, inicial.get(t, {}).get(k))
            referencia = fila or p.despues.get(k) or inicial.get(t, {}).get(k)
            if referencia is None:
                continue                       # la tocó el otro lado y aquí no existe: la verá la comparación
            ll = llave(t, referencia, refs)
            if t == 'bitacora':
                conteo[ll] += 1
                ll = (*ll, conteo[ll])         # la bitácora es multiconjunto: la n-ésima anotación igual
            filas[ll] = None if fila is None else valor(t, fila, refs)
        lado.filas[t] = filas
    return lado, tocadas


@dataclass
class Diferencia:
    tabla: str
    llave: tuple
    tipo: str                       # 'sólo en el legado', 'sólo en el TO-BE', 'distinta'
    columnas: tuple = ()
    legado: tuple | None = None
    tobe: tuple | None = None
    clase: str = 'defecto nuestro'  # la del árbitro que la explicó (auditado), o defecto nuestro
    explicacion: str = ''


def comparar(legado: Lado, tobe: Lado) -> list[Diferencia]:
    """Por tabla y llave de negocio: lo que la etapa dejó en cada lado. Una fila que no está en un lado, o que tiene
    otro valor en alguna columna, es una diferencia."""
    resultado = []
    for t in ORDEN_TABLAS:
        a, b = legado.filas.get(t, {}), tobe.filas.get(t, {})
        for k in sorted(set(a) | set(b), key=str):
            va, vb = a.get(k), b.get(k)
            if va == vb:
                continue
            if va is None or vb is None:
                tipo = 'sólo en el legado' if vb is None else 'sólo en el TO-BE'
                resultado.append(Diferencia(t, k, tipo, legado=va, tobe=vb))
                continue
            columnas = tuple(x for (x, y), (_x, z) in zip(va, vb) if y != z)
            resultado.append(Diferencia(t, k, 'distinta', columnas, va, vb))
    return resultado


def resumen_de_diferencias(diferencias: list[Diferencia]) -> dict:
    por = Counter((d.tabla, d.tipo, ','.join(d.columnas), d.clase) for d in diferencias)
    return {'total': len(diferencias),
            'por_clase': dict(Counter(d.clase for d in diferencias)),
            'por_tabla_y_columna': [{'tabla': t, 'tipo': tipo, 'columnas': c, 'clase': clase, 'n': n}
                                    for (t, tipo, c, clase), n in sorted(por.items(), key=str)],
            'muestra': [{'tabla': d.tabla, 'llave': list(d.llave), 'tipo': d.tipo, 'columnas': list(d.columnas),
                         'legado': dict(d.legado or ()), 'tobe': dict(d.tobe or ()), 'clase': d.clase,
                         'explicacion': d.explicacion} for d in diferencias[:MUESTRA]]}


# ── árbitros (cada uno AUDITA su explicación en cada diferencia) ─────────────────────────────────────────────────

DEFECTO_NUESTRO = 'defecto nuestro'
DEFECTO_LEGADO = 'defecto del legado (pendiente de decisión de negocio)'
REGLA_1_N = 'UPDATE … FROM con un JOIN 1:N: la operación tomó el estatus de una orden que NO es la vigente'
REGLA_IDENTIDAD = '@@IDENTITY: el id devuelto es la identidad que generó el disparador en otra tabla'


def arbitrar_1_n(diferencias: list[Diferencia], ordenes: dict[tuple, list[tuple[int, str]]]) -> None:
    """r3-T1 sin leer el catálogo: una diferencia de `operacion.estatus` se explica por el JOIN 1:N sólo si la
    operación tiene varias órdenes, el TO-BE escribió el reflejo de la VIGENTE (la no REEMPLAZADA de id mayor) y el
    legado el de OTRA de sus órdenes. `ordenes` = (folio, sucursal) de la operación → [(id, estatus)] en el respaldo."""
    for d in diferencias:
        if d.tabla != 'operacion' or d.tipo != 'distinta' or d.columnas != ('estatus',):
            continue
        filas = ordenes.get(d.llave, [])
        vigentes = [f for f in filas if f[1] != 'REEMPLAZADA']
        if len(filas) < 2 or not vigentes:
            continue
        vigente = max(vigentes)
        del_legado, del_tobe = dict(d.legado)['estatus'], dict(d.tobe)['estatus']
        otras = {reflejado(e) for i, e in filas if i != vigente[0]}
        if del_tobe == reflejado(vigente[1]) and del_legado != del_tobe and del_legado in otras:
            d.clase = DEFECTO_LEGADO
            d.explicacion = (f'{REGLA_1_N}: {len(filas)} órdenes; la vigente ({vigente[0]}, {vigente[1]}) da '
                             f'{del_tobe} y el legado dejó {del_legado}')


def revisar_identidad(llamada: dict, tabla: str) -> dict | None:
    """Verificación fija: el id que devuelve la llamada es el de la fila que ESA llamada insertó en `tabla`. Si no, se
    busca en qué tabla insertó la llamada una fila con ese id (el árbitro de @@IDENTITY lo exige para explicarlo)."""
    devuelto = llamada.get('devuelto')
    propias = llamada['insertadas'].get(tabla, [])
    if devuelto is not None and propias == [devuelto]:
        return None
    otras = sorted(t for t, ids in llamada['insertadas'].items() if t != tabla and devuelto in ids)
    explicada = bool(otras) and len(propias) == 1
    return {'llamada': llamada['n'], 'escritor': llamada['escritor'], 'devuelto': devuelto,
            'insertada_en': {tabla: propias}, 'el_id_es_de': otras,
            'clase': DEFECTO_LEGADO if explicada else DEFECTO_NUESTRO,
            'explicacion': (f'{REGLA_IDENTIDAD} ({", ".join(otras)}): devolvió {devuelto} y la fila de {tabla} '
                            f'quedó con {propias[0]}') if explicada else
                           f'devolvió {devuelto} y en {tabla} insertó {propias}'}


def guarda_trancount(objeto: str, antes: int | None, despues: int | None) -> str | None:
    """La guarda: la llamada no puede cambiar `@@TRANCOUNT` (ni abrir sin cerrar, ni confirmar, ni revertir la
    transacción externa)."""
    if antes == despues:
        return None
    return (f'{objeto}: @@TRANCOUNT {antes} → {despues} durante la llamada; se llevó la transacción externa y lo que '
            'escribió ya no se puede volcar ni revertir con ella: la corrida se detiene')


def inserciones(antes: tuple, despues: tuple) -> dict[str, list[int]]:
    """Los ids que una llamada insertó en cada tabla con identidad (MAX(id) antes y después, en la transacción)."""
    resultado = {}
    for t, a, d in zip((t.nombre for t in CON_IDENTIDAD), antes, despues):
        if d is not None and (a is None or d > a):
            resultado[t] = list(range((a or 0) + 1, d + 1))
    return resultado
