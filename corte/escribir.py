"""Regenera lo versionado del inventario a partir del código y de la observación:

    python -m corte.escribir              # escribe corte/inventario/objetos.json e INVENTARIO.md
    python -m corte.escribir --verificar  # sólo compara; sale con 1 si algo quedó viejo

`objetos.json` sale sólo del código (determinista). `INVENTARIO.md` cruza además `observado.json` (la observación del
CI que se versiona) y `renglones.yml`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from corte import codigo, cruce, puerta, renglones, vista

OBJETOS = puerta.INVENTARIO / 'objetos.json'
VISTA = puerta.INVENTARIO / 'INVENTARIO.md'


def generar() -> dict[Path, str]:
    inv = codigo.inventario()
    archivos = {OBJETOS: json.dumps(inv, ensure_ascii=False, indent=1) + '\n'}
    if puerta.OBSERVADO.exists():
        cruzado = cruce.cruzar(inv, json.loads(puerta.OBSERVADO.read_text(encoding='utf-8')))
        lista, formato = renglones.cargar(puerta.RENGLONES)
        archivos[VISTA] = vista.markdown(inv, cruzado, lista, puerta.evaluar(inv, cruzado, lista, formato))
    return archivos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.escribir', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--verificar', action='store_true')
    args = parser.parse_args(argv)
    viejos = []
    for ruta, contenido in generar().items():
        actual = ruta.read_text(encoding='utf-8') if ruta.exists() else None
        if actual == contenido:
            continue
        if args.verificar:
            viejos.append(ruta.relative_to(codigo.RAIZ).as_posix())
        else:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(contenido, encoding='utf-8')
            print(f'escrito {ruta.relative_to(codigo.RAIZ).as_posix()}')
    if viejos:
        print('desactualizado (corre python -m corte.escribir): ' + ', '.join(viejos), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
