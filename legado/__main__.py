"""Legado ficticio del Banco Ficticio del Norte.

    python -m legado esquema --recrear      # base, tablas, vista, trigger, procedimientos y job
    python -m legado cargar                 # genera 3 años (semilla fija) y los carga en bloque
    python -m legado pantalla               # pantalla de sólo lectura en http://127.0.0.1:8080/
    python -m legado respaldar              # .bak FECHADO de BFN_DIVISAS y msdb + manifiesto
    python -m legado bcp                    # mide el daño de `bcp -c` sobre las columnas Unicode
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from legado.conexion import BASE, RAIZ, SQL, conectar, ejecutar_script

DATOS = RAIZ / 'datos'


def esquema(recrear: bool) -> None:
    with conectar('master') as conexion:
        cursor = conexion.cursor()
        if recrear:
            cursor.execute(
                "IF DB_ID(N'BFN_DIVISAS') IS NOT NULL BEGIN "
                "ALTER DATABASE BFN_DIVISAS SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE BFN_DIVISAS; END")
        for script in sorted(SQL.glob('*.sql')):
            n = ejecutar_script(conexion, script)
            print(f'{script.name}: {n} lotes')


def cargar(operaciones_por_dia: int | None, semilla: int | None) -> None:
    from legado.generador import Config, generar
    from legado.generador.cargar import cargar as cargar_bloque

    opciones = {}
    if operaciones_por_dia:
        opciones['operaciones_por_dia'] = operaciones_por_dia
    if semilla is not None:
        opciones['semilla'] = semilla
    cfg = Config(**opciones)
    t0 = time.perf_counter()
    datos = generar(cfg)
    t1 = time.perf_counter()
    with conectar() as conexion:
        conteos = cargar_bloque(datos, conexion)
    t2 = time.perf_counter()
    DATOS.mkdir(exist_ok=True)
    generacion = {'semilla': cfg.semilla, 'operaciones_por_dia': cfg.operaciones_por_dia,
                  'inicio': cfg.inicio.isoformat(), 'fecha_respaldo': cfg.fecha_respaldo.isoformat(),
                  'conteos': conteos, 'pasos_delta': len(datos.pasos), 'huella': datos.huella(),
                  'huellas': datos.huellas()}
    (DATOS / 'generacion.json').write_text(json.dumps(generacion, indent=2) + '\n', encoding='utf-8')
    (DATOS / f'delta_{cfg.fecha_respaldo.isoformat()}.json').write_text(
        json.dumps({'fecha_negocio': cfg.fecha_respaldo.isoformat(), 'respaldo_utc': cfg.respaldo.isoformat(),
                    'congelamiento_utc': cfg.congelamiento.isoformat(), 'fin_utc': cfg.fin.isoformat(),
                    'pasos': datos.pasos}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'generado en {t1 - t0:.1f} s · cargado y verificado en {t2 - t1:.1f} s · huella {datos.huella()[:16]}')
    for tabla, n in conteos.items():
        print(f'  {tabla:20s} {n:>10,}')
    print(f'  delta del mismo día: {len(datos.pasos)} llamadas → {DATOS.name}/delta_{cfg.fecha_respaldo}.json')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m legado', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='orden', required=True)
    p = sub.add_parser('esquema', help=f'crea {BASE} y sus objetos')
    p.add_argument('--recrear', action='store_true', help='borra la base antes')
    p = sub.add_parser('cargar', help='genera y carga los datos históricos')
    p.add_argument('--operaciones-por-dia', type=int)
    p.add_argument('--semilla', type=int)
    p = sub.add_parser('pantalla', help='sirve la pantalla de sólo lectura')
    p.add_argument('--puerto', type=int, default=8080)
    p = sub.add_parser('respaldar', help='respaldo fechado + manifiesto')
    p.add_argument('--pantalla', default='http://127.0.0.1:8080/')
    p.add_argument('--salida', type=Path, default=Path('respaldos'))
    sub.add_parser('bcp', help='mide el daño de bcp -c')
    args = parser.parse_args(argv)

    if args.orden == 'esquema':
        esquema(args.recrear)
    elif args.orden == 'cargar':
        cargar(args.operaciones_por_dia, args.semilla)
    elif args.orden == 'pantalla':
        from legado.pantalla.app import servir
        servir(args.puerto)
    elif args.orden == 'respaldar':
        from legado.respaldo import respaldar
        m = respaldar(args.pantalla, args.salida)
        print(f"respaldo del {m['fecha_negocio']} · la pantalla publica {m['pantalla']['total_operaciones']:,} "
              f"operaciones · {m['ruta']}")
        for a in m['archivos']:
            print(f"  {a['nombre']}  {a['bytes']:,} bytes  sha256 {a['sha256'][:16]}…")
    elif args.orden == 'bcp':
        from legado.bcp import medir
        resultado = medir()
        DATOS.mkdir(exist_ok=True)
        (DATOS / 'bcp.json').write_text(json.dumps(resultado, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(resultado, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
