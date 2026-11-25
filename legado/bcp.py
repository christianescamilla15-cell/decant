"""El daño de `bcp -c` sobre columnas Unicode, medido en el contenedor del legado.

En Windows, `bcp -c` escribe con la página ANSI del cliente (1252 en un equipo en español): lo que no cabe en ella
sale como `?` y el archivo deja de ser UTF-8. En Linux, mssql-tools18 escribe UTF-8; para reproducir lo que hace
un servidor Windows se fuerza `-C 1252`. La referencia es la exportación `-w` (UTF-16), que no pierde nada.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from legado.conexion import contenedor, docker

CONSULTAS = {
    'operacion.cliente': 'SELECT id, cliente FROM BFN_DIVISAS.dbo.operacion ORDER BY id',
    'orden_pago.beneficiario': 'SELECT id, beneficiario FROM BFN_DIVISAS.dbo.orden_pago ORDER BY id',
}
# La consulta y el modo llegan como argumentos posicionales de bash; la contraseña se queda en el contenedor.
_EXPORTAR = ('/opt/mssql-tools18/bin/bcp "$1" queryout "$2" $3 -t "|" -S localhost -U sa '
             '-P "$MSSQL_SA_PASSWORD" -u > /dev/null')


def _exportar(consulta: str, destino: str, modo: str) -> None:
    docker('exec', contenedor(), 'bash', '-c', _EXPORTAR, '_', consulta, destino, modo)


def medir() -> dict[str, dict[str, int]]:
    resultado = {}
    with tempfile.TemporaryDirectory() as tmp:
        for nombre, consulta in CONSULTAS.items():
            archivos = {}
            for modo, bandera in (('c1252', '-c -C 1252'), ('w', '-w')):
                remoto = f'/tmp/decant_bcp_{modo}.txt'
                _exportar(consulta, remoto, bandera)
                local = Path(tmp) / f'{modo}.txt'
                docker('cp', f'{contenedor()}:{remoto}', str(local))
                archivos[modo] = local.read_bytes()
            resultado[nombre] = comparar(archivos['w'], archivos['c1252'])
    return resultado


def comparar(utf16: bytes, ansi: bytes) -> dict[str, int]:
    """Compara renglón por renglón la exportación -w (verdad) con la -c en página 1252."""
    verdad = utf16.decode('utf-16').splitlines()
    crudos = ansi.splitlines()
    dañadas = con_interrogacion = no_utf8 = 0
    for original, crudo in zip(verdad, crudos):
        leido = crudo.decode('cp1252', errors='replace')
        if leido != original:
            dañadas += 1
            if '?' in leido and '?' not in original:
                con_interrogacion += 1
        try:
            if crudo.decode('utf-8') != original:
                no_utf8 += 1
        except UnicodeDecodeError:
            no_utf8 += 1
    return {'filas': len(verdad), 'distintas_en_1252': dañadas, 'con_signos_de_interrogacion': con_interrogacion,
            'ilegibles_como_utf8': no_utf8}
