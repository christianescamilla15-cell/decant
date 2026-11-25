"""Inventario estructural de la base restaurada: tablas por FILAS, columnas, llaves, módulos, triggers y jobs.

El corte se MIDE aquí (MAX de cada identidad y de cada fecha); ningún valor viene escrito en el código.
"""
from __future__ import annotations

from radiografia.datos import FECHA, consultar
from radiografia.patrones import Modulo

TIPOS_MODULO = {'P': 'PROCEDIMIENTO', 'V': 'VISTA', 'TR': 'TRIGGER', 'FN': 'FUNCION', 'IF': 'FUNCION',
                'TF': 'FUNCION'}


def tablas(cursor) -> list[dict]:
    cursor.execute("""
        SELECT s.name, t.name, t.temporal_type_desc, t.is_memory_optimized
        FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
        WHERE t.is_ms_shipped = 0 ORDER BY s.name, t.name""")
    resultado = []
    for esquema, nombre, temporal, memoria in cursor.fetchall():
        filas = consultar(cursor, 'SELECT COUNT_BIG(*) FROM {t}', esquema, nombre)[0][0]
        resultado.append({'esquema': esquema, 'tabla': nombre, 'filas': filas, 'temporal': temporal,
                          'en_memoria': bool(memoria)})
    return resultado


def columnas(cursor, filas_por_tabla: dict[str, int]) -> list[dict]:
    cursor.execute("""
        SELECT s.name, t.name, c.name, ty.name, c.max_length, c.is_nullable, c.is_identity, c.is_computed,
               CASE WHEN EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.indexes i
                                 ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                                 WHERE i.is_primary_key = 1 AND ic.object_id = c.object_id
                                   AND ic.column_id = c.column_id) THEN 1 ELSE 0 END,
               CASE WHEN EXISTS (SELECT 1 FROM sys.foreign_key_columns f
                                 WHERE f.parent_object_id = c.object_id AND f.parent_column_id = c.column_id)
                    THEN 1 ELSE 0 END
        FROM sys.columns c
        JOIN sys.tables t ON t.object_id = c.object_id
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        JOIN sys.types ty ON ty.user_type_id = c.user_type_id
        WHERE t.is_ms_shipped = 0
        ORDER BY s.name, t.name, c.column_id""")
    resultado = []
    for esq, tab, col, tipo, largo, nulable, identidad, calculada, pk, fk in cursor.fetchall():
        resultado.append({'esquema': esq, 'tabla': tab, 'columna': col, 'tipo': tipo.lower(), 'largo': largo,
                          'nulable': bool(nulable), 'es_identidad': bool(identidad), 'es_calculada': bool(calculada),
                          'es_pk': bool(pk), 'es_fk': bool(fk),
                          'filas': filas_por_tabla.get(f'{esq}.{tab}'.lower(), 0)})
    return resultado


def llaves_foraneas(cursor) -> list[dict]:
    cursor.execute("""
        SELECT fk.name, sh.name, th.name, sp.name, tp.name
        FROM sys.foreign_keys fk
        JOIN sys.tables th ON th.object_id = fk.parent_object_id
        JOIN sys.schemas sh ON sh.schema_id = th.schema_id
        JOIN sys.tables tp ON tp.object_id = fk.referenced_object_id
        JOIN sys.schemas sp ON sp.schema_id = tp.schema_id
        ORDER BY sh.name, th.name, fk.name""")
    return [{'nombre': n, 'hija': f'{sh}.{th}'.lower(), 'padre': f'{sp}.{tp}'.lower()}
            for n, sh, th, sp, tp in cursor.fetchall()]


def llaves_unicas(cursor) -> dict[str, list[set[str]]]:
    """Llaves únicas REALES de cada tabla: PK e índices únicos sin filtro (columnas de llave, no las incluidas).
    Toda tabla de usuario aparece, aunque no tenga ninguna (lista vacía)."""
    cursor.execute("""
        SELECT s.name, t.name, i.index_id, c.name
        FROM sys.tables t
        JOIN sys.schemas s ON s.schema_id = t.schema_id
        LEFT JOIN sys.indexes i ON i.object_id = t.object_id AND i.is_unique = 1 AND i.has_filter = 0
        LEFT JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
                                       AND ic.is_included_column = 0
        LEFT JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE t.is_ms_shipped = 0""")
    llaves: dict[str, dict[int, set[str]]] = {}
    for esquema, tabla, indice, columna in cursor.fetchall():
        por_indice = llaves.setdefault(f'{esquema}.{tabla}'.lower(), {})
        if indice is not None and columna is not None:
            por_indice.setdefault(indice, set()).add(columna.lower())
    return {tabla: list(indices.values()) for tabla, indices in llaves.items()}


def modulos(cursor) -> list[Modulo]:
    cursor.execute("""
        SELECT s.name, o.name, o.type, m.definition
        FROM sys.sql_modules m
        JOIN sys.objects o ON o.object_id = m.object_id
        JOIN sys.schemas s ON s.schema_id = o.schema_id
        WHERE o.is_ms_shipped = 0
        ORDER BY o.type, s.name, o.name""")
    resultado = []
    for esquema, nombre, tipo, definicion in cursor.fetchall():
        tipo = tipo.strip()
        if tipo in TIPOS_MODULO and definicion:
            resultado.append(Modulo(f'{esquema}.{nombre}'.lower(), TIPOS_MODULO[tipo], definicion))
    return resultado


def triggers(cursor) -> list[dict]:
    cursor.execute("""
        SELECT s.name, tr.name, OBJECT_SCHEMA_NAME(tr.parent_id), OBJECT_NAME(tr.parent_id), tr.is_disabled
        FROM sys.triggers tr JOIN sys.objects o ON o.object_id = tr.object_id
        JOIN sys.schemas s ON s.schema_id = o.schema_id
        WHERE tr.parent_class = 1 ORDER BY 1, 2""")
    return [{'trigger': f'{s}.{n}'.lower(), 'tabla': f'{ps}.{pt}'.lower(), 'deshabilitado': bool(d)}
            for s, n, ps, pt, d in cursor.fetchall()]


def jobs(cursor, base_msdb: str | None, base: str) -> tuple[list[dict], list[Modulo]]:
    """Jobs de la copia restaurada de msdb cuyos pasos corren en la base analizada."""
    if not base_msdb:
        return [], []
    cursor.execute("""
        DECLARE @sql nvarchar(max) = N'
            SELECT j.name, j.enabled, s.step_id, s.step_name, s.subsystem, s.database_name, s.command,
                   sc.name, sc.freq_type, sc.freq_interval, sc.active_start_time, sc.enabled
            FROM ' + QUOTENAME(%s) + N'.dbo.sysjobs j
            JOIN ' + QUOTENAME(%s) + N'.dbo.sysjobsteps s ON s.job_id = j.job_id
            LEFT JOIN ' + QUOTENAME(%s) + N'.dbo.sysjobschedules js ON js.job_id = j.job_id
            LEFT JOIN ' + QUOTENAME(%s) + N'.dbo.sysschedules sc ON sc.schedule_id = js.schedule_id
            WHERE s.database_name = @base ORDER BY j.name, s.step_id';
        EXEC sp_executesql @sql, N'@base sysname', @base = %s""", (base_msdb,) * 4 + (base,))
    lista, pasos = [], []
    for nombre, activo, paso, nombre_paso, subsistema, base_paso, comando, horario, freq, intervalo, hora, \
            horario_activo in cursor.fetchall():
        lista.append({'job': nombre, 'habilitado': bool(activo), 'paso': paso, 'nombre_paso': nombre_paso,
                      'subsistema': subsistema, 'base': base_paso, 'comando': comando, 'horario': horario,
                      'frecuencia': freq, 'intervalo': intervalo,
                      'hora': f'{hora // 10000:02d}:{hora // 100 % 100:02d}' if hora is not None else None,
                      'horario_habilitado': None if horario_activo is None else bool(horario_activo)})
        if subsistema == 'TSQL' and comando:
            pasos.append(Modulo(f'job: {nombre} / {nombre_paso}', 'JOB', comando))
    return lista, pasos


def corte(cursor, columnas_: list[dict]) -> list[dict]:
    """MAX de cada identidad y MIN/MAX de cada fecha, por tabla: el corte se mide en la fuente."""
    resultado = []
    por_tabla: dict[tuple[str, str], list[dict]] = {}
    for c in columnas_:
        por_tabla.setdefault((c['esquema'], c['tabla']), []).append(c)
    for (esq, tab), cols in por_tabla.items():
        entrada = {'tabla': f'{esq}.{tab}'.lower(), 'identidad': None, 'fechas': {}}
        for c in cols:
            if c['es_identidad']:
                maximo, actual = consultar(
                    cursor, "SELECT MAX({c}), IDENT_CURRENT(N'{t}') FROM {t}", esq, tab, c['columna'])[0]
                entrada['identidad'] = {'columna': c['columna'], 'max': maximo,
                                        'ident_current': int(actual) if actual is not None else None}
            elif c['tipo'] in FECHA and c['filas']:
                minimo, maximo = consultar(cursor, 'SELECT MIN({c}), MAX({c}) FROM {t}', esq, tab, c['columna'])[0]
                entrada['fechas'][c['columna']] = {'min': _texto(minimo), 'max': _texto(maximo)}
        resultado.append(entrada)
    return resultado


def _texto(valor):
    return None if valor is None else str(valor)
