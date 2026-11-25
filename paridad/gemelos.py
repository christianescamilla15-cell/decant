"""GEMELOS: la pantalla de detalle del legado contra el JSON de la API del TO-BE, caso por caso.

Los dos leen el MISMO momento: la pantalla del legado sobre el respaldo restaurado y la API del TO-BE sobre la carga
histórica. Cada campo de la pantalla tiene su lugar en el JSON (o una razón para no estar), y las dos rejillas se
comparan por el BINDING de la pantalla (T4): la rejilla «Liquidado por el corresponsal» contra el campo del TO-BE con
ese nombre, sin importar cómo se llama la tabla del legado.
"""
from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from legado.extraer_pantalla import leer_detalle
from paridad.binding import campo_json, rejillas
from paridad.mapeo import aplicar

RAIZ = Path(__file__).resolve().parent.parent
API = RAIZ / 'src' / 'Decant.Api' / 'bin' / 'Release' / 'net10.0' / 'Decant.Api.dll'

# campo de la pantalla → (ruta en el JSON, normalización documentada)
CAMPOS = {
    'id': ('operacion.id', None), 'folio': ('operacion.folio', None),
    'fecha_operacion': ('operacion.fechaOperacion', 'hora_local'), 'sucursal': ('operacion.sucursal', ('char:4',)),
    'canal': ('operacion.canal', None), 'cliente': ('operacion.cliente', None),
    'cuenta_clabe': ('operacion.cuentaClabe', ('T3_texto',)), 'tipo': ('operacion.tipo', ('char:1',)),
    'moneda': ('operacion.moneda', ('char:3',)), 'nombre_moneda': ('operacion.nombreMoneda', None),
    'decimales': ('operacion.decimales', None), 'monto_divisa': ('operacion.montoDivisa', None),
    'tipo_cambio': ('operacion.tipoCambio', None),
    'tipo_cambio_referencia': ('operacion.tipoCambioReferencia', ('T3_numero',)),
    'monto_mxn': ('operacion.montoMxn', None), 'estatus': ('operacion.estatus', None),
    'folio_orden': ('orden.folio', None), 'uetr': ('orden.uetr', None),
    'referencia_mt103': ('orden.referenciaMt103', None), 'fecha_registro': ('orden.fechaRegistro', 'hora_local'),
    'fecha_envio': ('orden.fechaEnvio', 'hora_local'), 'fecha_valor': ('orden.fechaValor', None),
    'bic_corresponsal': ('orden.bicCorresponsal', ('char:11',)),
    'bic_intermediario': ('orden.bicIntermediario', ('char:11', 'T3_texto')),
    'beneficiario': ('orden.beneficiario', None), 'cuenta_beneficiario': ('orden.cuentaBeneficiario', None),
    'monto_orden': ('orden.monto', None), 'gastos': ('orden.gastos', ('char:3',)),
    'estatus_orden': ('orden.estatus', None),
    'horas_liquidacion': ('orden.horasLiquidacion', None),
}
NO_EXPUESTOS = {'orden_id': 'llave interna del legado (cambia con cada re-registro); el TO-BE expone la UETR'}
PARTIDA = {'#': ('renglon', None), 'Concepto': ('concepto', None), 'Moneda': ('moneda', ('char:3',)),
           'Monto': ('monto', None), 'Fecha y hora': ('fechaHora', 'hora_local'),
           'Referencia': ('referencia', ('ciega1_T3',))}

# Casos estratificados (estatus × forma): los elige el legado restaurado, siempre los mismos para la misma semilla.
CASOS = {
    'conciliada con re-registros y gastos OUR': """
        SELECT TOP 1 p.operacion_id FROM dbo.orden_pago p WHERE p.estatus = 'CONCILIADA' AND p.gastos = 'OUR'
          AND (SELECT COUNT(*) FROM dbo.orden_pago r WHERE r.uetr = p.uetr) >= 3 ORDER BY p.id""",
    'diferencia en yenes (D2)': """
        SELECT TOP 1 p.operacion_id FROM dbo.orden_pago p WHERE p.estatus = 'DIFERENCIA' AND p.moneda = 'JPY'
        ORDER BY p.id""",
    'vencida sin partidas del corresponsal, en efectivo (T3)': """
        SELECT TOP 1 p.operacion_id FROM dbo.orden_pago p JOIN dbo.operacion o ON o.id = p.operacion_id
        WHERE p.estatus = 'VENCIDA' AND o.cuenta_clabe = 'NA' ORDER BY p.id""",
}


def _get(puerto: int, ruta: str) -> tuple[int, str]:
    conexion = http.client.HTTPConnection('127.0.0.1', puerto, timeout=30)
    try:
        conexion.request('GET', ruta)
        respuesta = conexion.getresponse()
        return respuesta.status, respuesta.read().decode('utf-8')
    finally:
        conexion.close()


def _esperar(puerto: int, ruta: str, proceso: subprocess.Popen, segundos: int = 60) -> None:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            raise SystemExit(f'el proceso en el puerto {puerto} terminó antes de responder')
        try:
            if _get(puerto, ruta)[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit(f'nada responde en el puerto {puerto}{ruta}')


def _valor_json(documento: dict, ruta: str):
    valor = documento
    for parte in ruta.split('.'):
        if valor is None:
            return None
        valor = valor.get(parte)
    return valor


def _normalizar(legado: str, tobe, regla, fila: dict | None = None) -> tuple[str | None, str | None]:
    """Texto esperado (el de la pantalla con sus parches EXACTOS de `paridad/mapeo.py`) y texto del TO-BE."""
    esperado: str | None = legado
    if isinstance(regla, tuple):
        esperado = aplicar(regla, legado, fila=fila)
    if tobe is None:
        return esperado, None
    if regla == 'hora_local':
        local = datetime.fromisoformat(str(tobe)).replace(tzinfo=None)
        return esperado, local.isoformat(sep=' ')
    if isinstance(tobe, bool):
        return esperado, '1' if tobe else '0'
    return esperado, str(tobe)


def comparar_caso(pantalla: int, api: int, operacion_id: int) -> dict:
    estado, html = _get(pantalla, f'/operacion/{operacion_id}')
    estado_api, cuerpo = _get(api, f'/api/operaciones/{operacion_id}')
    if estado != 200 or estado_api != 200:
        return {'operacion': operacion_id, 'error': f'pantalla {estado}, API {estado_api}', 'cumple': False}
    vista = leer_detalle(html)
    documento = json.loads(cuerpo, parse_float=Decimal)
    campos, distintos = 0, []
    for campo, valor in vista['encabezado'].items():
        if campo in NO_EXPUESTOS:
            continue
        if campo not in CAMPOS:
            distintos.append({'campo': campo, 'pantalla': valor, 'tobe': 'SIN LUGAR EN EL JSON'})
            continue
        ruta, regla = CAMPOS[campo]
        esperado, obtenido = _normalizar(valor, _valor_json(documento, ruta), regla)
        campos += 1
        if (esperado or None) != (obtenido or None):
            distintos.append({'campo': campo, 'pantalla': valor, 'esperado': esperado, 'tobe': obtenido})
    rejillas_comparadas = []
    for r in rejillas():
        renglones_pantalla = vista['rejillas'].get(r['id'], [])
        campo = campo_json(r['titulo'])
        renglones_tobe = documento.get(campo) or []
        iguales = len(renglones_pantalla) == len(renglones_tobe)
        for fila_p, fila_t in zip(renglones_pantalla, renglones_tobe):
            for titulo, (clave, regla) in PARTIDA.items():
                contexto = {'fecha_hora': datetime.fromisoformat(fila_p['Fecha y hora'])}
                esperado, obtenido = _normalizar(fila_p[titulo], fila_t.get(clave), regla, contexto)
                campos += 1
                if esperado != obtenido:
                    iguales = False
                    distintos.append({'campo': f"{r['id']}.{titulo}", 'pantalla': fila_p[titulo],
                                      'esperado': esperado, 'tobe': obtenido})
        rejillas_comparadas.append({'rejilla': r['id'], 'titulo': r['titulo'], 'campo_tobe': campo,
                                    'renglones': len(renglones_pantalla), 'iguales': iguales})
    return {'operacion': operacion_id, 'campos_comparados': campos, 'distintos': distintos,
            'rejillas': rejillas_comparadas, 'cumple': not distintos}


def gemelos(restaurado, puerto_pantalla: int, puerto_api: int, conexion_tobe: str) -> dict:
    """Levanta la pantalla del legado (sobre el restaurado) y la API del TO-BE (sobre la carga histórica)."""
    if not API.exists():
        raise SystemExit(f'No está compilada la API del TO-BE (dotnet build -c Release): {API}')
    with restaurado.conectar() as c:
        cursor = c.cursor()
        casos = {}
        for nombre, consulta in CASOS.items():
            cursor.execute(consulta)
            fila = cursor.fetchone()
            if fila:
                casos[nombre] = fila[0]
    s = restaurado.servidor
    entorno_pantalla = {**os.environ, 'DECANT_SQL_HOST': '127.0.0.1', 'DECANT_PUERTO': str(s.puerto),
                        'DECANT_SA_PASSWORD': s.contrasena}
    entorno_api = {**os.environ, 'ASPNETCORE_ENVIRONMENT': 'Pruebas', 'ConnectionStrings__Decant': conexion_tobe,
                   'ASPNETCORE_URLS': f'http://127.0.0.1:{puerto_api}'}
    pantalla = subprocess.Popen([sys.executable, '-m', 'legado', 'pantalla', '--puerto', str(puerto_pantalla)],
                                cwd=RAIZ, env=entorno_pantalla, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    api = subprocess.Popen(['dotnet', str(API)], cwd=API.parent, env=entorno_api, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    try:
        _esperar(puerto_pantalla, '/salud', pantalla)
        _esperar(puerto_api, '/salud', api)
        resultados = {nombre: comparar_caso(puerto_pantalla, puerto_api, op) for nombre, op in casos.items()}
    finally:
        for proceso in (pantalla, api):
            proceso.terminate()
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()
    return {'casos': resultados, 'no_expuestos': NO_EXPUESTOS,
            'cumple': bool(resultados) and all(r['cumple'] for r in resultados.values())}
