"""Veredicto del corte por dos caminos y de las cifras de control, SIN base (S3 paso 2, job `corte` del CI):

    python -m corte.veredicto corte/medido-ci --resumen "$GITHUB_STEP_SUMMARY"
    python -m corte.veredicto corte/medido-ci --artefacto huellas-por-documento.csv=sha256:…   # ya publicados
    python -m corte.veredicto corte/medido-ci --versionar [--artefactos artefactos.json]       # a corte/cifras/

Re-verifica lo que dejó `python -m corte.medir` en el job `legado`, sin creerle:
- el sha256 del CSV de huellas es el que declaran las cifras;
- recuenta desde el CSV, documento por documento, cada grupo tipo + estado + mes y cada tipo, por destino: documentos y
  huella deben ser los de las cifras, y cargado + no viaja = origen;
- las tablas con identidad del inventario DEL CÓDIGO de hoy tienen camino por sellos, todos los caminos coinciden
  (diferencia de conjuntos vacía) y el control negativo por fecha_operacion falló nombrando las altas fechadas hacia
  atrás;
- 0 duplicados por documento, la conciliación por llave sin duplicados (y por id duplicando los re-registros del día)
  y cada control negativo de las cifras detectado;
- las cifras y el CSV son los VERSIONADOS en `corte/cifras/huella.json`: las dos salen idénticas si el legado y el
  código no cambian, así que una diferencia es un cambio que alguien tiene que versionar a propósito.

Con `--artefacto nombre=digest` comprueba que el digest que GitHub calculó al publicar cada artefacto (subido sin
comprimir, `archive: false`) es el sha256 del archivo, y lo deja en el resumen. Con `--versionar` copia las cifras y el
corte de la corrida a `corte/cifras/`, escribe `huella.json` (con los artefactos de `gh api …/artifacts` si se dan) y
regenera `CIFRAS.md`.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from corte import caminos, cifras, codigo, medir

VERSIONADO = codigo.RAIZ / 'corte' / 'cifras'
HUELLA = 'huella.json'
VISTA = 'CIFRAS.md'
PUBLICADOS = (medir.CIFRAS, medir.HUELLAS)


def _mostrar(ruta: Path) -> str:
    return ruta.relative_to(codigo.RAIZ).as_posix() if ruta.is_relative_to(codigo.RAIZ) else str(ruta)


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def recontar(ruta: Path) -> dict:
    """Desde el CSV: documentos y huella por tipo y por grupo tipo + estado + mes, para el origen y cada destino."""
    tipos: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    grupos: dict[tuple[str, str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    llaves: dict[tuple[str, str, str], int] = defaultdict(int)
    with ruta.open(encoding='utf-8', newline='') as archivo:
        lector = csv.reader(archivo)
        if tuple(next(lector)) != cifras.CSV_COLUMNAS:
            raise ValueError(f'{ruta.name}: encabezado distinto de {cifras.CSV_COLUMNAS}')
        for tipo, documento, sucursal, estado, mes, destino, huella in lector:
            linea = f'{documento}|{sucursal}|{huella}'
            llaves[(tipo, documento, sucursal)] += 1
            for d in ('origen', destino):
                tipos[tipo][d].append(linea)
                grupos[(tipo, estado, mes)][d].append(linea)

    def cerrar(lineas: list[str]) -> dict:
        return {'documentos': len(lineas),
                'huella': hashlib.sha256('\n'.join(sorted(lineas)).encode('utf-8')).hexdigest()}

    return {'tipos': {t: {d: cerrar(v) for d, v in b.items()} for t, b in tipos.items()},
            'grupos': {g: {d: cerrar(v) for d, v in b.items()} for g, b in grupos.items()},
            'repetidas': sorted('/'.join(k) for k, n in llaves.items() if n > 1)}


def _destinos(bloque: dict) -> dict[str, dict]:
    salida = {'origen': bloque['origen'], cifras.CARGADO: bloque[cifras.CARGADO], **bloque['no_viaja']}
    return {d: {'documentos': v['documentos'], 'huella': v['huella']} for d, v in salida.items() if v['documentos']}


def revisar_cifras(control: dict, recuento: dict) -> list[str]:
    faltas = list(control.get('faltas', []))
    faltas += [f'el cuadre no cierra: {f}' for f in cifras.cuadre(control['cifras'])]
    for tipo, bloque in control['cifras']['tipos'].items():
        if _destinos(bloque) != recuento['tipos'].get(tipo):
            faltas.append(f'tipo {tipo}: las cifras no son las que da el CSV documento por documento')
    declarados = set()
    for g in control['cifras']['grupos']:
        llave = (g['tipo'], g['estado'], g['mes'])
        declarados.add(llave)
        if _destinos(g) != recuento['grupos'].get(llave):
            faltas.append(f'grupo {" · ".join(llave)}: las cifras no son las que da el CSV')
    faltas += [f'grupo {" · ".join(g)} en el CSV y no en las cifras' for g in sorted(set(recuento['grupos'])
                                                                                    - declarados)]
    faltas += [f'documento repetido en el CSV: {k}' for k in recuento['repetidas'][:20]]
    if control['duplicados_por_documento']:
        faltas.append(f"duplicados por documento: {control['duplicados_por_documento'][:10]}")
    for nombre, r in control['controles_negativos'].items():
        if not r.get('detectado'):
            faltas.append(f'control negativo «{nombre}» no detectado')
    for nombre in ('un_centavo', 'duplicado', 'grieta_utc'):
        if nombre not in control['controles_negativos']:
            faltas.append(f'falta el control negativo «{nombre}»')
    return list(dict.fromkeys(faltas))


def revisar_corte(corte: dict, tablas: dict) -> list[str]:
    """Las faltas que declaró la medición y, otra vez, la cobertura contra el inventario del código DE HOY."""
    faltas = list(corte.get('faltas', []))
    cob = caminos.cobertura(tablas)
    faltas += [f'tabla con identidad sin camino por sellos (inventario de hoy): {t}' for t in cob['sin_camino']]
    faltas += [f'camino huérfano (inventario de hoy): {c}' for c in cob['caminos_huerfanos']]
    medidas = set(corte['tablas'])
    faltas += [f'tabla del inventario que la medición no midió: {t}' for t in sorted(set(tablas) - medidas)]
    for tabla in cob['con_identidad']:
        t = corte['tablas'].get(tabla, {})
        if not any(not c['control_negativo'] for c in t.get('caminos', [])):
            faltas.append(f'{tabla}: la medición no trae ningún camino por sellos')
        for c in t.get('caminos', []):
            if not c['control_negativo'] and not c['comparacion']['coincide']:
                faltas.append(f"{tabla} · {c['nombre']}: los dos caminos no coinciden")
    negativo = corte.get('control_negativo')
    if not negativo or not negativo.get('detectado'):
        faltas.append('el control negativo por fecha_operacion no falló nombrando las altas fechadas hacia atrás')
    return list(dict.fromkeys(faltas))


def comparar_versionado(directorio: Path, versionado: Path) -> tuple[list[str], list[str]]:
    """(faltas, avisos) contra corte/cifras/huella.json."""
    ruta = versionado / HUELLA
    if not ruta.exists():
        return [], [f'sin cifras versionadas ({_mostrar(ruta)}): ésta sería la primera']
    huella = json.loads(ruta.read_text(encoding='utf-8'))
    faltas = []
    for nombre, esperado in huella['archivos'].items():
        actual = sha256(directorio / nombre)
        if actual != esperado:
            faltas.append(f"{nombre}: sha256 {actual[:16]}… ≠ versionado {esperado[:16]}… (corrida "
                          f"{huella.get('corrida', {}).get('corrida')})")
    if faltas and (versionado / medir.CIFRAS).exists():
        antes = json.loads((versionado / medir.CIFRAS).read_text(encoding='utf-8'))
        ahora = json.loads((directorio / medir.CIFRAS).read_text(encoding='utf-8'))
        dif = cifras.diferencias(antes['cifras'], ahora['cifras'])
        faltas += [f"  cambió el total de {g['tipo']}: {g['distinto']}" for g in dif['globales']]
        faltas += [f"  cambió el grupo {g['tipo']} · {g['estado']} · {g['mes']}" for g in dif['por_grupo'][:20]]
    return faltas, []


def revisar_artefactos(directorio: Path, artefactos: list[str]) -> tuple[list[str], list[dict]]:
    faltas, filas = [], []
    for dato in artefactos:
        nombre, _, digest = dato.partition('=')
        esperado = 'sha256:' + sha256(directorio / nombre)
        filas.append({'artefacto': nombre, 'digest': digest or '(vacío)', 'coincide': digest == esperado})
        if digest != esperado:
            faltas.append(f'el digest del artefacto {nombre} ({digest or "vacío"}) no es el sha256 del archivo '
                          f'({esperado})')
    return faltas, filas


def evaluar(directorio: Path, versionado: Path = VERSIONADO) -> dict:
    corte = json.loads((directorio / medir.CORTE).read_text(encoding='utf-8'))
    control = json.loads((directorio / medir.CIFRAS).read_text(encoding='utf-8'))
    faltas, avisos = [], []
    declarado = control['huellas_por_documento']['sha256']
    real = sha256(directorio / medir.HUELLAS)
    if declarado != real:
        faltas.append(f'el CSV de huellas no es el que declaran las cifras: {real} ≠ {declarado}')
    inv = codigo.inventario()
    faltas += revisar_corte(corte, inv['tablas'])
    faltas += revisar_cifras(control, recontar(directorio / medir.HUELLAS))
    f, a = comparar_versionado(directorio, versionado)
    faltas += f
    avisos += a
    return {'corte': corte, 'cifras': control, 'faltas': faltas, 'avisos': avisos, 'verde': not faltas,
            'sha256': {n: sha256(directorio / n) for n in PUBLICADOS}}


def markdown_artefactos(filas: list[dict]) -> str:
    return '\n'.join(['\n### Artefactos inmutables publicados', '',
                      '| artefacto | digest de GitHub | = sha256 del archivo |', '|---|---|---|']
                     + [f"| `{a['artefacto']}` | `{a['digest']}` | {'sí' if a['coincide'] else 'NO'} |" for a in filas])


def markdown(r: dict) -> str:
    c, k = r['corte'], r['cifras']
    partes = [f"## Corte por dos caminos y cifras de control: {'verde' if r['verde'] else 'ROJO'}"]
    filas = ['| tabla | corte | congelamiento | delta | posterior | huecos | caminos por sellos |',
             '|---|---|---|---|---|---|---|']
    for tabla, t in c['tablas'].items():
        if 'por_identidad' not in t:
            filas.append(f"| `{tabla}` | – | – | – | – | – | sin identidad: se compara completo |")
            continue
        p = t['por_identidad']
        caminos_md = '<br>'.join(f"{'✔' if x['comparacion']['coincide'] else '✘'} {x['nombre']}: "
                                 f"{x['delta']} + {x['posterior']}" for x in t['caminos'])
        filas.append(f"| `{tabla}` | {p['corte']:,} | {p['congelamiento']:,} | {p['delta']:,} | {p['posterior']:,} | "
                     f"{t['huecos']['cuantos']} | {caminos_md} |")
    partes.append('\n'.join(filas))
    n = c.get('control_negativo') or {}
    partes.append(f"**Control negativo (fecha_operacion):** pierde {n.get('perdidos_por_el_camino')} ids y nombra "
                  f"{n.get('nombradas')} de {n.get('esperadas')} altas fechadas hacia atrás: "
                  + ', '.join(f'`{x}`' for x in n.get('altas_fechadas_hacia_atras', [])))
    filas = ['| documentos | origen | cargado | ' + ' | '.join(cifras.MOTIVOS) + ' |',
             '|---|---|---|' + '---|' * len(cifras.MOTIVOS)]
    for tipo, b in k['cifras']['tipos'].items():
        filas.append(f"| {tipo} | {b['origen']['documentos']:,} | {b['cargado']['documentos']:,} | "
                     + ' | '.join(f"{b['no_viaja'][m]['documentos']:,}" for m in cifras.MOTIVOS) + ' |')
    partes.append('\n'.join(filas))
    con = k['conciliacion']
    partes.append(f"Duplicados por documento: **{len(k['duplicados_por_documento'])}**. Conciliación del delta por "
                  f"llave de negocio: {con['por_llave']['duplicados']} duplicados y "
                  f"{con['por_llave']['registros_que_salen']} registros viejos que salen (re-registros del día: "
                  f"{con['re_registros_del_dia']['de_documentos_del_corte']} de documentos del corte); por id "
                  f"(control negativo): {con['por_id']['duplicados']} "
                  'duplicados.')
    partes.append('Controles negativos de las cifras: ' + ', '.join(
        f"{nombre} {'detectado' if x['detectado'] else 'NO detectado'}"
        for nombre, x in k['controles_negativos'].items()))
    partes.append('sha256: ' + ' · '.join(f'`{n}` `{s}`' for n, s in r['sha256'].items()))
    if r['faltas']:
        partes.append('**Faltas:**\n' + '\n'.join(f'- {f}' for f in r['faltas']))
    if r['avisos']:
        partes.append('**Avisos:**\n' + '\n'.join(f'- {a}' for a in r['avisos']))
    return '\n\n'.join(partes) + '\n'


def texto(r: dict) -> str:
    lineas = [medir.resumen(r['corte'], r['cifras'])]
    lineas += [f'sha256 {n}: {s}' for n, s in r['sha256'].items()]
    lineas += [f'✘ {f}' for f in r['faltas']]
    lineas += [f'· {a}' for a in r['avisos']]
    lineas.append('Resultado: ' + ('VERDE' if r['verde'] else 'ROJO'))
    return '\n'.join(lineas)


def versionar(directorio: Path, artefactos: Path | None, versionado: Path = VERSIONADO) -> list[Path]:
    """Copia las cifras y el corte de una corrida a corte/cifras/, con su huella y la vista."""
    versionado.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nombre in (medir.CIFRAS, medir.CORTE):
        shutil.copyfile(directorio / nombre, versionado / nombre)
        escritos.append(versionado / nombre)
    corte = json.loads((directorio / medir.CORTE).read_text(encoding='utf-8'))
    huella = {'que_es': 'sha256 de las cifras de control y de las huellas por documento de una corrida del CI; el job '
                        '`corte` exige que las de cada corrida sean éstas (python -m corte.veredicto --versionar)',
              'corrida': corte.get('ci', {}),
              'archivos': {n: sha256(directorio / n) for n in PUBLICADOS}}
    if artefactos is not None:
        listado = json.loads(artefactos.read_text(encoding='utf-8'))
        huella['artefactos'] = {a['name']: {'id': a['id'], 'digest': a.get('digest'), 'bytes': a.get('size_in_bytes'),
                                            'expira': a.get('expires_at')}
                                for a in listado.get('artifacts', []) if a['name'] in PUBLICADOS}
    (versionado / HUELLA).write_text(json.dumps(huella, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    escritos.append(versionado / HUELLA)
    escritos.append(escribir_vista(versionado))
    return escritos


def escribir_vista(versionado: Path = VERSIONADO) -> Path:
    from corte import vista_cifras
    ruta = versionado / VISTA
    ruta.write_text(vista_cifras.markdown(versionado), encoding='utf-8')
    return ruta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.veredicto', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('directorio', type=Path, help='lo que dejó python -m corte.medir')
    parser.add_argument('--resumen', type=Path, help='agrega el resultado en Markdown (p. ej. $GITHUB_STEP_SUMMARY)')
    parser.add_argument('--artefacto', action='append', default=[], metavar='NOMBRE=DIGEST',
                        help='digest con el que GitHub publicó un artefacto (sha256:…)')
    parser.add_argument('--versionar', action='store_true', help='copia la corrida a corte/cifras/')
    parser.add_argument('--artefactos', type=Path, help='JSON de gh api repos/…/actions/runs/<id>/artifacts')
    args = parser.parse_args(argv)
    if args.versionar:
        for ruta in versionar(args.directorio, args.artefactos):
            print(f'escrito {_mostrar(ruta)}')
        return 0
    if args.artefacto:                 # después de publicar: sólo los digests, el veredicto ya está en el resumen
        faltas, filas = revisar_artefactos(args.directorio, args.artefacto)
        for f in filas:
            print(f"{f['artefacto']}: {f['digest']} · {'= sha256 del archivo' if f['coincide'] else 'DISTINTO'}")
        if args.resumen:
            with args.resumen.open('a', encoding='utf-8') as salida:
                salida.write(markdown_artefactos(filas) + ''.join(f'\n- ✘ {f}' for f in faltas) + '\n')
        return 1 if faltas else 0
    r = evaluar(args.directorio)
    print(texto(r))
    if args.resumen:
        with args.resumen.open('a', encoding='utf-8') as salida:
            salida.write(markdown(r))
    return 0 if r['verde'] else 1


if __name__ == '__main__':
    sys.exit(main())
