"""Generador determinista del legado ficticio (semilla fija → mismos datos, mismo hash)."""
from .simulacion import COLUMNAS, TABLAS, Config, Datos, generar

__all__ = ['COLUMNAS', 'TABLAS', 'Config', 'Datos', 'generar']
