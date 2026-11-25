"""Los dos ejercicios con nombre, la paridad de reporte y los gemelos, con UN comando:

    python -m paridad --manifiesto respaldos/respaldo_2023-12-29.json

Restaura el respaldo en un contenedor limpio (que se quita siempre), extrae universo y oráculo, carga el TO-BE
(carga histórica y cuatro replays del universo) con su CLI, y escribe `paridad/informe/paridad.{md,json}`:

1. «Verificar la migración»: byte a byte, esquema después de cada carga y cuadre interno por lado.
2. «Medir el motor»: % de coincidencia por regla (replay hasta el corte medido), hipótesis, controles y «sólo marca».
3. Paridad de reporte: el reporte del TO-BE en sombra contra el que el legado publicó, con arbitraje.
4. Gemelos: la pantalla de detalle del legado contra el JSON de la API.

Necesita PostgreSQL (DECANT_PG_PASSWORD y DECANT_PG_PUERTO) y el TO-BE compilado en Release. Sale con 1 si algo no
cumple. El legado vivo (DECANT_SA_PASSWORD / DECANT_PUERTO, el que deja `./ciclo.sh`) audita el avance.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from paridad import binding, esquema, extraer, gemelos, informe, migracion, motor, reporte, tobe
from paridad.respaldo_limpio import restaurar

BASES = {
    'migracion': ('decant_migracion', 'carga histórica (universo + oráculo)'),
    'motor': ('decant_motor', 'replay del universo hasta el corte, banderas encendidas'),
    'marca_vencimiento': ('decant_marca_vencimiento', 'replay hasta el corte, vencimiento en «sólo marca»'),
    'marca_conciliacion': ('decant_marca_conciliacion', 'replay hasta el corte, conciliación en «sólo marca»'),
    'sombra': ('decant_sombra', 'replay de TODO el universo (TO-BE en sombra)'),
}


def _vivo():
    """El legado vivo (después del delta), si está arriba: audita el avance de producción."""
    try:
        from legado.conexion import conectar
        return conectar()
    except BaseException as error:              # sin legado vivo el avance queda sin auditar (y no se absuelve)
        print(f'  legado vivo no disponible: {error}', file=sys.stderr)
        return None


def correr(args) -> dict:
    tiempos: dict[str, float] = {}

    def paso(nombre: str, t0: float) -> None:
        tiempos[nombre] = round(time.perf_counter() - t0, 1)
        print(f'── {nombre}: {tiempos[nombre]} s', flush=True)

    for compilado in (tobe.CLI, gemelos.API):
        if not compilado.exists():
            raise SystemExit(f'Falta compilar el TO-BE en Release: dotnet build Decant.slnx -c Release ({compilado})')
    resultado: dict = {'generado': datetime.now().astimezone().isoformat(timespec='seconds')}
    t = time.perf_counter()
    with restaurar(args.manifiesto) as r:
        paso('restaurar el respaldo en un contenedor limpio', t)
        t = time.perf_counter()
        llave = tobe.llave_de_cargas(args.manifiesto)
        if args.reusar_cargas:                       # sólo para iterar en local: el CI siempre extrae y carga
            tobe.verificar_reuso(args.datos, llave)  # y sólo si las hizo este mismo código
            corte = json.loads((args.datos / 'corte.json').read_text(encoding='utf-8'))
            paquetes = {n: json.loads((args.datos / n / 'manifiesto.json').read_text(encoding='utf-8'))
                        for n in ('universo', 'oraculo')}
        else:
            paquetes = extraer.escribir_paquetes(r, args.interfaces, args.datos)
            (args.datos / tobe.LLAVE_DE_CARGAS).unlink(missing_ok=True)  # se reescribe al terminar las cargas
            corte = paquetes['corte']
        resultado['corte'] = corte
        resultado['paquetes'] = {n: {a: x['filas'] for a, x in paquetes[n]['tablas'].items()}
                                 for n in ('universo', 'oraculo')}
        paso('extraer universo y oráculo', t)

        universo, oraculo = str(args.datos / 'universo'), str(args.datos / 'oraculo')
        hasta = corte['instante_utc']
        cargas = {
            'migracion': ['migrar', '--universo', universo, '--oraculo', oraculo],
            'motor': ['reproducir', '--universo', universo, '--hasta', hasta],
            'marca_vencimiento': ['reproducir', '--universo', universo, '--hasta', hasta, '--sin-vencer'],
            'marca_conciliacion': ['reproducir', '--universo', universo, '--hasta', hasta, '--sin-conciliar'],
            'sombra': ['reproducir', '--universo', universo],
        }
        resultado['cargas'] = {}
        with r.conectar() as cl:
            esquema_legado = esquema.esquema_legado(cl.cursor())
        resultado['esquema'] = {}
        for nombre, argumentos in cargas.items():
            t = time.perf_counter()
            base = BASES[nombre][0]
            resumen = ('reutilizada (--reusar-cargas)' if args.reusar_cargas
                       else tobe.decant(argumentos[0], '--base', base, *argumentos[1:]))
            resultado['cargas'][nombre] = {'base': base, 'que': BASES[nombre][1], 'resumen': resumen}
            with tobe.conectar(base) as ct:          # esquema columna por columna DESPUÉS de cada carga
                esquema_tobe = esquema.esquema_tobe(ct.cursor())
            comparado = esquema.comparar(esquema_legado, esquema_tobe)
            comparado.pop('filas') if nombre != 'migracion' else None
            resultado['esquema'][nombre] = comparado
            if nombre == 'migracion':
                resultado['esquema']['control_negativo_t6'] = esquema.control_negativo_t6(esquema_legado,
                                                                                          esquema_tobe)
            paso(f'cargar {base} y comparar su esquema', t)
        if not args.reusar_cargas:
            tobe.guardar_llave(args.datos, llave)

        t = time.perf_counter()
        with r.conectar() as cl, tobe.conectar(BASES['migracion'][0]) as ct:
            cursor = cl.cursor()
            enlace = binding.binding(cursor)
            lado_cliente = enlace['Solicitado por el cliente']['tabla_legado']
            otra = next(x for x in binding.TABLAS_DE_PARTIDAS if x != lado_cliente)
            resultado['binding'] = enlace
            resultado['migracion'] = {
                'byte_a_byte': migracion.byte_a_byte(cursor, ct.cursor()),
                'cuadre_por_lado': {
                    'legado (lados según la pantalla)': migracion.cuadre_legado(cursor, lado_cliente),
                    'CONTROL: legado con los lados según el NOMBRE de la tabla': migracion.cuadre_legado(cursor, otra),
                },
            }
        for nombre in ('migracion', 'motor', 'sombra'):
            with tobe.conectar(BASES[nombre][0]) as ct:
                resultado['migracion']['cuadre_por_lado'][f'TO-BE {BASES[nombre][0]}'] = migracion.cuadre_tobe(
                    ct.cursor())
        paso('verificar la migración (byte a byte y cuadres)', t)

        t = time.perf_counter()
        corte_utc = datetime.fromisoformat(corte['instante_utc'])
        with r.conectar() as cl, tobe.conectar(BASES['motor'][0]) as ct:
            resultado['motor'] = motor.medir(cl.cursor(), ct.cursor(), args.datos / 'universo', corte_utc)
        resultado['motor']['solo_marca'] = []
        for base, regla in ((BASES['marca_vencimiento'][0], 'R10-vencimiento'),
                            (BASES['marca_conciliacion'][0], 'R07-conciliacion')):
            with r.conectar() as cl, tobe.conectar(base) as ct:
                resultado['motor']['solo_marca'].append(motor.solo_marca(cl.cursor(), ct.cursor(), regla))
        paso('medir el motor', t)

        t = time.perf_counter()
        publicada = next(s for s in r.manifiesto['salidas'] if s['nombre'] == 'reporte_del_mes')
        desde, hasta_reporte = publicada['parametros']
        ruta_tobe = args.datos / 'reporte_tobe.jsonl'
        tobe.decant('reporte-ordenes', '--base', BASES['sombra'][0], '--desde', desde, '--hasta', hasta_reporte,
                    '--salida', str(ruta_tobe.resolve()))
        with r.conectar() as cl:
            piso = reporte.piso(cl.cursor(), publicada, args.datos / 'oraculo' / 'publicadas')
        eventos = reporte.eventos_posteriores(args.datos / 'universo', corte_utc)
        vivo = _vivo()
        try:
            resultado['reporte'] = reporte.comparar(publicada, args.datos / 'oraculo' / 'publicadas', ruta_tobe,
                                                    piso, corte, vivo, eventos)
            # control negativo del comparador: cada mutante del reporte del TO-BE DEBE fallar
            resultado['reporte']['mutantes'] = reporte.mutantes(
                publicada, args.datos / 'oraculo' / 'publicadas', ruta_tobe, piso, corte, vivo, eventos,
                args.datos / 'mutantes')
        finally:
            if vivo is not None:
                vivo.close()
        resultado['reporte']['legado_vivo_disponible'] = vivo is not None
        paso('paridad de reporte', t)

        if not args.sin_gemelos:
            t = time.perf_counter()
            conexion = tobe.cadena_dotnet() + f";Database={BASES['migracion'][0]}"
            resultado['gemelos'] = gemelos.gemelos(r, args.puerto_pantalla, args.puerto_api, conexion)
            paso('gemelos', t)
    resultado['tiempos'] = tiempos
    resultado['trampas_a_ciegas'] = informe.trampas_a_ciegas(resultado)
    resultado['cumple'] = informe.cumple(resultado)
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m paridad', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifiesto', type=Path, required=True)
    parser.add_argument('--interfaces', type=Path, default=Path('legado/datos/interfaces'))
    parser.add_argument('--datos', type=Path, help='carpeta de universo y oráculo (por omisión paridad/datos/<fecha>)')
    parser.add_argument('--salida', type=Path, default=Path('paridad/informe'))
    parser.add_argument('--sin-gemelos', action='store_true')
    parser.add_argument('--reusar-cargas', action='store_true',
                        help='no extrae ni carga: usa lo que ya está en paridad/datos y en PostgreSQL (sólo en local)')
    parser.add_argument('--puerto-pantalla', type=int, default=18096)
    parser.add_argument('--puerto-api', type=int, default=18097)
    args = parser.parse_args(argv)
    if args.datos is None:
        args.datos = Path('paridad/datos') / args.manifiesto.stem.replace('respaldo_', '')
    resultado = correr(args)
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / 'paridad.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=1, default=str) + '\n',
                                              encoding='utf-8')
    (args.salida / 'paridad.md').write_text(informe.markdown(resultado), encoding='utf-8')
    print(informe.resumen(resultado))
    return 0 if resultado['cumple']['todo'] else 1


if __name__ == '__main__':
    sys.exit(main())
