"""T4, lados invertidos: el BINDING de la pantalla del legado, no el nombre de la tabla.

La pantalla (`legado/pantalla/app.py`) declara en `REJILLAS` qué conjunto de resultados de `sp_detalle_operacion`
pinta cada rejilla. Qué TABLA hay detrás de cada conjunto no se adivina por su nombre: se ejecuta el procedimiento
sobre el respaldo restaurado y se busca qué tabla contiene exactamente esos renglones. Así se sabe qué ve el usuario
en «Liquidado por el corresponsal» y en «Solicitado por el cliente».
"""
from __future__ import annotations

import ast
import unicodedata
from pathlib import Path

PANTALLA = Path(__file__).resolve().parent.parent / 'legado' / 'pantalla' / 'app.py'
TABLAS_DE_PARTIDAS = ('dbo.partida_solicitada', 'dbo.partida_liquidada')
# Consultas fijas por tabla candidata (sin armar SQL con texto).
_PARTIDAS = {
    'dbo.partida_solicitada': 'SELECT renglon, concepto, moneda, monto, fecha_hora, referencia '
                              'FROM dbo.partida_solicitada WHERE orden_id = %s ORDER BY renglon',
    'dbo.partida_liquidada': 'SELECT renglon, concepto, moneda, monto, fecha_hora, referencia '
                             'FROM dbo.partida_liquidada WHERE orden_id = %s ORDER BY renglon',
}


def rejillas(ruta: Path = PANTALLA) -> list[dict]:
    """Lee `REJILLAS` del código de la pantalla SIN importarla (es un literal: id, título y conjunto)."""
    arbol = ast.parse(ruta.read_text(encoding='utf-8'))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REJILLAS' for t in nodo.targets):
            return [dict(x) for x in ast.literal_eval(nodo.value)]
    raise ValueError(f'{ruta}: no declara REJILLAS')


def campo_json(titulo: str) -> str:
    """«Liquidado por el corresponsal» → `liquidadoPorElCorresponsal` (el nombre que debe usar el TO-BE)."""
    simple = unicodedata.normalize('NFKD', titulo).encode('ascii', 'ignore').decode()
    palabras = simple.split()
    return palabras[0].lower() + ''.join(p[:1].upper() + p[1:].lower() for p in palabras[1:])


def _conjuntos(cursor) -> list[list[tuple]]:
    resultado = []
    while True:
        if cursor.description:
            resultado.append([tuple(f) for f in cursor.fetchall()])
        if not cursor.nextset():
            return resultado


def tabla_de_cada_conjunto(cursor, operacion_id: int, orden_id: int) -> dict[int, str]:
    """Ejecuta `sp_detalle_operacion` y averigua qué tabla del legado alimenta cada conjunto de partidas."""
    cursor.execute('EXEC dbo.sp_detalle_operacion @operacion_id = %s', (operacion_id,))
    conjuntos = _conjuntos(cursor)
    contenido = {}
    for tabla, consulta in _PARTIDAS.items():
        cursor.execute(consulta, (orden_id,))
        contenido[tabla] = [tuple(f) for f in cursor.fetchall()]
    resultado = {}
    for indice, filas in enumerate(conjuntos[1:], start=1):
        candidatas = [t for t, c in contenido.items() if c == filas and filas]
        if len(candidatas) != 1:
            raise ValueError(f'conjunto {indice}: no se identifica una sola tabla ({candidatas})')
        resultado[indice] = candidatas[0]
    return resultado


def ejemplo_con_dos_lados(cursor) -> tuple[int, int]:
    """Una operación cuya orden vigente tiene partidas en las dos tablas (para identificar el binding)."""
    cursor.execute("""SELECT TOP 1 p.operacion_id, p.id FROM dbo.orden_pago p
                      WHERE p.estatus = 'CONCILIADA'
                        AND EXISTS (SELECT 1 FROM dbo.partida_solicitada s WHERE s.orden_id = p.id)
                        AND EXISTS (SELECT 1 FROM dbo.partida_liquidada l WHERE l.orden_id = p.id)
                      ORDER BY p.id DESC""")
    operacion, orden = cursor.fetchone()
    return operacion, orden


def binding(cursor, ruta: Path = PANTALLA) -> dict[str, dict]:
    """Título de la rejilla → {conjunto, tabla del legado, campo JSON del TO-BE}."""
    operacion, orden = ejemplo_con_dos_lados(cursor)
    tablas = tabla_de_cada_conjunto(cursor, operacion, orden)
    return {r['titulo']: {'rejilla': r['id'], 'conjunto': r['conjunto'], 'tabla_legado': tablas[r['conjunto']],
                          'campo_tobe': campo_json(r['titulo']), 'operacion_de_prueba': operacion}
            for r in rejillas(ruta)}
