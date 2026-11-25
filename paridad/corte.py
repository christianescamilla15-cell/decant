"""El CORTE se mide de la fuente (el respaldo restaurado), nunca es una constante.

- Por identidad: COUNT y MAX(id) de cada tabla. Lo que el legado vivo tenga por encima es posterior al corte, sea cual
  sea su fecha de negocio (las altas fechadas hacia atrás tienen fecha anterior e id posterior).
- Por instante: la última escritura registrada. La bitácora sella con la hora del servidor (Ciudad de México) cada
  alta y cada cambio de estatus de una orden, incluidas las liquidaciones; las operaciones no pasan por la bitácora y
  se cuentan por su `fecha_operacion`. El instante del corte es el mayor de los dos, convertido a UTC.

Un evento del universo POSTERIOR a este instante y que el respaldo no tiene es candidato a AVANCE de producción; uno
anterior no puede serlo.
"""
from __future__ import annotations

from datetime import timezone

from legado.generador.zonas import a_utc

# Consultas fijas (sin armar SQL con texto): una por tabla.
CONTEOS = {
    'dbo.moneda': 'SELECT COUNT_BIG(*), NULL FROM dbo.moneda',
    'dbo.folio': 'SELECT COUNT_BIG(*), NULL FROM dbo.folio',
    'dbo.operacion': 'SELECT COUNT_BIG(*), MAX(id) FROM dbo.operacion',
    'dbo.orden_pago': 'SELECT COUNT_BIG(*), MAX(id) FROM dbo.orden_pago',
    'dbo.partida_solicitada': 'SELECT COUNT_BIG(*), MAX(id) FROM dbo.partida_solicitada',
    'dbo.partida_liquidada': 'SELECT COUNT_BIG(*), MAX(id) FROM dbo.partida_liquidada',
    'dbo.bitacora': 'SELECT COUNT_BIG(*), MAX(id) FROM dbo.bitacora',
}


def medir(cursor) -> dict:
    tablas = {}
    for tabla, consulta in CONTEOS.items():
        cursor.execute(consulta)
        filas, max_id = cursor.fetchone()
        tablas[tabla] = {'filas': filas, 'max_id': max_id}
    cursor.execute('SELECT MAX(fecha) FROM dbo.bitacora')
    bitacora = cursor.fetchone()[0]
    cursor.execute('SELECT MAX(fecha_operacion) FROM dbo.operacion')
    operacion = cursor.fetchone()[0]
    ultima_local = max(bitacora, operacion)
    return {
        'tablas': tablas,
        'ultima_escritura_bitacora_local': bitacora.isoformat(),
        'ultima_operacion_local': operacion.isoformat(),
        'instante_local': ultima_local.isoformat(),
        'instante_utc': a_utc(ultima_local).astimezone(timezone.utc).isoformat(),
        'regla': 'mayor sello de la bitácora o fecha_operacion (hora de la Ciudad de México), convertido a UTC; '
                 'por identidad, MAX(id) de cada tabla',
    }
