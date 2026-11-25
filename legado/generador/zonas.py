"""Zonas horarias del legado, leídas SIEMPRE del paquete `tzdata` fijado en requirements.txt.

La base de zonas del sistema operativo cambia de una máquina a otra (México quitó el horario de verano en
oct-2022 y no todas las imágenes lo traen igual); si el generador la usara, la semilla dejaría de bastar para
reproducir los datos. Por eso se cargan los archivos TZif del paquete y no `ZoneInfo('...')` a secas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import tzdata

UTC = timezone.utc
_ZONAS = Path(tzdata.__file__).parent / 'zoneinfo'


def _zona(nombre: str) -> ZoneInfo:
    with (_ZONAS / nombre).open('rb') as archivo:
        return ZoneInfo.from_file(archivo, key=nombre)


# El legado guarda la hora LOCAL de la Ciudad de México; el corresponsal manda la de Nueva York.
CDMX = _zona('America/Mexico_City')
NUEVA_YORK = _zona('America/New_York')


def local(instante: datetime, zona: ZoneInfo = CDMX) -> datetime:
    """Instante UTC → hora local SIN zona, como la guarda el legado (se pierde si era la 1:30 repetida)."""
    return instante.astimezone(zona).replace(tzinfo=None)


def a_utc(hora_local: datetime, zona: ZoneInfo = CDMX) -> datetime:
    """Hora local (sin zona) → instante UTC. En la hora repetida toma la primera ocurrencia (fold=0)."""
    return hora_local.replace(tzinfo=zona).astimezone(UTC)
