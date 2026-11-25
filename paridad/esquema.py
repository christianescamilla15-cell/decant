"""Comparación de ESQUEMA columna por columna, después de CADA carga: legado restaurado → mapeo → TO-BE.

Es la única comparación que caza una columna que ningún reporte ni pantalla imprime (T6, `codigo_proposito`): si el
TO-BE la pierde, ninguna salida lo extraña. Reglas:

- cada columna del legado tiene un destino que EXISTE en el TO-BE, con un tipo compatible, o un motivo escrito para
  no migrarse;
- cada columna del TO-BE tiene un origen en el legado o está declarada como nueva;
- texto: el TO-BE no puede ser más corto; decimales: la misma precisión y escala; fechas: `timestamptz` y sólo con el
  parche T5; nulos: el TO-BE admite NULL si el legado lo admitía o si un parche de centinela lo introduce.
"""
from __future__ import annotations

from paridad.mapeo import MAPEO, NUEVAS

_TEXTO = {'char', 'varchar', 'nchar', 'nvarchar'}
_ENTEROS = {'tinyint': 'smallint', 'smallint': 'smallint', 'int': 'integer', 'bigint': 'bigint'}
_FECHAS = {'smalldatetime', 'datetime', 'datetime2'}


def esquema_legado(cursor) -> dict[str, dict]:
    cursor.execute("""
        SELECT LOWER(s.name + '.' + t.name), c.name, ty.name, c.max_length, c.precision, c.scale, c.is_nullable
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE t.is_ms_shipped = 0
        ORDER BY 1, c.column_id""")
    columnas = {}
    for tabla, columna, tipo, largo, precision, escala, nulable in cursor.fetchall():
        caracteres = largo // 2 if tipo in ('nchar', 'nvarchar') else largo
        columnas[f'{tabla}.{columna}'] = {'tipo': tipo, 'largo': caracteres, 'precision': precision,
                                          'escala': escala, 'nulable': bool(nulable)}
    return columnas


def esquema_tobe(cursor, esquema: str = 'decant') -> dict[str, dict]:
    cursor.execute("""
        SELECT table_schema || '.' || table_name, column_name, data_type, character_maximum_length,
               numeric_precision, numeric_scale, is_nullable = 'YES'
        FROM information_schema.columns WHERE table_schema = %s
        ORDER BY 1, ordinal_position""", (esquema,))
    return {f'{t}.{c}': {'tipo': tipo, 'largo': largo, 'precision': precision, 'escala': escala, 'nulable': nulable}
            for t, c, tipo, largo, precision, escala, nulable in cursor.fetchall()}


def _compatible(origen: dict, destino: dict, parches: tuple[str, ...], tipo_destino: str | None) -> str | None:
    """None si es compatible; si no, el porqué."""
    tipo = origen['tipo']
    if tipo_destino == 'uuid':
        return None if destino['tipo'] == 'uuid' else f"se esperaba uuid y es {destino['tipo']}"
    if tipo in _TEXTO:
        if destino['tipo'] not in ('character varying', 'text'):
            return f"texto {tipo}({origen['largo']}) → {destino['tipo']}"
        if destino['largo'] is not None and destino['largo'] < origen['largo']:
            return f"más corto: {tipo}({origen['largo']}) → varchar({destino['largo']})"
    elif tipo == 'decimal':
        if destino['tipo'] != 'numeric' or (destino['precision'], destino['escala']) != (
                origen['precision'], origen['escala']):
            return (f"decimal({origen['precision']},{origen['escala']}) → {destino['tipo']}"
                    f"({destino['precision']},{destino['escala']})")
    elif tipo in _ENTEROS:
        esperado = tipo_destino or _ENTEROS[tipo]
        if destino['tipo'] != esperado:
            return f'{tipo} → {destino["tipo"]} (se esperaba {esperado})'
    elif tipo == 'bit':
        if destino['tipo'] != 'boolean':
            return f'bit → {destino["tipo"]}'
    elif tipo in _FECHAS:
        if destino['tipo'] != 'timestamp with time zone':
            return f'{tipo} → {destino["tipo"]} (el TO-BE guarda instantes)'
        if not {'T5_cdmx', 'T5_ny', 'T5_cdmx_llegada'} & set(parches):
            return f'{tipo} → timestamptz sin el parche T5 que dice de qué zona es la hora local'
    elif tipo == 'date':
        if destino['tipo'] != 'date':
            return f'date → {destino["tipo"]}'
    else:
        return f'tipo del legado sin regla: {tipo}'
    introduce_nulos = bool({'T3_texto', 'T3_numero'} & set(parches))
    if (origen['nulable'] or introduce_nulos) and not destino['nulable']:
        return 'el TO-BE no admite NULL y el legado (o un parche de centinela) sí'
    return None


def comparar(legado: dict[str, dict], tobe: dict[str, dict]) -> dict:
    filas, errores, avisos = [], [], []
    usadas = set()
    for columna_legado, origen in legado.items():
        tabla, columna = columna_legado.rsplit('.', 1)
        mapeo = MAPEO.get(tabla)
        c = mapeo.columnas.get(columna) if mapeo else None
        if c is None:
            errores.append(f'{columna_legado}: columna del legado sin lugar en el mapeo')
            filas.append({'legado': columna_legado, 'destino': None, 'estado': 'SIN MAPEO'})
            continue
        if c.destino is None:
            filas.append({'legado': columna_legado, 'destino': None, 'estado': 'no se migra',
                          'motivo': c.motivo or mapeo.motivo})
            continue
        destino = tobe.get(c.destino)
        if destino is None:
            errores.append(f'{columna_legado} → {c.destino}: FALTA en el TO-BE')
            filas.append({'legado': columna_legado, 'destino': c.destino, 'estado': 'FALTA'})
            continue
        usadas.add(c.destino)
        problema = _compatible(origen, destino, c.parches, c.tipo_destino)
        if problema:
            errores.append(f'{columna_legado} → {c.destino}: {problema}')
        elif not origen['nulable'] and destino['nulable'] and not {'T3_texto', 'T3_numero'} & set(c.parches):
            avisos.append(f'{columna_legado} → {c.destino}: el TO-BE admite NULL y el legado no')
        filas.append({'legado': columna_legado, 'destino': c.destino, 'estado': 'INCOMPATIBLE' if problema else 'ok',
                      'detalle': problema, 'parches': list(c.parches)})
    for tabla in MAPEO:
        if not any(f.startswith(tabla + '.') for f in legado):
            errores.append(f'{tabla}: la tabla del legado no está en el respaldo')
    sin_origen = []
    for columna_tobe in tobe:
        if columna_tobe in usadas or columna_tobe in NUEVAS:
            continue
        tabla = columna_tobe.rsplit('.', 1)[0]
        if f'{tabla}.*' in NUEVAS:
            continue
        sin_origen.append(columna_tobe)
        errores.append(f'{columna_tobe}: columna del TO-BE sin origen ni declaración')
    return {'columnas_legado': len(legado), 'columnas_tobe': len(tobe), 'filas': filas, 'errores': errores,
            'avisos': avisos, 'sin_origen': sin_origen, 'cumple': not errores}


def control_negativo_t6(legado: dict[str, dict], tobe: dict[str, dict]) -> dict:
    """La misma comparación contra un TO-BE que perdió `codigo_proposito`: debe FALLAR nombrándola."""
    sin_t6 = {k: v for k, v in tobe.items() if k != 'decant.orden_pago.codigo_proposito'}
    resultado = comparar(legado, sin_t6)
    caza = any('codigo_proposito' in e for e in resultado['errores'])
    return {'errores': resultado['errores'], 'caza_t6': caza}
