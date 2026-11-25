"""Acceso de sólo lectura al TO-BE en PostgreSQL y al CLI del TO-BE (`decant`)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / 'src' / 'Decant.Cli' / 'bin' / 'Release' / 'net10.0' / 'decant.dll'

# Lo que decide el contenido de las cargas: el TO-BE y la extracción de universo y oráculo.
FUENTES_DE_LAS_CARGAS = ('src', 'Directory.Build.props', 'Directory.Packages.props', 'global.json', 'universo',
                         'paridad/extraer.py', 'paridad/universo.py', 'paridad/oraculo.py')
_GENERADOS = {'bin', 'obj', '__pycache__'}
LLAVE_DE_CARGAS = 'cargas.json'


def llave_de_cargas(manifiesto: Path, raiz: Path = RAIZ) -> str:
    """sha256 del código que produce las cargas (sin bin/obj) y del respaldo de origen: la llave para reutilizarlas."""
    h = hashlib.sha256(Path(manifiesto).read_bytes())
    for fuente in FUENTES_DE_LAS_CARGAS:
        ruta = raiz / fuente
        if ruta.is_file():
            archivos = [ruta]
        else:
            archivos = sorted(a for a in ruta.rglob('*')
                              if a.is_file() and not _GENERADOS & set(a.relative_to(raiz).parts))
        for archivo in archivos:
            h.update(str(archivo.relative_to(raiz)).encode('utf-8') + b'\0' + archivo.read_bytes() + b'\0')
    return h.hexdigest()


def guardar_llave(datos: Path, llave: str) -> None:
    (datos / LLAVE_DE_CARGAS).write_text(json.dumps({'llave': llave}) + '\n', encoding='utf-8')


def verificar_reuso(datos: Path, llave: str) -> None:
    """--reusar-cargas sólo con cargas hechas por ESTE código y ESTE respaldo; si no, se vuelve a cargar."""
    archivo = datos / LLAVE_DE_CARGAS
    guardada = json.loads(archivo.read_text(encoding='utf-8'))['llave'] if archivo.exists() else None
    if guardada != llave:
        raise SystemExit(f'--reusar-cargas: las cargas guardadas en {datos} son de otra versión del código o de otro '
                         f'respaldo ({(guardada or "sin llave")[:12]} ≠ {llave[:12]}); corre sin --reusar-cargas')


def parametros() -> dict:
    """Conexión base a PostgreSQL (sin la base), de las mismas variables que usa el TO-BE."""
    clave = os.environ.get('DECANT_PG_PASSWORD')
    if not clave:
        raise SystemExit('Falta DECANT_PG_PASSWORD (contraseña del PostgreSQL del TO-BE).')
    return {'host': os.environ.get('DECANT_PG_HOST', '127.0.0.1'), 'port': int(os.environ.get('DECANT_PG_PUERTO',
            '15450')), 'user': os.environ.get('DECANT_PG_USUARIO', 'decant'), 'password': clave}


def conectar(base: str) -> psycopg.Connection:
    conexion = psycopg.connect(dbname=base, autocommit=True, **parametros())
    conexion.execute("SET TIME ZONE 'UTC'")
    return conexion


def cadena_dotnet() -> str:
    p = parametros()
    return f"Host={p['host']};Port={p['port']};Username={p['user']};Password={p['password']}"


def decant(*argumentos: str) -> dict | str:
    """Corre el CLI del TO-BE (ya compilado en Release). Devuelve su JSON si imprime uno."""
    if not CLI.exists():
        raise SystemExit(f'No está compilado el TO-BE: dotnet build src/Decant.Cli -c Release ({CLI})')
    entorno = {**os.environ, 'DECANT_PG': cadena_dotnet()}
    salida = subprocess.run(['dotnet', str(CLI), *argumentos], check=True, capture_output=True, text=True,
                            env=entorno).stdout
    try:
        return json.loads(salida)
    except json.JSONDecodeError:
        return salida.strip()
