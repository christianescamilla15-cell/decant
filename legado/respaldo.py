"""Respaldo FECHADO del legado: BFN_DIVISAS y msdb (ahí vive el job), con un manifiesto que dice qué publicaba el
legado en ese instante.

El manifiesto lleva:
- las cifras del encabezado de la pantalla (operaciones y órdenes de pago), leídas antes y después;
- COUNT y MAX(id) de cada tabla, y los contadores de folio, en el instante del BACKUP;
- las SALIDAS que el legado publicaba (reporte del mes y lista del día anterior), capturadas en ese mismo instante:
  son el oráculo de los reportes, no una re-corrida posterior.

La fecha del nombre se MIDE de la fuente (día de la última operación). Si algo se mueve entre la primera y la
última lectura (pantalla o conteos), no hay respaldo.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from legado.conexion import conectar, contenedor, docker

DIRECTORIO_SERVIDOR = '/var/opt/mssql/backup'
BACKUP = {
    'BFN_DIVISAS': 'BACKUP DATABASE BFN_DIVISAS TO DISK = %s WITH FORMAT, INIT, CHECKSUM, COMPRESSION',
    'msdb': 'BACKUP DATABASE msdb TO DISK = %s WITH FORMAT, INIT, CHECKSUM, COMPRESSION',
}
# Etiqueta de la pantalla → atributo que la publica y tabla a la que se refiere (lo sabe quien toma el respaldo).
CIFRAS = (('Operaciones registradas', 'data-total-operaciones', 'dbo.operacion'),
          ('Órdenes de pago', 'data-total-ordenes', 'dbo.orden_pago'))


def cifras_pantalla(url: str) -> dict[str, int]:
    """Cifras que publica el encabezado de la pantalla del legado."""
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
    resultado = {}
    for etiqueta, atributo, _tabla in CIFRAS:
        coincide = re.search(rf'{atributo}="(\d+)"', cuerpo)
        if respuesta.status != 200 or not coincide:
            raise SystemExit(f'la pantalla no publicó «{etiqueta}» (HTTP {respuesta.status})')
        resultado[etiqueta] = int(coincide.group(1))
    return resultado


def cifra_pantalla(url: str) -> int:
    return cifras_pantalla(url)['Operaciones registradas']


def foto_tablas(cursor) -> tuple[dict, dict]:
    """COUNT y MAX(id) de cada tabla, y los contadores de folio, en este instante."""
    cursor.execute("SELECT s.name, t.name, c.name FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id "
                   "LEFT JOIN sys.identity_columns c ON c.object_id = t.object_id WHERE t.is_ms_shipped = 0 "
                   "ORDER BY s.name, t.name")
    tablas = {}
    for esquema, tabla, identidad in cursor.fetchall():
        cursor.execute(
            "DECLARE @t nvarchar(300) = QUOTENAME(%s) + N'.' + QUOTENAME(%s); "
            "DECLARE @sql nvarchar(max) = N'SELECT COUNT_BIG(*), ' + "
            "CASE WHEN %s IS NULL THEN N'NULL' ELSE N'MAX(' + QUOTENAME(%s) + N')' END + N' FROM ' + @t; "
            "EXEC sp_executesql @sql", (esquema, tabla, identidad, identidad))
        filas, maximo = cursor.fetchone()
        tablas[f'{esquema}.{tabla}'.lower()] = {'filas': filas, 'max_id': maximo}
    cursor.execute('SELECT serie, siguiente FROM dbo.folio ORDER BY serie')
    contadores = {'dbo.folio': {'llave': 'serie', 'valor': 'siguiente',
                                'filas': {serie.strip(): siguiente for serie, siguiente in cursor.fetchall()}}}
    return tablas, contadores


def _texto(valor) -> str | None:
    return None if valor is None else str(valor)


def capturar(cursor, procedimiento: str, parametros: list, conjunto: int) -> tuple[list[str], list[list]]:
    """Corre un procedimiento del legado y devuelve el conjunto de resultados pedido, con valores en texto."""
    cursor.callproc(procedimiento, tuple(parametros))
    indice = 0
    while True:
        if cursor.description:
            if indice == conjunto:
                columnas = [d[0] for d in cursor.description]
                return columnas, [[_texto(v) for v in fila] for fila in cursor.fetchall()]
            cursor.fetchall()
            indice += 1
        if not cursor.nextset():
            raise SystemExit(f'{procedimiento} no devolvió el conjunto {conjunto}')


def salidas_a_capturar(fecha: date) -> list[dict]:
    return [
        {'nombre': 'reporte_del_mes', 'procedimiento': 'dbo.sp_reporte_ordenes',
         'parametros': [fecha.replace(day=1).isoformat(), fecha.isoformat()], 'conjunto': 0,
         'llave_natural': ['folio', 'concepto'], 'llave_orden': ['fecha_valor']},
        # sin ORDER BY no hay contrato de orden: todos los pares son libres
        {'nombre': 'lista_del_dia_anterior', 'procedimiento': 'dbo.sp_lista_operaciones',
         'parametros': [(fecha - timedelta(days=1)).isoformat(), 200], 'conjunto': 1,
         'llave_natural': ['folio'], 'llave_orden': []},
    ]


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
    antes, leido_antes = cifras_pantalla(url_pantalla), _ahora()
    with conectar() as conexion:
        cursor = conexion.cursor()
        cursor.execute('SELECT CAST(MAX(fecha_operacion) AS date) FROM dbo.operacion')
        fecha = cursor.fetchone()[0]
        tablas, contadores = foto_tablas(cursor)
        docker('exec', contenedor(), 'mkdir', '-p', DIRECTORIO_SERVIDOR)
        archivos = []
        for base, sentencia in BACKUP.items():
            nombre = f'{base.lower()}_{fecha.isoformat()}.bak'
            cursor.execute(sentencia, (f'{DIRECTORIO_SERVIDOR}/{nombre}',))
            while cursor.nextset():
                pass
            archivos.append((base, nombre))
        tomado = _ahora()
        salidas = []
        for s in salidas_a_capturar(fecha):
            columnas, filas = capturar(cursor, s['procedimiento'], s['parametros'], s['conjunto'])
            ruta = salida / f"salida_{s['nombre']}_{fecha.isoformat()}.jsonl"
            with ruta.open('w', encoding='utf-8') as archivo:
                archivo.write(json.dumps(columnas, ensure_ascii=False) + '\n')
                for fila in filas:
                    archivo.write(json.dumps(fila, ensure_ascii=False) + '\n')
            salidas.append({**s, 'archivo': ruta.name, 'filas': len(filas), 'sha256': _sha256(ruta)})
        if foto_tablas(cursor) != (tablas, contadores):
            raise SystemExit('el legado se movió durante el respaldo: los conteos cambiaron')
    despues, leido_despues = cifras_pantalla(url_pantalla), _ahora()
    if antes != despues:
        raise SystemExit(f'el legado se movió durante el respaldo: la pantalla pasó de {antes} a {despues}')
    manifiesto = {
        'base': 'BFN_DIVISAS',
        'fecha_negocio': fecha.isoformat(),
        'tomado_utc': tomado,
        'tabla_principal': 'dbo.operacion',
        'pantalla': {'url': url_pantalla, 'leido_antes_utc': leido_antes, 'leido_despues_utc': leido_despues,
                     'cifras': [{'etiqueta': e, 'atributo': a, 'tabla': t, 'valor': antes[e]} for e, a, t in CIFRAS]},
        'tablas': tablas,
        'contadores': contadores,
        'salidas': salidas,
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
