"""Datos del generador compartidos por las pruebas (se generan una sola vez por sesión)."""
from __future__ import annotations

from datetime import date

import pytest

from legado.generador import Config, generar

# Periodo corto que cruza el cambio de horario de Nueva York (14-mar-2021) y el de México (4-abr-2021).
CHICO = Config(inicio=date(2021, 3, 1), fecha_respaldo=date(2021, 4, 16), operaciones_por_dia=60)


@pytest.fixture(scope='session')
def datos():
    """Los tres años completos, con la configuración por omisión (la misma que carga el CI)."""
    return generar()


@pytest.fixture(scope='session')
def datos_chicos():
    return generar(CHICO)
