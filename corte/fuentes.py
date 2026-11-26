"""Lo que el legado tiene FUERA de la base, leído del código Python con `ast` (sin ejecutarlo):

- **la pantalla** (`legado/pantalla/*.py`): cada cadena que es SQL (empieza con EXEC, SELECT, INSERT, UPDATE, DELETE,
  MERGE, WITH o DECLARE) se analiza con el mismo parser que los módulos: qué llama y qué lee;
- **las interfaces de entrada** (`legado/generador/interfaces.py`): cada función que arma rutas de archivo con un
  f-string `'<carpeta>/…'` es una interfaz; su nombre sale del docstring del módulo (la viñeta que cita esa carpeta).
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from corte.sql import Analisis, analizar, relativa
from radiografia.tsql import fichas

_SQL = frozenset(('EXEC', 'EXECUTE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'WITH', 'DECLARE'))
_CARPETA = re.compile(r'^([a-z_]+)/')
_VINETA = re.compile(r'^- \*\*(?P<nombre>[^*]+)\*\*', re.MULTILINE)


@dataclass
class Consulta:
    archivo: str
    linea: int
    analisis: Analisis


@dataclass
class Interfaz:
    funcion: str
    nombre: str
    archivo: str
    linea: int
    carpeta: str
    archivos: list[str] = field(default_factory=list)


def consultas_de(rutas: list[Path], raiz: Path, conocidos: dict[str, str], principal: str) -> list[Consulta]:
    """Cadenas de SQL del código Python, analizadas."""
    resultado = []
    for ruta in sorted(rutas):
        archivo = relativa(ruta, raiz)
        arbol = ast.parse(ruta.read_text(encoding='utf-8'), filename=archivo)
        for nodo in ast.walk(arbol):
            if not (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)):
                continue
            fs = fichas(nodo.value)
            if fs and fs[0].tipo == 'ident' and fs[0].mayus in _SQL:
                resultado.append(Consulta(archivo, nodo.lineno, analizar(fs, conocidos, principal, principal)))
    return sorted(resultado, key=lambda c: (c.archivo, c.linea))


def interfaces_de(ruta: Path, raiz: Path) -> list[Interfaz]:
    """Funciones que arman las rutas de los archivos que recibe el legado: una interfaz por función."""
    archivo = relativa(ruta, raiz)
    arbol = ast.parse(ruta.read_text(encoding='utf-8'), filename=archivo)
    vinetas = _vinetas(ast.get_docstring(arbol) or '')
    resultado = []
    for funcion in arbol.body:
        if not isinstance(funcion, ast.FunctionDef):
            continue
        rutas = []
        for nodo in ast.walk(funcion):
            if isinstance(nodo, ast.JoinedStr) and nodo.values and isinstance(nodo.values[0], ast.Constant):
                coincide = _CARPETA.match(str(nodo.values[0].value))
                if coincide:
                    rutas.append((coincide.group(1), ast.unparse(nodo)[2:-1]))
        if not rutas:
            continue
        carpeta = rutas[0][0]
        nombre = next((n for n, texto in vinetas if f'`{carpeta}/' in texto), funcion.name)
        resultado.append(Interfaz(funcion.name, nombre, archivo, funcion.lineno, carpeta,
                                  sorted({patron for _c, patron in rutas})))
    return resultado


def _vinetas(docstring: str) -> list[tuple[str, str]]:
    """(nombre en negritas, texto) de cada viñeta `- **Nombre** …` del docstring."""
    inicios = list(_VINETA.finditer(docstring))
    return [(m.group('nombre').strip(), docstring[m.start():inicios[i + 1].start() if i + 1 < len(inicios) else None])
            for i, m in enumerate(inicios)]
