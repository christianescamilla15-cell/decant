"""El respaldo FECHADO restaurado en un contenedor LIMPIO: la única fuente del legado para la paridad.

Reutiliza la restauración de la radiografía (`radiografia.sqlserver`) sin cambiarla: contenedor nuevo con
contraseña aleatoria, sha256 contra el manifiesto, `RESTORE VERIFYONLY` y `RESTORE` de BFN_DIVISAS y de msdb
(como `legado_msdb`, ahí vive el horario del job).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from paridad.formato import sha256
from radiografia import sqlserver

BASE = 'BFN_DIVISAS'
MSDB = 'legado_msdb'


@dataclass
class Restaurado:
    servidor: sqlserver.Servidor
    manifiesto: dict
    carpeta: Path

    def conectar(self, base: str = BASE):
        return self.servidor.conectar(base)


def leer_manifiesto(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding='utf-8'))


@contextmanager
def restaurar(ruta_manifiesto: Path, conservar: bool = False):
    manifiesto = leer_manifiesto(ruta_manifiesto)
    carpeta = ruta_manifiesto.parent
    servidor = sqlserver.arrancar_limpio()
    try:
        for archivo in manifiesto['archivos']:
            ruta = carpeta / archivo['nombre']
            if sha256(ruta) != archivo['sha256']:
                raise SystemExit(f'{ruta.name}: el sha256 no coincide con el manifiesto; no se restaura')
            disco = servidor.copiar(str(ruta))
            servidor.verificar(disco)
            servidor.restaurar(disco, MSDB if archivo['base'].lower() == 'msdb' else archivo['base'])
        yield Restaurado(servidor, manifiesto, carpeta)
    finally:
        if not conservar:
            servidor.cerrar()
