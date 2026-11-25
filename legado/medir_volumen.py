"""¿Cuánto volumen hace falta para que el CONTROL NEGATIVO no salga en 0 %? Se mide, no se adivina.

Control negativo = el legado contra sí mismo: la misma salida del legado, sobre los mismos datos, tomada dos veces.
Si sale idéntica siempre, una comparación posicional parece perfecta y el arnés de paridad no tiene listón.

Para cada volumen (operaciones por día) se recrea la base, se carga, y se corre varias veces el reporte del legado
(`sp_reporte_ordenes`, orden por fecha valor con cientos de empates por día) y la lista de la pantalla
(`sp_lista_operaciones`, TOP sin ORDER BY). Se mide el % de posiciones que cambian contra la primera corrida, con
MAXDOP 4 (los núcleos del runner de GitHub) y sin límite, y en «dos momentos» (tras actualizar estadísticas).

    python -m legado.medir_volumen --volumenes 25,50,100,250,400 --corridas 5
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date

from legado.__main__ import DATOS, esquema
from legado.conexion import RAIZ, conectar

PERIODOS = (('mes', date(2023, 12, 1), date(2023, 12, 31)),
            ('trimestre', date(2023, 10, 1), date(2023, 12, 31)),
            ('año', date(2023, 1, 1), date(2023, 12, 31)))


def _reporte(cursor, desde: date, hasta: date) -> list[tuple]:
    cursor.execute('EXEC dbo.sp_reporte_ordenes @desde = %s, @hasta = %s', (desde, hasta))
    return [(fila[0], fila[11]) for fila in cursor.fetchall()]          # (folio, concepto): llave del renglón


def _lista(cursor, fecha: date) -> list[int]:
    cursor.execute('EXEC dbo.sp_lista_operaciones @fecha = %s', (fecha,))
    cursor.fetchall()
    cursor.nextset()
    return [fila[0] for fila in cursor.fetchall()]


def _distintas(a: list, b: list) -> float:
    if not a:
        return 0.0
    return 100.0 * sum(1 for x, y in zip(a, b) if x != y) / len(a)


def _maxdop(cursor, valor: int) -> None:
    cursor.execute("EXEC sp_configure 'show advanced options', 1; RECONFIGURE;")
    cursor.execute("EXEC sp_configure 'max degree of parallelism', %s; RECONFIGURE;", (valor,))
    cursor.execute('DBCC FREEPROCCACHE WITH NO_INFOMSGS;')


def medir_volumen(volumen: int, corridas: int) -> dict:
    from legado.generador import Config, generar
    from legado.generador.cargar import cargar

    esquema(recrear=True)
    datos = generar(Config(operaciones_por_dia=volumen))
    with conectar() as conexion:
        cargar(datos, conexion)
        cursor = conexion.cursor()
        cursor.execute('SELECT TOP 1 CAST(fecha_operacion AS date) FROM dbo.operacion '
                       'GROUP BY CAST(fecha_operacion AS date) ORDER BY COUNT(*) DESC, 1')
        dia_pico = cursor.fetchone()[0]
        resultado = {'operaciones_por_dia': volumen, 'filas': datos.conteos(), 'mediciones': []}
        for maxdop in (4, 0):
            _maxdop(cursor, maxdop)
            for nombre, desde, hasta in PERIODOS:
                t0 = time.perf_counter()
                salidas = [_reporte(cursor, desde, hasta) for _ in range(corridas)]
                segundos = (time.perf_counter() - t0) / corridas
                cursor.execute('UPDATE STATISTICS dbo.orden_pago WITH FULLSCAN; '
                               'UPDATE STATISTICS dbo.partida_solicitada WITH FULLSCAN; '
                               'DBCC FREEPROCCACHE WITH NO_INFOMSGS;')
                otro_momento = _reporte(cursor, desde, hasta)
                cambios = [_distintas(salidas[0], s) for s in salidas[1:]]
                resultado['mediciones'].append({
                    'salida': f'sp_reporte_ordenes ({nombre})', 'maxdop': maxdop, 'renglones': len(salidas[0]),
                    'pct_posiciones_distintas_max': round(max(cambios), 1),
                    'pct_posiciones_distintas_prom': round(sum(cambios) / len(cambios), 1),
                    'corridas_distintas': sum(1 for c in cambios if c > 0),
                    'pct_dos_momentos': round(_distintas(salidas[0], otro_momento), 1),
                    'segundos_por_corrida': round(segundos, 2)})
            listas = [_lista(cursor, dia_pico) for _ in range(corridas)]
            cambios = [_distintas(listas[0], s) for s in listas[1:]]
            resultado['mediciones'].append({
                'salida': f'sp_lista_operaciones ({dia_pico})', 'maxdop': maxdop, 'renglones': len(listas[0]),
                'pct_posiciones_distintas_max': round(max(cambios), 1),
                'pct_posiciones_distintas_prom': round(sum(cambios) / len(cambios), 1),
                'corridas_distintas': sum(1 for c in cambios if c > 0), 'pct_dos_momentos': None,
                'segundos_por_corrida': None})
        _maxdop(cursor, 0)
    return resultado


def tabla_markdown(resultados: list[dict]) -> str:
    lineas = ['| ops/día | operaciones | salida | MAXDOP | renglones | % posiciones que cambian (máx / prom) '
              '| corridas distintas | % en otro momento | s/corrida |',
              '|---:|---:|---|---:|---:|---:|---:|---:|---:|']
    for r in resultados:
        for m in r['mediciones']:
            momento = '—' if m['pct_dos_momentos'] is None else f"{m['pct_dos_momentos']}"
            segundos = '—' if m['segundos_por_corrida'] is None else f"{m['segundos_por_corrida']}"
            lineas.append(f"| {r['operaciones_por_dia']} | {r['filas']['operacion']:,} | {m['salida']} | "
                          f"{m['maxdop'] or 'todos'} | {m['renglones']:,} | {m['pct_posiciones_distintas_max']} / "
                          f"{m['pct_posiciones_distintas_prom']} | {m['corridas_distintas']} | {momento} | "
                          f"{segundos} |")
    return '\n'.join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--volumenes', default='25,50,100,250,400')
    parser.add_argument('--corridas', type=int, default=5)
    args = parser.parse_args()
    resultados = []
    for volumen in (int(v) for v in args.volumenes.split(',')):
        t0 = time.perf_counter()
        resultados.append(medir_volumen(volumen, args.corridas))
        print(f'volumen {volumen}: {time.perf_counter() - t0:.0f} s', flush=True)
    DATOS.mkdir(exist_ok=True)
    (DATOS / 'volumen.json').write_text(json.dumps(resultados, indent=2, default=str) + '\n', encoding='utf-8')
    texto = tabla_markdown(resultados)
    (RAIZ / 'datos' / 'volumen.md').write_text(texto + '\n', encoding='utf-8')
    print(texto)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
