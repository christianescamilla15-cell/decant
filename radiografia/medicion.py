"""Medición de la radiografía contra el catálogo de trampas (`legado/TRAMPAS.md`).

Es el ÚNICO módulo de la radiografía que lee el catálogo, y lo hace DESPUÉS: los detectores ya corrieron y su
informe está escrito. Aquí sólo se cuenta qué señales esperadas aparecen entre los hallazgos y cuáles no.

    python -m radiografia.medicion --informe radiografia/informe/radiografia.json --trampas legado/TRAMPAS.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_FILA = re.compile(r'^\|\s*(?P<id>[TD]\d+)\s*\|\s*(?P<nombre>[^|]+?)\s*\|\s*(?P<senales>[^|]*?)\s*\|\s*$')
_SENAL = re.compile(r'`([a-z_]+) → ([^`]+)`')
# Inventario, no señal de defecto: no cuenta como ruido ni como acierto.
INFORMATIVAS = frozenset(('literal_magico', 'if_exists_guarda'))


def leer_catalogo(texto: str) -> list[dict]:
    trampas = []
    for linea in texto.splitlines():
        m = _FILA.match(linea.strip())
        if not m:
            continue
        senales = [(c, o.strip().lower()) for c, o in _SENAL.findall(m.group('senales'))]
        trampas.append({'id': m.group('id'), 'nombre': m.group('nombre'), 'senales': senales})
    return trampas


def medir(hallazgos: list[dict], trampas: list[dict]) -> dict:
    presentes = {(h['categoria'], h['objeto'].lower()) for h in hallazgos}
    usadas: set[tuple[str, str]] = set()
    filas = []
    for t in trampas:
        encontradas = [s for s in t['senales'] if s in presentes]
        usadas.update(encontradas)
        if not t['senales']:
            estado = 'sin patrón en S1'
        elif len(encontradas) == len(t['senales']):
            estado = 'detectada'
        elif encontradas:
            estado = 'parcial'
        else:
            estado = 'no detectada'
        filas.append({**t, 'senales': [f'{c} → {o}' for c, o in t['senales']],
                      'encontradas': [f'{c} → {o}' for c, o in encontradas], 'estado': estado})
    principales = [f for f in filas if f['id'].startswith('T')]
    detectadas = sum(1 for f in principales if f['estado'] == 'detectada')
    fuera = sorted({(h['categoria'], h['objeto']) for h in hallazgos
                    if h['categoria'] not in INFORMATIVAS and (h['categoria'], h['objeto'].lower()) not in usadas})
    return {
        'trampas': len(principales),
        'detectadas': detectadas,
        'pct_deteccion': round(100 * detectadas / len(principales), 1) if principales else 0.0,
        'parciales': sum(1 for f in principales if f['estado'] == 'parcial'),
        'filas': filas,
        'hallazgos_sin_trampa': [{'categoria': c, 'objeto': o} for c, o in fuera],
    }


def markdown(m: dict, base: str) -> str:
    r = [f'# Medición de la radiografía de `{base}` contra `legado/TRAMPAS.md`\n',
         'Los detectores corrieron sin leer el catálogo; esta tabla sólo cuenta qué señales esperadas aparecieron.\n',
         f"**Detección: {m['detectadas']} de {m['trampas']} trampas ({m['pct_deteccion']} %)**"
         + (f" · {m['parciales']} parcial(es)" if m['parciales'] else '') + '.\n',
         '| Id | Trampa | Estado | Señales esperadas | Encontradas |', '|---|---|---|---|---|']
    for f in m['filas']:
        r.append(f"| {f['id']} | {f['nombre']} | {f['estado']} | {'<br>'.join(f['senales']) or '—'} | "
                 f"{'<br>'.join(f['encontradas']) or '—'} |")
    r.append(f"\n## Hallazgos que no corresponden a ninguna trampa ({len(m['hallazgos_sin_trampa'])})\n")
    r.append('Patrones que sí están en el código o en los datos pero que el catálogo no siembra como defecto: '
             'hay que revisarlos uno por uno (algunos son ruido del patrón, otros son hallazgos reales).\n')
    r.append('| Patrón | Objeto |')
    r.append('|---|---|')
    for h in m['hallazgos_sin_trampa']:
        r.append(f"| {h['categoria']} | `{h['objeto']}` |")
    return '\n'.join(r) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m radiografia.medicion', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--informe', type=Path, default=Path('radiografia/informe/radiografia.json'))
    parser.add_argument('--trampas', type=Path, default=Path('legado/TRAMPAS.md'))
    parser.add_argument('--minimo', type=float, default=0.0, help='falla si el %% de detección queda debajo')
    args = parser.parse_args(argv)
    informe = json.loads(args.informe.read_text(encoding='utf-8'))
    resultado = medir(informe['hallazgos'], leer_catalogo(args.trampas.read_text(encoding='utf-8')))
    destino = args.informe.parent
    (destino / 'medicion.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + '\n',
                                           encoding='utf-8')
    (destino / 'medicion.md').write_text(markdown(resultado, informe['base']), encoding='utf-8')
    print(f"detección: {resultado['detectadas']} de {resultado['trampas']} trampas ({resultado['pct_deteccion']} %) · "
          f"{len(resultado['hallazgos_sin_trampa'])} hallazgos fuera del catálogo · {destino / 'medicion.md'}")
    for f in resultado['filas']:
        print(f"  {f['id']:3s} {f['estado']:16s} {f['nombre']}")
    return 0 if resultado['pct_deteccion'] >= args.minimo else 1


if __name__ == '__main__':
    sys.exit(main())
