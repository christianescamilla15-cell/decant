"""Extracción del UNIVERSO (lo que entra) del respaldo restaurado, POR COLUMNA según `universo/particion.py`.

El universo es: las columnas `llave_interna` y `entrada` de cada tabla del respaldo, la parte de entrada de cada
columna `mixta`, los archivos de interfaz que recibió el legado (buzón del corresponsal y archivo de sucursales) y el
horario del job en la copia de msdb. Ninguna columna `resultado` sale por aquí: el oráculo vive en `paridad/oraculo.py`
y en otra carpeta. Una prueba exige que cada consulta de este archivo pida exactamente las columnas de su categoría.

Las consultas son literales fijos (no se arman con texto); la prueba es la que las ata a la partición.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from paridad import formato
from universo.noches import horario

# tabla → (consulta, columnas que entrega). `tipo_cambio` es MIXTA: entra sólo cuando el cajero lo tecleó, que el
# legado marca con el centinela tipo_cambio_referencia = 0 (T3); en los demás renglones es resultado y va nulo.
CONSULTAS = {
    'dbo.moneda': (
        'SELECT codigo, numerico, nombre, decimales, activa FROM dbo.moneda ORDER BY codigo',
        ['codigo', 'numerico', 'nombre', 'decimales', 'activa']),
    'dbo.folio': (
        'SELECT serie FROM dbo.folio ORDER BY serie',
        ['serie']),
    'dbo.operacion': (
        'SELECT id, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda, monto_divisa, '
        'tipo_cambio_referencia, estatus, CASE WHEN tipo_cambio_referencia = 0 THEN tipo_cambio END '
        'FROM dbo.operacion ORDER BY id',
        ['id', 'fecha_operacion', 'sucursal', 'canal', 'cliente', 'cuenta_clabe', 'tipo', 'moneda', 'monto_divisa',
         'tipo_cambio_referencia', 'estatus', 'tipo_cambio']),
    'dbo.orden_pago': (
        'SELECT id, operacion_id, uetr, referencia_mt103, fecha_registro, fecha_envio, fecha_valor, bic_corresponsal, '
        'bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, gastos, codigo_proposito '
        'FROM dbo.orden_pago ORDER BY id',
        ['id', 'operacion_id', 'uetr', 'referencia_mt103', 'fecha_registro', 'fecha_envio', 'fecha_valor',
         'bic_corresponsal', 'bic_intermediario', 'beneficiario', 'cuenta_beneficiario', 'moneda', 'monto', 'gastos',
         'codigo_proposito']),
    'dbo.partida_solicitada': (
        'SELECT id, monto, fecha_hora, referencia FROM dbo.partida_solicitada ORDER BY id',
        ['id', 'monto', 'fecha_hora', 'referencia']),
}
# Tablas sin columnas de entrada: todo lo que guardan lo calcula el legado.
SIN_ENTRADAS = ('dbo.partida_liquidada', 'dbo.bitacora')
MIXTAS_PARTE_ENTRADA = {('dbo.operacion', 'tipo_cambio'): 'tipo_cambio_referencia = 0'}


def extraer(cursor, interfaces: Path, salida: Path, base: str, base_msdb: str) -> dict:
    """Escribe el universo en `salida` y devuelve su manifiesto (filas y sha256 por archivo)."""
    archivos = {}
    for tabla, (consulta, columnas) in CONSULTAS.items():
        cursor.execute(consulta)
        ruta = salida / f"{tabla.split('.')[1]}.jsonl"
        n = formato.escribir(ruta, columnas, cursor.fetchall())
        archivos[ruta.name] = {'tabla': tabla, 'columnas': columnas, 'filas': n, 'sha256': formato.sha256(ruta)}
    job = horario(cursor, base_msdb, base)
    ruta = salida / 'job.jsonl'
    formato.escribir(ruta, ['job', 'frecuencia', 'intervalo', 'hora'],
                     [[j['job'], j['frecuencia'], j['intervalo'], j['hora']] for j in job])
    archivos[ruta.name] = {'origen': 'horario del job en msdb (restaurada)', 'filas': len(job),
                           'sha256': formato.sha256(ruta)}
    destino = salida / 'interfaces'
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(interfaces, destino)
    copiados = sorted(p for p in destino.rglob('*') if p.is_file())
    return {
        'tablas': archivos,
        'interfaces': {'origen': str(interfaces), 'archivos': len(copiados),
                       'sha256': {str(p.relative_to(destino)): formato.sha256(p) for p in copiados}},
        'mixtas': {f'{t}.{c}': f'sólo la parte de entrada: {regla}' for (t, c), regla in
                   MIXTAS_PARTE_ENTRADA.items()},
    }
