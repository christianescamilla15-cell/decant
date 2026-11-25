"""Radiografía de un respaldo de SQL Server, restaurado en un contenedor limpio.

    # el legado: lee el manifiesto que deja `python -m legado respaldar` (archivos, sha256 y cifra de la pantalla)
    python -m radiografia --manifiesto respaldos/respaldo_2023-12-29.json --salida radiografia/informe

    # control con una base pública de muestra de Microsoft
    python -m radiografia --bak muestras/WideWorldImporters-Full.bak --base WideWorldImporters \\
        --salida radiografia/control/wideworldimporters

Sale con 1 si no se cumple el criterio de salida (el COUNT de la tabla principal ≠ la cifra de la pantalla).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from radiografia import datos, informe, inventario, patrones, sqlserver


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def radiografiar(archivos: list[dict], base: str, manifiesto: dict | None, conservar: bool = False) -> dict:
    tiempos: dict[str, float] = {}
    t0 = time.perf_counter()
    servidor = sqlserver.arrancar_limpio()
    tiempos['arranque_contenedor'] = round(time.perf_counter() - t0, 1)
    try:
        restauracion, base_msdb = [], None
        t = time.perf_counter()
        for a in archivos:
            ruta = Path(a['ruta'])
            sha = _sha256(ruta)
            esperado = a.get('sha256')
            if esperado and sha != esperado:
                raise SystemExit(f'{ruta.name}: el sha256 no coincide con el manifiesto; no se restaura')
            disco = servidor.copiar(str(ruta))
            verificacion = servidor.verificar(disco)
            como = 'legado_msdb' if a['base'].lower() == 'msdb' else a['base']
            segundos = servidor.restaurar(disco, como)
            if como == 'legado_msdb':
                base_msdb = como
            restauracion.append({'base': a['base'], 'restaurada_como': como, 'archivo': ruta.name, 'sha256': sha,
                                 'sha256_ok': (sha == esperado) if esperado else None,
                                 'verificacion': verificacion, 'segundos': round(segundos, 1)})
        tiempos['restauracion'] = round(time.perf_counter() - t, 1)

        with servidor.conectar(base) as conexion:
            cursor = conexion.cursor()
            t = time.perf_counter()
            tablas = inventario.tablas(cursor)
            filas = {f"{x['esquema']}.{x['tabla']}".lower(): x['filas'] for x in tablas}
            columnas = inventario.columnas(cursor, filas)
            fks = inventario.llaves_foraneas(cursor)
            modulos = inventario.modulos(cursor)
            triggers = inventario.triggers(cursor)
            jobs, pasos = inventario.jobs(cursor, base_msdb, base)
            corte = inventario.corte(cursor, columnas)
            tiempos['inventario'] = round(time.perf_counter() - t, 1)

            t = time.perf_counter()
            padres_de: dict[str, set[str]] = {}
            for fk in fks:
                padres_de.setdefault(fk['hija'], set()).add(fk['padre'])
            codigo = modulos + pasos
            hallazgos = patrones.analizar_codigo(codigo, padres_de)
            por_tabla: dict[str, list[str]] = {}
            for c in columnas:
                por_tabla.setdefault(f"{c['esquema']}.{c['tabla']}".lower(), []).append(c['columna'])
            hallazgos += patrones.columnas_sin_lectura(codigo, por_tabla)
            tiempos['patrones_codigo'] = round(time.perf_counter() - t, 1)

            t = time.perf_counter()
            columnas_por_tabla: dict[str, list[dict]] = {}
            for c in columnas:
                columnas_por_tabla.setdefault(f"{c['esquema']}.{c['tabla']}".lower(), []).append(c)
            hallazgos += datos.centinelas(cursor, columnas)
            hallazgos += datos.mojibake(cursor, columnas)
            historicas = frozenset(f"{x['esquema']}.{x['tabla']}".lower() for x in tablas
                                   if x['temporal'] == 'HISTORY_TABLE')
            hallazgos += datos.llaves_duplicadas(cursor, columnas, columnas_por_tabla, historicas)
            tiempos['patrones_datos'] = round(time.perf_counter() - t, 1)
    finally:
        if not conservar:
            servidor.cerrar()

    principal = (manifiesto or {}).get('tabla_principal')
    criterio = {'aplica': False}
    if manifiesto and principal:
        n = filas.get(principal.lower())
        cifra = manifiesto['pantalla']['total_operaciones']
        criterio = {'aplica': True, 'tabla': principal, 'filas': n, 'pantalla': cifra, 'cumple': n == cifra}
    corte_principal = next((x for x in corte if principal and x['tabla'] == principal.lower()), None)
    return {
        'base': base,
        'generado_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'respaldo': {k: v for k, v in (manifiesto or {}).items() if k != 'archivos'},
        'restauracion': restauracion,
        'msdb': base_msdb,
        'criterio_salida': criterio,
        'corte': {'tabla_principal': principal, 'principal': corte_principal, 'tablas': corte},
        'inventario': {
            'tablas': tablas, 'columnas': len(columnas), 'llaves_foraneas': fks,
            'modulos': [{'nombre': m.nombre, 'tipo': m.tipo, 'lineas': m.texto.count('\n') + 1} for m in codigo],
            'triggers': triggers, 'jobs': jobs},
        'hallazgos': hallazgos,
        'resumen': _resumen(hallazgos),
        'tiempos': tiempos,
    }


def _resumen(hallazgos: list[dict]) -> dict[str, int]:
    resumen: dict[str, int] = {}
    for h in hallazgos:
        resumen[h['categoria']] = resumen.get(h['categoria'], 0) + 1
    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m radiografia', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    origen = parser.add_mutually_exclusive_group(required=True)
    origen.add_argument('--manifiesto', type=Path, help='manifiesto JSON del respaldo fechado')
    origen.add_argument('--bak', type=Path, help='un .bak suelto (base de muestra)')
    parser.add_argument('--base', help='nombre con el que se restaura el .bak suelto')
    parser.add_argument('--salida', type=Path, default=Path('radiografia/informe'))
    parser.add_argument('--conservar', action='store_true', help='no borrar el contenedor al terminar')
    args = parser.parse_args(argv)

    if args.manifiesto:
        manifiesto = json.loads(args.manifiesto.read_text(encoding='utf-8'))
        carpeta = args.manifiesto.parent
        archivos = [{'base': a['base'], 'ruta': carpeta / a['nombre'], 'sha256': a['sha256']}
                    for a in manifiesto['archivos']]
        base = manifiesto['base']
    else:
        if not args.base:
            parser.error('--bak necesita --base')
        manifiesto, base = None, args.base
        archivos = [{'base': args.base, 'ruta': args.bak}]
    t0 = time.perf_counter()
    resultado = radiografiar(archivos, base, manifiesto, args.conservar)
    resultado['tiempos']['total'] = round(time.perf_counter() - t0, 1)
    ruta_json, ruta_md = informe.escribir(resultado, args.salida)
    c = resultado['criterio_salida']
    print(f'radiografía de {base}: {len(resultado["hallazgos"])} hallazgos · {ruta_md}')
    print('  ' + ' · '.join(f'{k} {v}' for k, v in sorted(resultado['resumen'].items())))
    if c['aplica']:
        print(f"  criterio de salida: COUNT({c['tabla']}) = {c['filas']:,} · pantalla = {c['pantalla']:,} → "
              f"{'CUMPLE' if c['cumple'] else 'NO CUMPLE'}")
        return 0 if c['cumple'] else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
