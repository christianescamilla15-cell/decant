"""Acceso de sólo lectura al TO-BE en PostgreSQL y al CLI del TO-BE (`decant`)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import psycopg

RAIZ = Path(__file__).resolve().parent.parent
CLI = RAIZ / 'src' / 'Decant.Cli' / 'bin' / 'Release' / 'net10.0' / 'decant.dll'


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
