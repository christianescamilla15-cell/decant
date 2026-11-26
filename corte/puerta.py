"""La PUERTA de cobertura de salidas (ADR 0014, criterio 1 del plan de S3):

    python -m corte.puerta                                   # código + observación versionada + renglones
    python -m corte.puerta --observado corte/observado-ci/observado.json --resumen "$GITHUB_STEP_SUMMARY"

Lee el inventario DEL CÓDIGO en el momento (no el JSON versionado: un objeto sembrado en el SQL entra solo), lo cruza
con lo que el CI observó y exige un renglón para cada objeto y para cada login. Falla (sale con 1) y NOMBRA:
- cada objeto del código, o que el servidor tiene o ejecutó fuera del código, sin renglón;
- cada login observado sin renglón, y cada aplicación de un login que su renglón no declara;
- cada renglón inválido (destino, evidencia que no existe, retiro sin dueño, fecha o vigía), duplicado o huérfano;
- los `pendiente`, con su conteo por tipo: mientras haya alguno, la puerta está en rojo a propósito (define el alcance
  y lista lo que falta).
Nunca decide un destino por su cuenta: lo «sin ejecución observada» sigue necesitando su renglón.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from corte import codigo, cruce, renglones

INVENTARIO = codigo.RAIZ / 'corte' / 'inventario'
EJECUCION = {cruce.OBSERVADA: 'observada', cruce.POR_QUIEN_LA_USA: 'observada por quien la usa',
             cruce.SIN_EJECUCION: 'sin ejecución observada'}
OBSERVADO = INVENTARIO / 'observado.json'
RENGLONES = INVENTARIO / 'renglones.yml'


def evaluar(inv: dict, cruzado: dict, lista: list[renglones.Renglon], errores_de_formato: list[str],
            raiz: Path = codigo.RAIZ) -> dict:
    tipos = {o['id']: o['tipo'] for o in inv['objetos']}
    tipos.update({f['id']: f['tipo'] for f in cruzado['fuera_del_codigo']})
    logins = cruzado['consumidores']
    por_clave: dict[tuple[str, str], renglones.Renglon] = {}
    duplicados, huerfanos, invalidos = [], [], {}
    for r in lista:
        llave = (r.clase, r.clave)
        if llave in por_clave:
            duplicados.append(f'{r.clase} {r.clave}')
            continue
        por_clave[llave] = r
        if (r.clase == 'objeto' and r.clave not in tipos) or (r.clase == 'login' and r.clave not in logins):
            huerfanos.append(f'{r.clase} {r.clave}')
        problemas = renglones.validar(r, raiz)
        if problemas:
            invalidos[f'{r.clase} {r.clave}'] = problemas
    sin_objeto = [i for i in tipos if ('objeto', i) not in por_clave]
    sin_login = [x for x in logins if ('login', x) not in por_clave]
    aplicaciones = [f'{x} · {a}' for x, c in logins.items() if ('login', x) in por_clave
                    for a in c['aplicaciones'] if not por_clave[('login', x)].aplicacion_conocida(a)]
    vigentes = [r for r in por_clave.values()
                if (r.clase == 'objeto' and r.clave in tipos) or (r.clase == 'login' and r.clave in logins)]
    pendientes = [r for r in vigentes if r.destino == 'pendiente']
    resultado = {
        'objetos': len(tipos), 'objetos_del_codigo': len(inv['objetos']), 'logins': len(logins),
        'por_tipo': dict(Counter(tipos.values())),
        'destinos': {d: dict(Counter(tipos[r.clave] if r.clase == 'objeto' else 'login'
                                     for r in vigentes if r.destino == d))
                     for d in renglones.DESTINOS},
        'sin_renglon': {'objetos': sorted(sin_objeto), 'logins': sorted(sin_login),
                        'aplicaciones': sorted(aplicaciones)},
        'renglones_invalidos': invalidos, 'formato': errores_de_formato, 'duplicados': sorted(duplicados),
        'huerfanos': sorted(huerfanos),
        'pendientes': [{'clave': r.clave, 'tipo': tipos.get(r.clave, 'login'),
                        'acceso': next((o['acceso'] for o in inv['objetos'] if o['id'] == r.clave), None),
                        'ejecucion': cruzado['objetos'].get(r.clave, {}).get('ejecucion'), 'nota': r.nota}
                       for r in sorted(pendientes, key=lambda r: (r.clase, tipos.get(r.clave, ''), r.clave))],
        'pendientes_por_tipo': dict(Counter(tipos.get(r.clave, 'login') for r in pendientes)),
        'sin_ejecucion_observada': cruce.sin_ejecucion(cruzado),
    }
    resultado['verde'] = not (sin_objeto or sin_login or aplicaciones or invalidos or errores_de_formato
                              or duplicados or huerfanos or pendientes)
    return resultado


def texto(r: dict) -> str:
    lineas = [f"Puerta de cobertura de salidas (ADR 0014): {r['objetos']} objetos "
              f"({r['objetos_del_codigo']} del código), {r['logins']} logins",
              '  por tipo: ' + ', '.join(f'{t} {n}' for t, n in sorted(r['por_tipo'].items())),
              '  destinos: ' + ' · '.join(f'{d} {sum(c.values())}' for d, c in r['destinos'].items())]
    faltas = [('objetos sin renglón', r['sin_renglon']['objetos']), ('logins sin renglón', r['sin_renglon']['logins']),
              ('aplicaciones que su login no declara', r['sin_renglon']['aplicaciones']),
              ('renglones duplicados', r['duplicados']), ('renglones huérfanos (su objeto o login no existe)',
                                                          r['huerfanos']),
              ('errores de formato', r['formato'])]
    for titulo, lista in faltas:
        if lista:
            lineas.append(f'✘ {titulo} ({len(lista)}):')
            lineas += [f'    - {x}' for x in lista]
    for clave, problemas in r['renglones_invalidos'].items():
        lineas.append(f'✘ renglón inválido: {clave}')
        lineas += [f'    - {p}' for p in problemas]
    if r['pendientes']:
        lineas.append(f"✘ pendientes ({len(r['pendientes'])}): "
                      + ', '.join(f'{t} {n}' for t, n in sorted(r['pendientes_por_tipo'].items())))
        for p in r['pendientes']:
            detalle = ', '.join(x for x in (p['tipo'], p['acceso'], EJECUCION.get(p['ejecucion'])) if x)
            lineas.append(f"    - {p['clave']} ({detalle})")
    lineas.append(f"  sin ejecución observada: {len(r['sin_ejecucion_observada'])} (clasifica; no recorta)")
    lineas.append('Resultado: ' + ('VERDE' if r['verde'] else 'ROJO'))
    return '\n'.join(lineas)


def markdown(r: dict) -> str:
    filas = '\n'.join(f"| {d} | {sum(c.values())} | {', '.join(f'{t} {n}' for t, n in sorted(c.items())) or '–'} |"
                      for d, c in r['destinos'].items())
    sin = r['sin_renglon']
    partes = [f"## Puerta de cobertura de salidas: {'verde' if r['verde'] else 'ROJA'}",
              f"{r['objetos']} objetos ({r['objetos_del_codigo']} del código) y {r['logins']} logins.",
              '| destino | renglones | por tipo |', '|---|---|---|', filas,
              f"Sin renglón: {len(sin['objetos'])} objetos, {len(sin['logins'])} logins, "
              f"{len(sin['aplicaciones'])} aplicaciones. Inválidos: {len(r['renglones_invalidos'])}. "
              f"Huérfanos: {len(r['huerfanos'])}. Sin ejecución observada: {len(r['sin_ejecucion_observada'])}."]
    for titulo, lista in (('Objetos sin renglón', sin['objetos']), ('Logins sin renglón', sin['logins']),
                          ('Aplicaciones sin renglón', sin['aplicaciones'])):
        if lista:
            partes.append(f'**{titulo}:** ' + ', '.join(f'`{x}`' for x in lista))
    if r['pendientes']:
        partes.append('**Pendientes:** ' + ', '.join(f'`{p["clave"]}`' for p in r['pendientes']))
    return '\n\n'.join(partes) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.puerta', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sql', type=Path, default=codigo.SQL)
    parser.add_argument('--pantalla', type=Path, default=codigo.PANTALLA)
    parser.add_argument('--interfaces', type=Path, default=codigo.INTERFACES)
    parser.add_argument('--observado', type=Path, default=OBSERVADO)
    parser.add_argument('--renglones', type=Path, default=RENGLONES)
    parser.add_argument('--resumen', type=Path, help='agrega el resultado en Markdown (p. ej. $GITHUB_STEP_SUMMARY)')
    parser.add_argument('--json', type=Path, help='escribe el resultado completo en JSON')
    args = parser.parse_args(argv)
    inv = codigo.inventario(args.sql, args.pantalla, args.interfaces)
    observado = json.loads(args.observado.read_text(encoding='utf-8'))
    cruzado = cruce.cruzar(inv, observado)
    lista, formato = renglones.cargar(args.renglones)
    if not observado.get('terminado'):
        formato.append(f'la observación {args.observado} no terminó: no se puede contar a los consumidores')
    r = evaluar(inv, cruzado, lista, formato)
    print(texto(r))
    if args.resumen:
        with args.resumen.open('a', encoding='utf-8') as salida:
            salida.write(markdown(r))
    if args.json:
        args.json.write_text(json.dumps(r, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 0 if r['verde'] else 1


if __name__ == '__main__':
    sys.exit(main())
