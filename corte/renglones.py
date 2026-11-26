"""Renglones de la puerta (`corte/inventario/renglones.yml`): un renglón por objeto y por login, con su destino.

- `comparado`: su salida se compara contra la del TO-BE; `reemplazado_con_paridad`: el TO-BE hace lo que hacía, con
  paridad medida. Los dos exigen evidencia `archivo::prueba`, y la prueba TIENE que existir en el repo (se busca en el
  código con `ast`): una cobertura que no apunta a una prueba real no cuenta.
- `retirado`: exige dueño, fecha y la confirmación del vigía en sólo lectura después del corte (ADR 0016). El
  silencio de las estadísticas no basta: nada pasa a retirado solo.
- `pendiente`: lo que falta. La puerta lo lista.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import date
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

DESTINOS = ('comparado', 'reemplazado_con_paridad', 'retirado', 'pendiente')
CON_EVIDENCIA = ('comparado', 'reemplazado_con_paridad')
_EVIDENCIA = re.compile(r'^(?P<archivo>[\w./-]+\.py)::(?P<prueba>\w+)(\[.*\])?$')


@dataclass
class Renglon:
    clase: str                  # objeto o login
    clave: str
    destino: str
    evidencia: list[str] = field(default_factory=list)
    nota: str | None = None
    dueno: str | None = None
    fecha: str | None = None
    confirmacion_vigia: str | None = None
    aplicaciones: list[str] | None = None     # sólo logins: patrones (fnmatch) de las aplicaciones conocidas

    def aplicacion_conocida(self, aplicacion: str) -> bool:
        return self.aplicaciones is None or any(fnmatchcase(aplicacion, p) for p in self.aplicaciones)


def cargar(ruta: Path) -> tuple[list[Renglon], list[str]]:
    """Renglones y errores de FORMATO (claves faltantes, campos desconocidos)."""
    datos = yaml.safe_load(ruta.read_text(encoding='utf-8')) or {}
    renglones, errores = [], []
    for clase, plural in (('objeto', 'objetos'), ('login', 'logins')):
        for i, crudo in enumerate(datos.get(plural) or []):
            if not isinstance(crudo, dict) or clase not in crudo:
                errores.append(f'{plural}[{i}]: falta «{clase}»')
                continue
            desconocidos = set(crudo) - {clase, 'destino', 'evidencia', 'nota', 'dueno', 'fecha',
                                          'confirmacion_vigia', 'aplicaciones'}
            if desconocidos:
                errores.append(f'{crudo[clase]}: campos desconocidos {sorted(desconocidos)}')
            fecha = crudo.get('fecha')
            renglones.append(Renglon(
                clase, str(crudo[clase]), str(crudo.get('destino', '')), [str(e) for e in crudo.get('evidencia') or []],
                crudo.get('nota'), crudo.get('dueno'), fecha.isoformat() if isinstance(fecha, date) else fecha,
                crudo.get('confirmacion_vigia'),
                [str(a) for a in crudo['aplicaciones']] if crudo.get('aplicaciones') is not None else None))
    return renglones, errores


def validar(r: Renglon, raiz: Path) -> list[str]:
    """Errores de un renglón: destino válido, evidencia que existe, y lo que exige un retiro."""
    errores = []
    if r.destino not in DESTINOS:
        errores.append(f'destino «{r.destino}» no es uno de {", ".join(DESTINOS)}')
    if r.destino in CON_EVIDENCIA and not r.evidencia:
        errores.append(f'«{r.destino}» sin evidencia (archivo::prueba)')
    for evidencia in r.evidencia:
        problema = prueba_inexistente(evidencia, raiz)
        if problema:
            errores.append(problema)
    if r.destino == 'retirado':
        if not r.dueno:
            errores.append('retirado sin dueño')
        if not _es_fecha(r.fecha):
            errores.append('retirado sin fecha (AAAA-MM-DD)')
        if not r.confirmacion_vigia:
            errores.append('retirado sin la confirmación del vigía en sólo lectura después del corte (ADR 0016): '
                           'el silencio de las estadísticas no basta')
    return errores


def _es_fecha(valor) -> bool:
    try:
        date.fromisoformat(str(valor))
    except ValueError:
        return False
    return True


def prueba_inexistente(evidencia: str, raiz: Path) -> str | None:
    """None si `archivo::prueba` existe (función de prueba en el módulo o en una clase); si no, por qué no."""
    m = _EVIDENCIA.match(evidencia)
    if not m:
        return f'evidencia «{evidencia}» no tiene la forma archivo.py::prueba'
    ruta = (raiz / m.group('archivo')).resolve()
    if not ruta.is_relative_to(raiz.resolve()) or not ruta.is_file():
        return f'evidencia «{evidencia}»: no existe el archivo'
    arbol = ast.parse(ruta.read_text(encoding='utf-8'))
    nombres = {n.name for n in ast.walk(arbol) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if m.group('prueba') not in nombres:
        return f'evidencia «{evidencia}»: no existe la prueba'
    return None
