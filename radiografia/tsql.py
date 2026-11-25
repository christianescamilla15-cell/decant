"""Analizador léxico mínimo de T-SQL para los detectores por patrón.

No es un parser: convierte el texto de un módulo (procedimiento, vista, trigger, función o paso de un job) en
fichas con su línea y su profundidad de paréntesis, sin comentarios. Los detectores trabajan sobre las fichas,
así un `TOP` dentro de un comentario o un `GETDATE()` dentro de una cadena no cuentan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

_FICHA = re.compile(r"""
    (?P<espacio>\s+)
  | (?P<comentario>--[^\n]*|/\*.*?\*/)
  | (?P<cadena>N?'(?:[^']|'')*')
  | (?P<corchete>\[(?:[^\]]|\]\])*\])
  | (?P<comillas>"(?:[^"]|"")*")
  | (?P<variable>@@?[A-Za-z_\#\$@][\w\#\$@]*)
  | (?P<numero>(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
  | (?P<ident>[A-Za-z_\#][\w\#\$@]*)
  | (?P<operador><>|!=|>=|<=|\+=|-=|\*=|/=|[(),;.=<>+\-*/%&|^~!:])
  | (?P<otro>.)
""", re.VERBOSE | re.DOTALL)


@dataclass(frozen=True)
class Ficha:
    tipo: str          # ident, cadena, numero, variable, op
    texto: str         # texto original (cadena con comillas; identificador sin corchetes)
    linea: int
    nivel: int         # profundidad de paréntesis ANTES de la ficha
    en_caso: bool = False   # dentro de un CASE … END (su ELSE y su END no abren ni cierran sentencias)

    @property
    def mayus(self) -> str:
        return self.texto.upper()

    def es(self, *palabras: str) -> bool:
        return self.tipo == 'ident' and self.mayus in palabras


def fichas(texto: str) -> list[Ficha]:
    resultado: list[Ficha] = []
    linea, nivel = 1, 0
    for m in _FICHA.finditer(texto):
        clase, valor = m.lastgroup, m.group()
        if clase in ('espacio', 'comentario'):
            linea += valor.count('\n')
            continue
        if clase == 'corchete':
            resultado.append(Ficha('ident', valor[1:-1].replace(']]', ']'), linea, nivel))
        elif clase == 'comillas':
            resultado.append(Ficha('ident', valor[1:-1].replace('""', '"'), linea, nivel))
        elif clase == 'cadena':
            resultado.append(Ficha('cadena', valor, linea, nivel))
        elif clase == 'variable':
            resultado.append(Ficha('variable', valor, linea, nivel))
        elif clase == 'numero':
            resultado.append(Ficha('numero', valor, linea, nivel))
        elif clase == 'ident':
            resultado.append(Ficha('ident', valor, linea, nivel))
        else:
            resultado.append(Ficha('op', valor, linea, nivel))
            if valor == '(':
                nivel += 1
            elif valor == ')':
                nivel = max(nivel - 1, 0)
        linea += valor.count('\n')
    return _marcar_casos(resultado)


def _marcar_casos(fs: list[Ficha]) -> list[Ficha]:
    abiertos: list[int] = []          # nivel de paréntesis de cada CASE abierto
    marcadas = []
    for f in fs:
        dentro = bool(abiertos)
        if f.es('CASE'):
            abiertos.append(f.nivel)
            dentro = True
        elif f.es('END') and abiertos and abiertos[-1] == f.nivel:
            abiertos.pop()
            dentro = True
        marcadas.append(replace(f, en_caso=True) if dentro else f)
    return marcadas


def inicia_sentencia(fs: list[Ficha], j: int) -> bool:
    """¿La ficha j abre una sentencia? No cuentan el ELSE/END de un CASE ni el WITH de una sugerencia de tabla."""
    f = fs[j]
    if f.tipo != 'ident' or f.mayus not in INICIO_SENTENCIA or f.en_caso:
        return False
    return not (f.mayus == 'WITH' and j + 1 < len(fs) and fs[j + 1].texto == '(')


def cierre(fs: list[Ficha], i: int) -> int:
    """Índice del ')' que cierra el '(' en la posición i (o el último índice si no cierra)."""
    nivel = fs[i].nivel
    for j in range(i + 1, len(fs)):
        if fs[j].tipo == 'op' and fs[j].texto == ')' and fs[j].nivel == nivel + 1:
            return j
    return len(fs) - 1


def apertura(fs: list[Ficha], i: int) -> int | None:
    """Índice del '(' que encierra la ficha i, o None si está en el nivel 0."""
    objetivo = fs[i].nivel - 1
    if objetivo < 0:
        return None
    for j in range(i - 1, -1, -1):
        if fs[j].tipo == 'op' and fs[j].texto == '(' and fs[j].nivel == objetivo:
            return j
    return None


# Palabras que abren una sentencia nueva cuando aparecen en el nivel del bloque.
INICIO_SENTENCIA = frozenset((
    'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'IF', 'ELSE', 'WHILE', 'BEGIN', 'END', 'SET', 'DECLARE',
    'EXEC', 'EXECUTE', 'RETURN', 'PRINT', 'RAISERROR', 'THROW', 'TRUNCATE', 'CREATE', 'ALTER', 'DROP', 'WITH',
    'OPEN', 'FETCH', 'CLOSE', 'DEALLOCATE', 'COMMIT', 'ROLLBACK', 'BREAK', 'CONTINUE', 'GOTO', 'WAITFOR', 'USE',
    'GRANT', 'DENY', 'REVOKE', 'BACKUP', 'RESTORE', 'DBCC', 'SAVE'))

# Funciones del reloj del servidor.
RELOJ = frozenset(('GETDATE', 'SYSDATETIME', 'GETUTCDATE', 'SYSUTCDATETIME', 'SYSDATETIMEOFFSET',
                   'CURRENT_TIMESTAMP'))


def fin_de_consulta(fs: list[Ficha], inicio: int) -> int:
    """Fin (exclusivo) de la consulta SELECT que empieza en `inicio`, en su mismo nivel de paréntesis.

    Termina al cerrar el paréntesis que la contiene, en `;`, o cuando en su nivel aparece otra sentencia
    (que no sea parte de la misma consulta: UNION, un SELECT tras INSERT, etc.).
    """
    nivel = fs[inicio].nivel
    for j in range(inicio + 1, len(fs)):
        f = fs[j]
        if f.nivel < nivel or (f.nivel == nivel and f.tipo == 'op' and f.texto in (')', ';')):
            return j
        if f.nivel == nivel and inicia_sentencia(fs, j):
            anterior = fs[j - 1]
            if f.mayus == 'SELECT' and anterior.es('UNION', 'ALL', 'EXCEPT', 'INTERSECT'):
                continue
            if f.mayus == 'SET' and _sentencia_actual(fs, j) == 'UPDATE':
                continue
            return j
    return len(fs)


def _sentencia_actual(fs: list[Ficha], i: int) -> str | None:
    nivel = fs[i].nivel
    for j in range(i - 1, -1, -1):
        f = fs[j]
        if f.nivel < nivel:
            return None
        if f.nivel == nivel and inicia_sentencia(fs, j) and f.mayus != 'SET':
            return f.mayus
    return None


def nombre_objeto(fs: list[Ficha], i: int) -> tuple[str | None, int]:
    """Lee un nombre de objeto (esquema.tabla, base.esquema.tabla) desde la ficha i. Devuelve (nombre, siguiente)."""
    if i >= len(fs) or fs[i].tipo != 'ident':
        return None, i
    partes = [fs[i].texto]
    j = i + 1
    while j + 1 < len(fs) and fs[j].tipo == 'op' and fs[j].texto == '.' and fs[j + 1].tipo == 'ident':
        partes.append(fs[j + 1].texto)
        j += 2
    return '.'.join(partes), j
