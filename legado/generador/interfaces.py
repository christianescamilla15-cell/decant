"""Archivos de interfaz que recibe el legado: son parte del UNIVERSO (entradas), no del oráculo.

- **Buzón del corresponsal** (`corresponsal/AAAAMMDD.fin`): una confirmación de abono por orden liquidada, estilo
  MT910 simplificado (no validado contra el estándar), mensajes separados por `$` como en un archivo RJE. Trae TODAS
  las confirmaciones, también las que el legado descartó en silencio (D3) porque llegaron después del vencimiento.
  Llaves reales: la UETR del bloque 3 (`{121:…}`) y nuestra referencia en `:21:`. El `:20:` es la referencia
  PROPIA del corresponsal: es el primer campo «parecido» y no sirve para cruzar.
  `:13D:` lleva la hora de Nueva York CON su desfase UTC; el legado lo tira y guarda sólo la hora local.
- **Archivo de sucursales** (`sucursales/AAAAMMDD.csv`, UTF-8, separador `;`): las operaciones del canal ARCHIVO tal
  como las mandó cada sucursal. El nombre del cliente viene sano: el legado lo leyó como latin-1 (T7). La
  `referencia` de la sucursal es la llave natural de la operación y el legado no la guarda.
  Un reenvío tardío llega como `sucursales/AAAAMMDD_SSSS_reenvio.csv`.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from .zonas import NUEVA_YORK

BIC_PROPIO = 'FICTMXMMXXX'
COLUMNAS_SUCURSAL = ('referencia', 'sucursal', 'fecha_hora', 'cliente', 'cuenta_clabe', 'tipo', 'moneda', 'monto',
                     'tipo_cambio_referencia', 'estatus')


def _monto_swift(valor: Decimal, moneda: str) -> str:
    texto = f'{valor:.0f},' if moneda == 'JPY' else f'{valor:.2f}'.replace('.', ',')
    return texto


def mensaje_corresponsal(d, cuenta_nostro: str) -> str:
    """Confirmación de abono del corresponsal para un documento (estilo MT910 simplificado)."""
    llegada = d.t_liquidacion.astimezone(NUEVA_YORK)
    desfase = llegada.strftime('%z')                       # -0500 en invierno, -0400 en verano
    lineas = [
        f'{{1:F01{BIC_PROPIO}0000000000}}{{2:O910{llegada:%H%M%y%m%d}{d.bic}X0000000000{llegada:%y%m%d%H%M}N}}'
        f'{{3:{{121:{d.uetr}}}}}{{4:',
        f':20:{d.ref_corresponsal}',
        f':21:{d.referencia}',
        f':25:{cuenta_nostro}',
        f':13D:{llegada:%y%m%d%H%M}{desfase}',
        f':32A:{d.fecha_valor:%y%m%d}{d.moneda}{_monto_swift(d.abono, d.moneda)}',
        f':52A:{d.bic}',
    ]
    if d.comision > 0:
        lineas.append(f':71F:{d.moneda}{_monto_swift(d.comision, d.moneda)}')
    lineas.append('-}')
    return '\n'.join(lineas)


def buzon_corresponsal(docs, fin: datetime) -> dict[str, str]:
    por_dia: dict[str, list] = defaultdict(list)
    for d in docs:
        if d.t_liquidacion is None or d.t_liquidacion >= fin:
            continue
        dia = d.t_liquidacion.astimezone(NUEVA_YORK).date()
        por_dia[f'corresponsal/{dia:%Y%m%d}.fin'].append(d)
    archivos = {}
    for ruta, lista in sorted(por_dia.items()):
        lista.sort(key=lambda x: (x.t_liquidacion, x.seq))
        archivos[ruta] = '\n$'.join(mensaje_corresponsal(d, f'BFN{d.moneda}NOSTRO01') for d in lista) + '\n'
    return archivos


def archivo_sucursales(ops, fin: datetime) -> dict[str, str]:
    por_archivo: dict[str, list] = defaultdict(list)
    for op in ops:
        if op.canal != 'ARCHIVO' or op.insercion >= fin:
            continue
        dia = op.fecha_local.date()
        if op.reenvio:
            ruta = f'sucursales/{dia:%Y%m%d}_{op.sucursal}_reenvio.csv'
        else:
            ruta = f'sucursales/{dia:%Y%m%d}.csv'
        por_archivo[ruta].append(op)
    archivos = {}
    for ruta, lista in sorted(por_archivo.items()):
        lista.sort(key=lambda o: o.orden_archivo)
        renglones = [';'.join(COLUMNAS_SUCURSAL)]
        consecutivo: dict[str, int] = defaultdict(int)
        for op in lista:
            consecutivo[op.sucursal] += 1
            op.ref_sucursal = f'S{op.sucursal}-{op.fecha_local:%Y%m%d}-{consecutivo[op.sucursal]:04d}'
            renglones.append(';'.join((
                op.ref_sucursal, op.sucursal, op.fecha_local.isoformat(timespec='minutes'), op.cliente_original,
                op.clabe, op.tipo, op.moneda, str(op.monto), str(op.tc_ref), op.estatus)))
        archivos[ruta] = '\n'.join(renglones) + '\n'
    return archivos
