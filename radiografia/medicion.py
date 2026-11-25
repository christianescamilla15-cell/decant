"""Medición de la radiografía contra el catálogo de trampas (`legado/TRAMPAS.md`).

Es el ÚNICO módulo de la radiografía que lee el catálogo, y lo hace DESPUÉS: los detectores ya corrieron y su
informe está escrito. Aquí sólo se cuenta qué señales esperadas aparecen entre los hallazgos y cuáles no.

    python -m radiografia.medicion --trampas legado/TRAMPAS.md --trampas legado/TRAMPAS_CIEGAS.md \
        --conocido legado/TRAMPAS_CIEGAS.md
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


def con_veredictos(m: dict, veredictos: list[dict]) -> dict:
    """Pega a cada hallazgo fuera del catálogo su veredicto medido (radiografia/veredictos.py)."""
    por_llave = {(v['categoria'], v['objeto']): v for v in veredictos}
    for h in m['hallazgos_sin_trampa']:
        v = por_llave.get((h['categoria'], h['objeto']))
        h['clase'] = v['clase'] if v else 'sin veredicto'
        h['veredicto'] = v['veredicto'] if v else ''
        h['medicion'] = v['medicion'] if v else {}
    m['sin_veredicto'] = sum(1 for h in m['hallazgos_sin_trampa'] if h['clase'] == 'sin veredicto')
    return m


def medir_catalogos(hallazgos: list[dict], catalogos: list[dict]) -> dict:
    """Mide contra uno o varios catálogos POR SEPARADO. «Fuera del catálogo» es lo que no explica ninguno.

    catalogos: [{'archivo', 'trampas', 'nota'}]; el primero es el principal (sus cifras quedan arriba).
    """
    resultados = [{**medir(hallazgos, c['trampas']), 'archivo': c['archivo'], 'nota': c.get('nota')}
                  for c in catalogos]
    senales = {s for c in catalogos for t in c['trampas'] for s in t['senales']}
    fuera = sorted({(h['categoria'], h['objeto']) for h in hallazgos
                    if h['categoria'] not in INFORMATIVAS and (h['categoria'], h['objeto'].lower()) not in senales})
    for r in resultados:
        r.pop('hallazgos_sin_trampa', None)
    principal = {k: v for k, v in resultados[0].items() if k not in ('archivo', 'nota')}
    return {**principal, 'catalogos': resultados,
            'hallazgos_sin_trampa': [{'categoria': c, 'objeto': o} for c, o in fuera]}


def _tabla_catalogo(c: dict) -> list[str]:
    r = [f"## `{c['archivo']}`\n"]
    if c.get('nota'):
        r.append(f"> {c['nota']}\n")
    r.append(f"**Detección: {c['detectadas']} de {c['trampas']} trampas ({c['pct_deteccion']} %)**"
             + (f" · {c['parciales']} parcial(es)" if c['parciales'] else '') + '.\n')
    r += ['| Id | Trampa | Estado | Señales esperadas | Encontradas |', '|---|---|---|---|---|']
    for f in c['filas']:
        r.append(f"| {f['id']} | {f['nombre']} | {f['estado']} | {'<br>'.join(f['senales']) or '—'} | "
                 f"{'<br>'.join(f['encontradas']) or '—'} |")
    return r + ['']


def markdown(m: dict, base: str) -> str:
    catalogos = m.get('catalogos') or [{**m, 'archivo': 'legado/TRAMPAS.md', 'nota': None}]
    r = [f'# Medición de la radiografía de `{base}`\n',
         'Los detectores corrieron sin leer los catálogos; estas tablas sólo cuentan qué señales esperadas '
         'aparecieron. Cada catálogo se mide por separado.\n']
    for c in catalogos:
        r += _tabla_catalogo(c)
    r.append(f"## Hallazgos que no corresponden a ninguna trampa ({len(m['hallazgos_sin_trampa'])})\n")
    r.append('Cada uno lleva su veredicto MEDIDO sobre el respaldo restaurado (`radiografia/veredictos.py`; la '
             'medición completa está en `veredictos.json`).\n')
    r.append('| Patrón | Objeto | Clase | Veredicto |')
    r.append('|---|---|---|---|')
    for h in m['hallazgos_sin_trampa']:
        veredicto = h.get('veredicto', '').replace('|', '\\|')
        r.append(f"| {h['categoria']} | `{h['objeto']}` | {h.get('clase', 'sin veredicto')} | {veredicto} |")
    if m.get('sin_veredicto'):
        r.append(f"\n**{m['sin_veredicto']} hallazgos sin veredicto.**")
    return '\n'.join(r) + '\n'


NOTA_CONOCIDO = ('Catálogo CONOCIDO: el autor de los detectores ya lo leyó, y los detectores de esta versión se '
                 'escribieron después de verlo. Detectar estas trampas ahora NO cuenta como control; el control real '
                 'de esta versión es una siembra a ciegas nueva.')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m radiografia.medicion', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--informe', type=Path, default=Path('radiografia/informe/radiografia.json'))
    parser.add_argument('--trampas', type=Path, action='append',
                        help='catálogo (repetible; el primero es el principal). Por omisión, legado/TRAMPAS.md')
    parser.add_argument('--conocido', type=Path, action='append', default=[],
                        help='catálogo que ya no cuenta como control (se dice en el informe)')
    parser.add_argument('--minimo', type=float, default=0.0,
                        help='falla si el %% de detección del catálogo principal queda debajo')
    args = parser.parse_args(argv)
    archivos = args.trampas or [Path('legado/TRAMPAS.md')]
    informe = json.loads(args.informe.read_text(encoding='utf-8'))
    catalogos = [{'archivo': str(a), 'trampas': leer_catalogo(a.read_text(encoding='utf-8')),
                  'nota': NOTA_CONOCIDO if a in args.conocido else None} for a in archivos]
    resultado = medir_catalogos(informe['hallazgos'], catalogos)
    destino = args.informe.parent
    veredictos = destino / 'veredictos.json'
    if veredictos.exists():
        resultado = con_veredictos(resultado, json.loads(veredictos.read_text(encoding='utf-8')))
    (destino / 'medicion.json').write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + '\n',
                                           encoding='utf-8')
    (destino / 'medicion.md').write_text(markdown(resultado, informe['base']), encoding='utf-8')
    for c in resultado['catalogos']:
        print(f"{c['archivo']}: {c['detectadas']} de {c['trampas']} trampas ({c['pct_deteccion']} %)"
              + (' · conocido, no cuenta como control' if c['nota'] else ''))
        for f in c['filas']:
            print(f"  {f['id']:3s} {f['estado']:16s} {f['nombre']}")
    print(f"{len(resultado['hallazgos_sin_trampa'])} hallazgos fuera de los catálogos · {destino / 'medicion.md'}")
    return 0 if resultado['pct_deteccion'] >= args.minimo else 1


if __name__ == '__main__':
    sys.exit(main())
