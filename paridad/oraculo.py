"""Extracción del ORÁCULO (lo que el legado calculó) del respaldo restaurado, POR COLUMNA según la partición.

El oráculo son las columnas `resultado` (más la parte de resultado de cada `mixta`), con la `llave_interna` para
juntarlas con su renglón del universo, y las salidas que el legado PUBLICÓ al tomar el respaldo (copiadas con su
sha256). La carga histórica (migración) lee universo y oráculo; el replay del motor, SÓLO el universo.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from paridad import formato

CONSULTAS = {
    'dbo.folio': (
        'SELECT serie, siguiente, actualizado FROM dbo.folio ORDER BY serie',
        ['serie', 'siguiente', 'actualizado']),
    'dbo.operacion': (
        'SELECT id, folio, monto_mxn, CASE WHEN tipo_cambio_referencia <> 0 THEN tipo_cambio END '
        'FROM dbo.operacion ORDER BY id',
        ['id', 'folio', 'monto_mxn', 'tipo_cambio']),
    'dbo.orden_pago': (
        'SELECT id, folio, estatus, horas_liquidacion FROM dbo.orden_pago ORDER BY id',
        ['id', 'folio', 'estatus', 'horas_liquidacion']),
    'dbo.partida_solicitada': (
        'SELECT id, orden_id, renglon, concepto, moneda FROM dbo.partida_solicitada ORDER BY id',
        ['id', 'orden_id', 'renglon', 'concepto', 'moneda']),
    'dbo.partida_liquidada': (
        'SELECT id, orden_id, renglon, concepto, moneda, monto, fecha_hora, referencia '
        'FROM dbo.partida_liquidada ORDER BY id',
        ['id', 'orden_id', 'renglon', 'concepto', 'moneda', 'monto', 'fecha_hora', 'referencia']),
}
# La bitácora es resultado del trigger, pero no se migra (retención: ADR 0004/0009); la paridad la lee directo del
# respaldo restaurado cuando la necesita (noches, sólo marca).
NO_SE_EXTRAEN = {'dbo.bitacora': 'retención: no se migra como tabla viva'}
MIXTAS_PARTE_RESULTADO = {('dbo.operacion', 'tipo_cambio'): 'tipo_cambio_referencia <> 0'}


def extraer(cursor, manifiesto: dict, carpeta_respaldo: Path, salida: Path) -> dict:
    archivos = {}
    for tabla, (consulta, columnas) in CONSULTAS.items():
        cursor.execute(consulta)
        ruta = salida / f"{tabla.split('.')[1]}.jsonl"
        n = formato.escribir(ruta, columnas, cursor.fetchall())
        archivos[ruta.name] = {'tabla': tabla, 'columnas': columnas, 'filas': n, 'sha256': formato.sha256(ruta)}
    publicadas = []
    for s in manifiesto.get('salidas', []):
        origen = carpeta_respaldo / s['archivo']
        if formato.sha256(origen) != s['sha256']:
            raise SystemExit(f"{s['archivo']}: el sha256 no coincide con el manifiesto del respaldo")
        destino = salida / 'publicadas' / s['archivo']
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, destino)
        publicadas.append({k: s[k] for k in ('nombre', 'procedimiento', 'parametros', 'conjunto', 'llave_natural',
                                              'llave_orden', 'archivo', 'filas', 'sha256')})
    return {'tablas': archivos, 'publicadas': publicadas, 'no_se_extraen': NO_SE_EXTRAEN,
            'mixtas': {f'{t}.{c}': f'sólo la parte de resultado: {r}' for (t, c), r in
                       MIXTAS_PARTE_RESULTADO.items()}}
