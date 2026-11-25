"""Lectura de los archivos de interfaz del legado con sus llaves REALES.

Buzón del corresponsal (estilo MT910 simplificado): la llave del documento es la UETR del bloque 3 (`{121:…}`) y,
como respaldo, nuestra referencia en `:21:`. El `:20:` es la referencia PROPIA del corresponsal: es el primer campo
«parecido» y cruzar por él no encuentra nada. `:13D:` trae la hora de Nueva York con su desfase UTC, así que aquí
sí se puede saber el instante exacto (el legado lo guardó sin zona).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

_UETR = re.compile(r'\{121:([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\}')
_CAMPO = re.compile(r'^:(\d{2}[A-Z]?):(.*)$', re.MULTILINE)
_MONTO = re.compile(r'^([A-Z]{3})(\d+,\d*)$')


@dataclass(frozen=True)
class Confirmacion:
    uetr: str                 # llave del documento (bloque 3)
    referencia: str           # nuestra referencia MT103 (:21:)
    trn_corresponsal: str     # :20: del corresponsal; NO es llave de cruce
    instante_utc: datetime
    hora_local_ny: datetime   # lo que guardó el legado
    fecha_valor: date
    moneda: str
    abono: Decimal
    comision: Decimal


def _monto(texto: str) -> tuple[str, Decimal]:
    m = _MONTO.match(texto.strip())
    if not m:
        raise ValueError(f'monto SWIFT inválido: {texto!r}')
    return m.group(1), Decimal(m.group(2).replace(',', '.').rstrip('.') or '0')


def leer_confirmacion(mensaje: str) -> Confirmacion:
    uetr = _UETR.search(mensaje)
    if not uetr:
        raise ValueError('mensaje sin UETR en el bloque 3')
    campos = {etiqueta: valor.strip() for etiqueta, valor in _CAMPO.findall(mensaje)}
    momento = campos['13D']                     # AAMMDDHHMM±HHMM
    local = datetime.strptime(momento[:10], '%y%m%d%H%M')
    signo = -1 if momento[10] == '-' else 1
    desfase = timedelta(hours=int(momento[11:13]), minutes=int(momento[13:15])) * signo
    valor = campos['32A']
    moneda, abono = _monto(valor[6:])
    comision = _monto(campos['71F'])[1] if '71F' in campos else Decimal(0)
    return Confirmacion(
        uetr=uetr.group(1), referencia=campos['21'], trn_corresponsal=campos['20'],
        instante_utc=(local - desfase).replace(tzinfo=timezone.utc), hora_local_ny=local,
        fecha_valor=datetime.strptime(valor[:6], '%y%m%d').date(), moneda=moneda, abono=abono, comision=comision)


def leer_buzon(texto: str) -> list[Confirmacion]:
    return [leer_confirmacion(m) for m in texto.split('\n$') if m.strip()]


def leer_sucursales(texto: str) -> list[dict]:
    """Archivo de sucursales (UTF-8, `;`). La llave natural es `referencia`."""
    return list(csv.DictReader(io.StringIO(texto), delimiter=';'))
