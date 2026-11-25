"""Conexión al SQL Server del legado (docker compose) y utilidades mínimas."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pymssql

BASE = 'BFN_DIVISAS'
RAIZ = Path(__file__).resolve().parent
SQL = RAIZ / 'sql'
_GO = re.compile(r'^\s*GO\s*$', re.IGNORECASE | re.MULTILINE)


def contrasena() -> str:
    valor = os.environ.get('DECANT_SA_PASSWORD')
    if not valor:
        raise SystemExit('Falta DECANT_SA_PASSWORD (la contraseña de sa del contenedor del legado).')
    return valor


def conectar(base: str = BASE, puerto: int | None = None, autocommit: bool = True) -> pymssql.Connection:
    return pymssql.connect(
        server=os.environ.get('DECANT_SQL_HOST', '127.0.0.1'),
        port=int(puerto or os.environ.get('DECANT_PUERTO', '14330')),
        user='sa', password=contrasena(), database=base, autocommit=autocommit,
        tds_version='7.4', charset='UTF-8', login_timeout=15, timeout=900)


def lotes(texto: str) -> list[str]:
    """Separa un script de T-SQL en lotes por las líneas `GO` (como sqlcmd)."""
    return [lote.strip() for lote in _GO.split(texto) if lote.strip()]


def ejecutar_script(conexion: pymssql.Connection, ruta: Path) -> int:
    cursor = conexion.cursor()
    n = 0
    for lote in lotes(ruta.read_text(encoding='utf-8')):
        cursor.execute(lote)
        while cursor.nextset():
            pass
        n += 1
    return n


def contenedor() -> str:
    return os.environ.get('DECANT_CONTENEDOR', 'decant-legado')


def docker(*argumentos: str, capturar: bool = True) -> subprocess.CompletedProcess:
    """Llama a la CLI de Docker con una lista de argumentos (nunca a través de un shell)."""
    return subprocess.run(['docker', *argumentos], check=True, capture_output=capturar, text=True)
