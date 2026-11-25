"""Catálogos del banco ficticio. Todo es inventado salvo los estándares públicos (ISO 4217, ISO 20022, CLABE)."""
from __future__ import annotations

from datetime import date

# ISO 4217: código, numérico, nombre, decimales (unidades menores), valor en USD al inicio y al final del periodo.
MONEDAS = (
    ('MXN', '484', 'Peso mexicano', 2, None, None),
    ('USD', '840', 'Dólar estadounidense', 2, 1.0, 1.0),
    ('EUR', '978', 'Euro', 2, 1.21, 1.10),
    ('GBP', '826', 'Libra esterlina', 2, 1.37, 1.27),
    ('CAD', '124', 'Dólar canadiense', 2, 0.79, 0.75),
    ('JPY', '392', 'Yen japonés', 0, 0.0097, 0.0070),
    ('CHF', '756', 'Franco suizo', 2, 1.13, 1.18),
    ('CNY', '156', 'Yuan renminbi', 2, 0.154, 0.141),
    ('KWD', '414', 'Dinar kuwaití', 3, 3.31, 3.25),
    ('HRK', '191', 'Kuna croata', 2, 0.162, 0.133),
    ('SLL', '694', 'Leone (anterior)', 2, None, None),
)
# Croacia adoptó el euro el 1-ene-2023: la kuna deja de operarse y el catálogo la apaga a mediados de mes.
FIN_HRK = date(2023, 1, 1)
BAJA_HRK = date(2023, 1, 15)

# Peso por dólar: puntos ancla (interpolación lineal + ruido).
USD_MXN = ((date(2021, 1, 1), 19.90), (date(2022, 3, 1), 20.60), (date(2022, 12, 31), 19.45),
           (date(2023, 7, 31), 16.75), (date(2023, 12, 31), 17.00))

PESO_MONEDA = (('USD', 70), ('EUR', 12), ('GBP', 4), ('CAD', 4), ('JPY', 3), ('CHF', 2), ('CNY', 2),
               ('KWD', 1), ('HRK', 2))

NOMBRES = ('José', 'María', 'Juan', 'Ana', 'Luis', 'Sofía', 'Jesús', 'Lucía', 'Martín', 'Mónica', 'Raúl', 'Inés',
           'Ángel', 'Begoña', 'Héctor', 'Verónica', 'Andrés', 'Valentina', 'Ramón', 'Fernanda', 'Óscar', 'Ximena',
           'Iñaki', 'Noé', 'Sebastián', 'Mariana', 'Joaquín', 'Rocío', 'Tomás', 'Elena', 'Pedro', 'Carmen')
APELLIDOS = ('Hernández', 'García', 'Martínez', 'López', 'González', 'Pérez', 'Rodríguez', 'Sánchez', 'Ramírez',
             'Cruz', 'Flores', 'Gómez', 'Díaz', 'Reyes', 'Morales', 'Jiménez', 'Ruiz', 'Gutiérrez', 'Ortiz',
             'Chávez', 'Núñez', 'Muñoz', 'Peña', 'Ibáñez', 'Vázquez', 'Castañeda', 'Domínguez', 'Treviño', 'Zúñiga',
             'Ordóñez', 'Salas', 'Rivera', 'Mendoza', 'Aguilar', 'Vega', 'Soto', 'Campos', 'Luna')
EMPRESAS = ('Importadora del Bajío, S.A. de C.V.', 'Comercializadora Peñasco, S.A. de C.V.',
            'Maquinados Ñandú, S. de R.L.', 'Agroexportadora del Pacífico, S.P.R. de R.L.',
            'Textiles Acámbaro, S.A.', 'Café de Altura Tacaná, S.C.', 'Distribuidora Médica del Centro, S.A. de C.V.',
            'Grupo Logístico Tláloc, S.A. de C.V.', 'Artesanías del Lago, S.C.',
            'Refacciones Industriales del Norte, S.A.', 'Muebles Cañada Honda, S.A. de C.V.',
            'Vinícola Valle Ámbar, S.P.R.')

# Beneficiarios en el extranjero (inventados). Algunos traen letras que NO caben en latin-1 / cp1252.
BENEFICIARIOS = {
    'USD': ('Pacific Harbor Imports Inc.', 'Café Olé Trading LLC', 'Great Plains Seed Co.',
            'Bayside Medical Supply Corp.', 'Ozark Hardwood Mills LLC'),
    'EUR': ('Nordlicht Präzision GmbH', 'Atelier Lumière SARL', 'Dvořák Nástroje s.r.o.',
            'Łęczyca Tkaniny Sp. z o.o.', 'Ελληνική Ναυτιλιακή Α.Ε.', 'İzmir Tekstil A.Ş.'),
    'GBP': ('Thames Valley Textiles plc', 'Moorland Bearings Ltd.'),
    'CAD': ('Maple Ridge Lumber Ltd.', 'Fleuve Saint-Laurent Équipement Inc.'),
    'JPY': ('Sakura Seimitsu K.K.', 'Kitakami Denki K.K.'),
    'CHF': ('Zürichsee Uhren AG', 'Genève Horlogerie SA'),
    'CNY': ('Hengtong Trading Co. Ltd.', 'Lianhe Precision Parts Co.'),
    'KWD': ('Gulf Pearl Trading W.L.L.',),
    'HRK': ('Jadran Brodogradnja d.o.o.', 'Øresund Maskin d.o.o.'),
}
CORRESPONSAL = {'USD': 'FICTUS33XXX', 'EUR': 'FICTDEFFXXX', 'GBP': 'FICTGB2LXXX', 'CAD': 'FICTCATTXXX',
                'JPY': 'FICTJPJTXXX', 'CHF': 'FICTCHZZXXX', 'CNY': 'FICTCNSHXXX', 'KWD': 'FICTKWKWXXX',
                'HRK': 'FICTHR2XXXX'}
INTERMEDIARIOS = ('FICTUS3NXXX', 'FICTUS6SXXX', 'FICTDEMMXXX', 'FICTGB22XXX')

# ISO 20022 ExternalPurpose1Code (pacs.008 Purp/Cd).
PROPOSITOS = (('SUPP', 40), ('GDDS', 25), ('SCVE', 12), ('TRAD', 8), ('INTC', 5), ('EDUC', 4), ('MDCS', 3),
              ('SALA', 3))

SUCURSALES = tuple(f'{n:04d}' for n in range(1, 41))
SUCURSAL_EN_LINEA = '0999'
BANCO_CLABE = '987'      # clave de banco inventada
PLAZAS = ('180', '320', '580', '650', '730')


def digito_clabe(diecisiete: str) -> str:
    """Dígito de control de la CLABE: pesos 3-7-1, suma de (dígito×peso mod 10), complemento a 10."""
    pesos = (3, 7, 1) * 6
    suma = sum((int(d) * p) % 10 for d, p in zip(diecisiete, pesos))
    return str((10 - suma % 10) % 10)
