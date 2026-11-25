"""Respaldo FECHADO del legado: BFN_DIVISAS y msdb (ahí vive el job) con la cifra que publica la pantalla.

La fecha del nombre se MIDE de la fuente (día de la última operación), no se escribe a mano. La pantalla se lee
antes y después del BACKUP: si las dos cifras no coinciden, el legado se movió durante la foto y no hay respaldo.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from legado.conexion import conectar, contenedor, docker

DIRECTORIO_SERVIDOR = '/var/opt/mssql/backup'
BACKUP = {
    'BFN_DIVISAS': 'BACKUP DATABASE BFN_DIVISAS TO DISK = %s WITH FORMAT, INIT, CHECKSUM, COMPRESSION',
    'msdb': 'BACKUP DATABASE msdb TO DISK = %s WITH FORMAT, INIT, CHECKSUM, COMPRESSION',
}


def cifra_pantalla(url: str) -> int:
    """Total de operaciones que publica el encabezado de la pantalla del legado."""
    partes = urlsplit(url)
    if partes.scheme != 'http' or not partes.hostname:
        raise SystemExit(f'URL de la pantalla no válida: {url}')
    conexion = http.client.HTTPConnection(partes.hostname, partes.port or 80, timeout=60)
    try:
        conexion.request('GET', '/')
        respuesta = conexion.getresponse()
        cuerpo = respuesta.read().decode('utf-8')
    finally:
        conexion.close()
    coincide = re.search(r'data-total-operaciones="(\d+)"', cuerpo)
    if respuesta.status != 200 or not coincide:
        raise SystemExit(f'la pantalla no publicó su total (HTTP {respuesta.status})')
    return int(coincide.group(1))


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def respaldar(url_pantalla: str, salida: Path) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    antes, leido_antes = cifra_pantalla(url_pantalla), _ahora()
    with conectar() as conexion:
        cursor = conexion.cursor()
        cursor.execute('SELECT CAST(MAX(fecha_operacion) AS date) FROM dbo.operacion')
        fecha = cursor.fetchone()[0]
        docker('exec', contenedor(), 'mkdir', '-p', DIRECTORIO_SERVIDOR)
        archivos = []
        for base, sentencia in BACKUP.items():
            nombre = f'{base.lower()}_{fecha.isoformat()}.bak'
            cursor.execute(sentencia, (f'{DIRECTORIO_SERVIDOR}/{nombre}',))
            while cursor.nextset():
                pass
            archivos.append((base, nombre))
        tomado = _ahora()
    despues, leido_despues = cifra_pantalla(url_pantalla), _ahora()
    if antes != despues:
        raise SystemExit(f'el legado se movió durante el respaldo: la pantalla pasó de {antes} a {despues}')
    manifiesto = {
        'base': 'BFN_DIVISAS',
        'fecha_negocio': fecha.isoformat(),
        'tomado_utc': tomado,
        'tabla_principal': 'dbo.operacion',
        'pantalla': {'url': url_pantalla, 'total_operaciones': antes, 'leido_antes_utc': leido_antes,
                     'leido_despues_utc': leido_despues},
        'archivos': [],
    }
    for base, nombre in archivos:
        destino = salida / nombre
        docker('cp', f'{contenedor()}:{DIRECTORIO_SERVIDOR}/{nombre}', str(destino))
        manifiesto['archivos'].append({'base': base, 'nombre': nombre, 'bytes': destino.stat().st_size,
                                       'sha256': _sha256(destino)})
    ruta = salida / f'respaldo_{fecha.isoformat()}.json'
    ruta.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifiesto['ruta'] = str(ruta)
    return manifiesto
