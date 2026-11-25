"""Horas de la PARIDAD, sin compartir código con la fuente de la verdad.

El generador (`legado/generador/zonas.py`) lee los archivos TZif del paquete `tzdata` FIJADO. El verificador no debe
reutilizarlo: aquí se usa `zoneinfo` directo, que toma la base de zonas del sistema (`zoneinfo.TZPATH`) y sólo si
no la encuentra cae al paquete. Una prueba contrasta las dos conversiones en las ventanas de cambio de horario y en
la hora que se repite (`tests/test_paridad.py`).
"""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timedelta, timezone

CDMX = zoneinfo.ZoneInfo('America/Mexico_City')
NUEVA_YORK = zoneinfo.ZoneInfo('America/New_York')
UTC = timezone.utc


def a_utc(hora_local: datetime, zona: zoneinfo.ZoneInfo, vuelta: int = 0) -> datetime:
    """Hora local sin zona → instante UTC. `vuelta` 0 es la primera ocurrencia de una hora repetida (y, en la hora que
    no existe, el desfase de antes del cambio); 1, la segunda."""
    return hora_local.replace(tzinfo=zona, fold=vuelta).astimezone(UTC)


def es_ambigua(hora_local: datetime, zona: zoneinfo.ZoneInfo) -> bool:
    """¿Esa hora local ocurrió dos veces (al terminar el horario de verano)?"""
    return hora_local.replace(tzinfo=zona, fold=0).utcoffset() != hora_local.replace(tzinfo=zona, fold=1).utcoffset()


def desfase(instante: datetime, zona: zoneinfo.ZoneInfo) -> timedelta:
    return instante.astimezone(zona).utcoffset()


def a_local(instante: datetime, zona: zoneinfo.ZoneInfo) -> datetime:
    return instante.astimezone(zona).replace(tzinfo=None)
