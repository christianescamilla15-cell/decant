"""Paquetes de UNIVERSO y de ORÁCULO a partir del respaldo fechado, restaurado en un contenedor limpio.

    python -m paridad.extraer --manifiesto respaldos/respaldo_2023-12-29.json \\
        --interfaces legado/datos/interfaces --salida paridad/datos/2023-12-29

Deja `universo/` (entradas + archivos de interfaz + horario del job), `oraculo/` (resultados + salidas publicadas) y
`corte.json` (el corte MEDIDO de la fuente). Cada carpeta lleva su manifiesto con filas y sha256 por archivo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paridad import corte, oraculo, universo
from paridad.respaldo_limpio import BASE, MSDB, Restaurado, restaurar


def escribir_paquetes(r: Restaurado, interfaces: Path, salida: Path) -> dict:
    with r.conectar() as conexion:
        cursor = conexion.cursor()
        medido = corte.medir(cursor)
        m_universo = universo.extraer(cursor, interfaces, salida / 'universo', BASE, MSDB)
        m_oraculo = oraculo.extraer(cursor, r.manifiesto, r.carpeta, salida / 'oraculo')
    origen = {'respaldo': r.manifiesto['base'], 'fecha_negocio': r.manifiesto['fecha_negocio'],
              'archivos': r.manifiesto['archivos']}
    for nombre, contenido in (('universo', m_universo), ('oraculo', m_oraculo)):
        (salida / nombre / 'manifiesto.json').write_text(
            json.dumps({'origen': origen, **contenido}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    (salida / 'corte.json').write_text(json.dumps(medido, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return {'corte': medido, 'universo': m_universo, 'oraculo': m_oraculo}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m paridad.extraer', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifiesto', type=Path, required=True)
    parser.add_argument('--interfaces', type=Path, default=Path('legado/datos/interfaces'))
    parser.add_argument('--salida', type=Path, required=True)
    args = parser.parse_args(argv)
    with restaurar(args.manifiesto) as r:
        resumen = escribir_paquetes(r, args.interfaces, args.salida)
    for nombre in ('universo', 'oraculo'):
        tablas = resumen[nombre]['tablas']
        print(f'{nombre}: ' + ' · '.join(f"{a} {t['filas']:,}" for a, t in tablas.items()))
    print(f"corte medido: {resumen['corte']['instante_local']} (local) = {resumen['corte']['instante_utc']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
