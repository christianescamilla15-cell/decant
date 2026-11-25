"""¿Cuánto volumen hace falta para que el CONTROL NEGATIVO no salga en 0 %? Se mide, no se adivina.

Control negativo = el legado contra sí mismo: la misma salida del legado, sobre los mismos datos, tomada dos veces.
Si sale idéntica siempre, una comparación posicional parece perfecta y el arnés de paridad no tiene listón.

Para cada volumen (operaciones por día) se recrea la base, se carga, y se corre varias veces el reporte del legado
(`sp_reporte_ordenes`, orden por fecha valor con cientos de empates por día) y la lista de la pantalla
(`sp_lista_operaciones`, TOP sin ORDER BY). El orden se mide en INVERSIONES contra la primera corrida, por llave
natural (`radiografia/orden.py`): pares con distinta fecha valor (contrato: deben dar 0) y pares EMPATADOS (libres:
ahí vive el piso). Se mide con MAXDOP 4 (los núcleos del runner de GitHub) y sin límite, y en «dos momentos» (tras
actualizar estadísticas). El % de posiciones distintas se deja sólo como contraste.

    python -m legado.medir_volumen --volumenes 25,50,100,250,400 --corridas 5
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date

from legado.__main__ import DATOS, esquema
from legado.conexion import RAIZ, conectar
from radiografia.orden import comparar

PERIODOS = (('mes', date(2023, 12, 1), date(2023, 12, 31)),
            ('trimestre', date(2023, 10, 1), date(2023, 12, 31)),
            ('año', date(2023, 1, 1), date(2023, 12, 31)))


def _reporte(cursor, desde: date, hasta: date) -> list[tuple]:
    cursor.execute('EXEC dbo.sp_reporte_ordenes @desde = %s, @hasta = %s', (desde, hasta))
    return [(fila[0], fila[11], fila[4]) for fila in cursor.fetchall()]     # (folio, concepto) + fecha_valor


def _lista(cursor, fecha: date) -> list[tuple]:
    cursor.execute('EXEC dbo.sp_lista_operaciones @fecha = %s', (fecha,))
    cursor.fetchall()
    cursor.nextset()
    return [(fila[0],) for fila in cursor.fetchall()]


def _medida(salida: str, maxdop: int, tomas: list[list[tuple]], natural, orden, otro_momento=None) -> dict:
    comparaciones = [comparar(tomas[0], t, natural, orden) for t in tomas[1:]]
    empatados = [c['pct_empatados_invertidos'] for c in comparaciones]
    momento = comparar(tomas[0], otro_momento, natural, orden) if otro_momento is not None else None
    return {'salida': salida, 'maxdop': maxdop, 'renglones': len(tomas[0]),
            'pares_empatados': comparaciones[0]['pares_empatados'],
            'inversiones_contrato_max': max(c['inversiones_contrato'] for c in comparaciones),
            'pct_empatados_invertidos_max': max(empatados),
            'pct_empatados_invertidos_prom': round(sum(empatados) / len(empatados), 2),
            'corridas_distintas': sum(1 for c in comparaciones if c['inversiones_empatados'] > 0),
            'pct_posiciones_distintas_max': max(c['pct_posiciones_distintas'] for c in comparaciones),
            'pct_empatados_invertidos_otro_momento': momento['pct_empatados_invertidos'] if momento else None}


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
                tomas = [_reporte(cursor, desde, hasta) for _ in range(corridas)]
                cursor.execute('UPDATE STATISTICS dbo.orden_pago WITH FULLSCAN; '
                               'UPDATE STATISTICS dbo.partida_solicitada WITH FULLSCAN; '
                               'DBCC FREEPROCCACHE WITH NO_INFOMSGS;')
                otro_momento = _reporte(cursor, desde, hasta)
                resultado['mediciones'].append(_medida(f'sp_reporte_ordenes ({nombre})', maxdop, tomas, [0, 1], [2],
                                                       otro_momento))
            # sin ORDER BY no hay contrato: todos los pares son libres
            tomas = [_lista(cursor, dia_pico) for _ in range(corridas)]
            resultado['mediciones'].append(_medida(f'sp_lista_operaciones ({dia_pico})', maxdop, tomas, [0], []))
        _maxdop(cursor, 0)
    return resultado


def tabla_markdown(resultados: list[dict]) -> str:
    lineas = ['| ops/día | operaciones | salida | MAXDOP | renglones | inversiones de contrato (máx) '
              '| % de pares empatados invertidos (máx / prom) | corridas distintas | % empatados invertidos en otro '
              'momento | % posiciones distintas (máx, sólo contraste) |',
              '|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in resultados:
        for m in r['mediciones']:
            momento = '—' if m['pct_empatados_invertidos_otro_momento'] is None else \
                m['pct_empatados_invertidos_otro_momento']
            lineas.append(f"| {r['operaciones_por_dia']} | {r['filas']['operacion']:,} | {m['salida']} | "
                          f"{m['maxdop'] or 'todos'} | {m['renglones']:,} | {m['inversiones_contrato_max']} | "
                          f"{m['pct_empatados_invertidos_max']} / {m['pct_empatados_invertidos_prom']} | "
                          f"{m['corridas_distintas']} | {momento} | {m['pct_posiciones_distintas_max']} |")
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
