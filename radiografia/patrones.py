"""Detectores por PATRÓN sobre el código de la base (procedimientos, vistas, triggers, funciones y pasos de jobs).

Son genéricos: buscan formas de código, no nombres conocidos. Cada uno devuelve hallazgos con el objeto, la línea
y el fragmento, para que una persona decida si es un defecto real (el control sobre una base pública mide cuántos
son ruido).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from radiografia.tsql import (
    INICIO_SENTENCIA,
    RELOJ,
    Ficha,
    abre_de,
    apertura,
    cierre,
    fichas,
    fin_de_caso,
    fin_de_consulta,
    inicia_sentencia,
    inicio_de_caso,
    nombre_objeto,
    sentencia_actual,
)


@dataclass
class Modulo:
    nombre: str              # esquema.objeto (o «job: nombre / paso»)
    tipo: str                # PROCEDIMIENTO, VISTA, TRIGGER, FUNCION, JOB
    texto: str
    _fichas: list[Ficha] | None = field(default=None, repr=False)

    @property
    def fichas(self) -> list[Ficha]:
        if self._fichas is None:
            self._fichas = fichas(self.texto)
        return self._fichas

    def renglon(self, linea: int) -> str:
        renglones = self.texto.splitlines()
        return renglones[linea - 1].strip()[:180] if 0 < linea <= len(renglones) else ''


def _hallazgo(categoria: str, modulo: Modulo, linea: int, detalle: str, **extra) -> dict:
    return {'categoria': categoria, 'objeto': modulo.nombre, 'tipo_objeto': modulo.tipo, 'linea': linea,
            'detalle': detalle, 'fragmento': modulo.renglon(linea), **extra}


def normalizar(nombre: str, esquema: str = 'dbo') -> str:
    partes = [p for p in nombre.split('.') if p]
    if len(partes) == 1:
        partes = [esquema, partes[0]]
    return '.'.join(partes[-2:]).lower()


# ── 1. TOP sin ORDER BY ──────────────────────────────────────────────────────────────────────────────────────

def top_sin_order_by(m: Modulo) -> list[dict]:
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not f.es('TOP'):
            continue
        j = i - 1
        while j >= 0 and fs[j].es('DISTINCT', 'ALL'):
            j -= 1
        if j < 0:
            continue
        if fs[j].es('UPDATE', 'DELETE'):
            hallazgos.append(_hallazgo('top_sin_order_by', m, f.linea,
                                       f'{fs[j].mayus} TOP: modifica filas arbitrarias (no admite ORDER BY)'))
            continue
        if not fs[j].es('SELECT'):
            continue
        fin = fin_de_consulta(fs, j)
        ordenada = any(fs[k].es('ORDER') and fs[k + 1].es('BY') and fs[k].nivel == fs[j].nivel
                       for k in range(j, min(fin, len(fs) - 1)))
        if ordenada:
            contexto = _expresion_de_tabla(fs, j, m) if _top_cien_por_ciento(fs, i) else None
            if contexto:
                hallazgos.append(_hallazgo(
                    'top_sin_order_by', m, f.linea,
                    f'TOP 100 PERCENT con ORDER BY en una {contexto}: el optimizador descarta ese TOP y su ORDER BY, '
                    f'así que el orden que promete no existe; quien la lea sin ORDER BY recibe las filas en el orden '
                    f'que entregue el plan', forma='orden_que_no_ordena', contexto=contexto))
            continue
        abre = apertura(fs, j)
        if abre is not None and abre > 0 and fs[abre - 1].es('EXISTS'):
            continue        # dentro de EXISTS el orden no importa
        asigna = j + 2 < len(fs) and any(fs[k].tipo == 'variable' and fs[k + 1].texto == '='
                                         for k in range(i, min(fin - 1, i + 8)))
        detalle = ('SELECT TOP sin ORDER BY: devuelve las filas que el plan entregue primero'
                   + ('; asigna a variables (si el filtro no es único, el valor es arbitrario)' if asigna else ''))
        hallazgos.append(_hallazgo('top_sin_order_by', m, f.linea, detalle, asigna_variable=asigna))
    return hallazgos


def _top_cien_por_ciento(fs: list[Ficha], i_top: int) -> bool:
    """`TOP 100 PERCENT` o `TOP (100) PERCENT`."""
    k = i_top + 1
    entre_parentesis = k < len(fs) and fs[k].texto == '('
    if entre_parentesis:
        k += 1
    if not (k < len(fs) and fs[k].tipo == 'numero' and float(fs[k].texto) == 100):
        return False
    k += 1
    if entre_parentesis:
        if not (k < len(fs) and fs[k].texto == ')'):
            return False
        k += 1
    return k < len(fs) and fs[k].es('PERCENT')


def _expresion_de_tabla(fs: list[Ficha], j_select: int, m: Modulo) -> str | None:
    """¿Dónde está el SELECT, si es un lugar en el que su ORDER BY no ordena el resultado final? La definición de una
    vista, una tabla derivada (FROM/JOIN/APPLY ( … )), una CTE (AS ( … )) o el RETURN de una función en línea."""
    abre = apertura(fs, j_select)
    previa = fs[abre - 1] if abre is not None and abre > 0 else None
    if previa is not None and previa.es('EXISTS', 'IN'):
        return None                     # ahí el orden no importa
    if m.tipo == 'VISTA':
        return 'vista'
    if previa is not None and previa.es('FROM', 'JOIN', 'APPLY', 'AS'):
        return 'tabla derivada'
    retorno = previa if abre is not None else (fs[j_select - 1] if j_select else None)
    if m.tipo == 'FUNCION' and retorno is not None and retorno.es('RETURN'):
        return 'función en línea'
    return None


# ── 2. INNER JOIN a una tabla hija ───────────────────────────────────────────────────────────────────────────

def inner_join_hija(m: Modulo, padres_de: dict[str, set[str]]) -> list[dict]:
    """INNER JOIN de un padre a una tabla HIJA (la que tiene la llave foránea): descarta a los padres sin hijos."""
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not f.es('JOIN'):
            continue
        anterior = fs[i - 1] if i else None
        if anterior is not None and (anterior.es('LEFT', 'RIGHT', 'FULL', 'OUTER', 'CROSS')):
            continue
        hija, _sig = nombre_objeto(fs, i + 1)
        if hija is None:
            continue
        hija = normalizar(hija)
        if hija not in padres_de:
            continue
        previas = _tablas_previas(fs, i)
        for padre in previas:
            # una llave foránea a sí misma (cliente → cliente que paga) no dice qué lado es el hijo: se omite
            if padre in padres_de[hija] and padre != hija:
                hallazgos.append(_hallazgo(
                    'inner_join_hija', m, f.linea,
                    f'INNER JOIN de {padre} a su tabla hija {hija}: descarta los registros de {padre} sin {hija}',
                    padre=padre, hija=hija))
                break
    return hallazgos


def _tablas_previas(fs: list[Ficha], i: int) -> list[str]:
    """Tablas del FROM y de los JOIN anteriores a la ficha i, en su mismo nivel."""
    nivel = fs[i].nivel
    tablas = []
    for j in range(i - 1, -1, -1):
        f = fs[j]
        if f.nivel < nivel:
            break
        if f.nivel != nivel:
            continue
        if f.es('JOIN', 'FROM'):
            nombre, _ = nombre_objeto(fs, j + 1)
            if nombre:
                tablas.append(normalizar(nombre))
            if f.es('FROM'):
                break
        elif inicia_sentencia(fs, j) and f.mayus != 'SELECT':
            break
    return tablas


# ── 3. Reloj del servidor dentro de una regla ────────────────────────────────────────────────────────────────

_REGLA = frozenset(('WHERE', 'ON', 'HAVING', 'IF', 'WHILE', 'WHEN', 'AND', 'OR'))
_ASIGNACION = frozenset(('SET', 'SELECT', 'VALUES', 'THEN', 'ELSE', 'DECLARE', 'RETURN', 'BY', 'DEFAULT'))


def reloj_en_regla(m: Modulo) -> list[dict]:
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not (f.tipo == 'ident' and f.mayus in RELOJ):
            continue
        if f.mayus != 'CURRENT_TIMESTAMP' and not (i + 1 < len(fs) and fs[i + 1].texto == '('):
            continue
        if _contexto_reloj(fs, i) == 'regla':
            hallazgos.append(_hallazgo('reloj_en_regla', m, f.linea,
                                       f'{f.mayus}() decide un resultado: reprocesar otro día da otra respuesta'))
    return hallazgos


def _contexto_reloj(fs: list[Ficha], i: int) -> str:
    palabra, _k = _palabra_de_contexto(fs, i)
    return 'regla' if palabra in _REGLA else 'asignacion'


def _palabra_de_contexto(fs: list[Ficha], i: int) -> tuple[str, int]:
    """La cláusula que gobierna la ficha i (WHERE, ON, WHEN, SET…) y su posición; ',' si es un elemento de lista."""
    # salir de las funciones que lo envuelven: DATEADD(day, -3, GETDATE()) cuenta donde está DATEADD
    while True:
        abre = apertura(fs, i)
        if abre is None or abre == 0 or fs[abre - 1].tipo != 'ident' or fs[abre - 1].mayus in (
                'VALUES', 'IN', 'EXISTS', 'AND', 'OR', 'WHERE', 'ON', 'IF', 'WHEN', 'THEN', 'ELSE', 'SELECT', 'SET'):
            break
        i = abre - 1
    profundidad = 0
    for j in range(i - 1, -1, -1):
        f = fs[j]
        if f.tipo == 'op' and f.texto == ')':
            profundidad += 1
            continue
        if f.tipo == 'op' and f.texto == '(':
            if profundidad:
                profundidad -= 1
            continue
        if profundidad:
            continue
        if f.tipo == 'op' and f.texto == ',':
            return ',', j
        if f.tipo != 'ident':
            continue
        if f.mayus in _REGLA or f.mayus in _ASIGNACION:
            return f.mayus, j
    return '', -1


# ── 3b. Reloj que entra a la regla por una variable ──────────────────────────────────────────────────────────

def _es_reloj(fs: list[Ficha], k: int) -> bool:
    f = fs[k]
    return f.tipo == 'ident' and f.mayus in RELOJ and (
        f.mayus == 'CURRENT_TIMESTAMP' or (k + 1 < len(fs) and fs[k + 1].texto == '('))


def _asignaciones_a_variables(fs: list[Ficha]) -> list[tuple[str, list[int]]]:
    """(variable, índices de su expresión) de cada `SET @v =`, `DECLARE @v tipo =` y `SELECT @v =` del módulo."""
    resultado = []
    for i, f in enumerate(fs):
        if f.es('SET') and i + 2 < len(fs) and fs[i + 1].tipo == 'variable' and fs[i + 2].texto in ('=', '+=', '-='):
            # dentro del SET de un UPDATE (`SET @n = siguiente, siguiente = …`) la expresión acaba en la coma
            fin = fin_de_sentencia(fs, i)
            hasta = next((x for x in range(i + 3, fin) if fs[x].nivel == f.nivel and (
                fs[x].texto == ',' or fs[x].es('FROM', 'WHERE', 'OUTPUT'))), fin)
            resultado.append((fs[i + 1].mayus, list(range(i + 3, hasta))))
            continue
        if not f.es('DECLARE', 'SELECT'):
            continue
        fin = fin_de_sentencia(fs, i) if f.es('DECLARE') else fin_de_consulta(fs, i)
        k = i + 1
        while k < fin:
            if fs[k].tipo == 'variable' and fs[k].nivel == f.nivel and (k == i + 1 or fs[k - 1].texto == ','):
                igual = next((x for x in range(k + 1, fin) if fs[x].nivel == f.nivel and (
                    fs[x].texto in ('=', ',') or fs[x].es('FROM'))), None)
                if igual is not None and fs[igual].texto == '=':
                    hasta = next((x for x in range(igual + 1, fin) if fs[x].nivel == f.nivel and (
                        fs[x].texto == ',' or fs[x].es('FROM', 'WHERE'))), fin)
                    resultado.append((fs[k].mayus, list(range(igual + 1, hasta))))
                    k = hasta
                    continue
            k += 1
    return resultado


def variables_de_reloj(m: Modulo) -> dict[str, str]:
    """Variables del módulo que llevan el reloj del servidor: asignadas desde GETDATE() y similares, o desde otra
    variable que ya lo lleva (DATEADD, DATEDIFF, CAST…). Devuelve {variable: de dónde le llega}."""
    fs = m.fichas
    asignaciones = _asignaciones_a_variables(fs)
    llevan: dict[str, str] = {}
    cambio = True
    while cambio:
        cambio = False
        for variable, expresion in asignaciones:
            if variable in llevan:
                continue
            reloj = next((f'{fs[k].mayus}()' for k in expresion if _es_reloj(fs, k)), None)
            fuente = reloj or next((fs[k].texto for k in expresion
                                    if fs[k].tipo == 'variable' and fs[k].mayus in llevan), None)
            if fuente:
                llevan[variable] = fuente
                cambio = True
    return llevan


def reloj_por_variable(m: Modulo) -> list[dict]:
    """El reloj no aparece en la regla: entra por una variable (`SET @hoy = GETDATE(); … WHERE f < @hoy`)."""
    llevan = variables_de_reloj(m)
    if not llevan:
        return []
    fs, hallazgos, vistos = m.fichas, [], set()
    for i, f in enumerate(fs):
        if f.tipo != 'variable' or f.mayus not in llevan or (f.linea, f.mayus) in vistos:
            continue
        if i and i + 1 < len(fs) and fs[i + 1].texto in ('=', '+=', '-=') and (
                fs[i - 1].es('SET', 'DECLARE', 'SELECT') or fs[i - 1].texto == ','):
            continue                    # es el destino de una asignación, no un uso
        palabra, k = _palabra_de_contexto(fs, i)
        if palabra in _REGLA:
            efecto = 'decide un resultado'
        elif palabra == 'SET' and sentencia_actual(fs, k) == 'UPDATE':
            efecto = 'se escribe en los datos (SET de un UPDATE)'
        else:
            continue
        vistos.add((f.linea, f.mayus))
        hallazgos.append(_hallazgo('reloj_en_regla', m, f.linea,
                                   f'el reloj del servidor entra por la variable {f.texto} (viene de '
                                   f'{llevan[f.mayus]}) y {efecto}: reprocesar otro día da otra respuesta',
                                   forma='por_variable'))
    return hallazgos


# ── 1b. Asignación desde varias filas (selección no determinista sin TOP) ────────────────────────────────────

_AGREGADOS = frozenset(('MAX', 'MIN', 'SUM', 'COUNT', 'COUNT_BIG', 'AVG', 'STRING_AGG', 'STDEV', 'STDEVP', 'VAR',
                        'VARP', 'CHECKSUM_AGG', 'GROUPING', 'APPROX_COUNT_DISTINCT'))


def asignacion_multifila(m: Modulo, unicas: dict[str, list[set[str]]], columnas: dict[str, set[str]]) -> list[dict]:
    """`SELECT @v = col FROM …` sin TOP ni agregado cuyo CONJUNTO puede traer varias filas: la variable se queda con
    la ÚLTIMA fila que entregue el plan. Es la misma clase que TOP sin ORDER BY (selección no determinista) en otra
    forma.

    El conjunto trae una sola fila si cada tabla queda fijada por una llave ÚNICA real suya (PK o índice único sin
    filtro, leídos del esquema restaurado), igualada con AND en el WHERE o en su ON a constantes, variables o columnas
    de tablas ya fijadas. Una tabla unida por el lado N de una llave foránea no queda fijada aunque el WHERE cubra la
    PK de la tabla del FROM. Sólo se reporta si alguna variable toma una columna de una tabla que no quedó fijada (si
    toma sólo de tablas fijadas, todas las filas le dan el mismo valor). Vistas, tablas derivadas, funciones,
    variables de tabla y temporales no tienen metadatos: no se juzgan y no le quitan la fijación a nadie.
    """
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not (f.es('SELECT') and i + 2 < len(fs) and fs[i + 1].tipo == 'variable' and fs[i + 2].texto == '='):
            continue
        fin = fin_de_consulta(fs, i)
        nivel = f.nivel
        desde = next((k for k in range(i, fin) if fs[k].nivel == nivel and fs[k].es('FROM')), None)
        if desde is None:
            continue
        agrupada = any(fs[k].nivel == nivel and fs[k].es('GROUP') for k in range(desde, fin))
        agregada = not agrupada and any(
            fs[k].tipo == 'ident' and fs[k].mayus in _AGREGADOS and fs[k + 1].texto == '('
            and not _seguido_de_over(fs, k + 1) for k in range(i, desde - 1))
        if agregada:
            continue
        fin_from = _fin_del_from(fs, desde, fin)
        fuentes_ = fuentes(fs, desde, fin_from)
        if not any(x['nombre'] in unicas for x in fuentes_):
            continue                    # nada con metadatos: no se puede decidir
        donde = fin_from if fin_from < fin and fs[fin_from].es('WHERE') else None
        condicion_donde: list | None = []
        if donde is not None:
            fin_donde = next((k for k in range(donde + 1, fin) if fs[k].nivel == nivel and fs[k].tipo == 'ident'
                              and fs[k].mayus in _FIN_DEL_FROM), fin)
            condicion_donde = _igualdades(fs, donde + 1, fin_donde, fuentes_, columnas)
        igualdades = list(condicion_donde or [])
        for x in fuentes_:
            if x['on']:
                igualdades += _igualdades(fs, *x['on'], fuentes_, columnas) or []
        fijadas = _fijadas(fuentes_, igualdades, unicas)
        asignadas = _asignadas(fs, i, desde)
        toman = {k for _v, a, b in asignadas for k in _dependencias(fs, a, b, fuentes_, columnas)}
        sueltas = [k for k in range(len(fuentes_)) if k not in fijadas and k in toman]
        if not sueltas:
            continue
        razones = []
        for k in sueltas:
            x = fuentes_[k]
            iguala = sorted({c for fuente, c, deps in igualdades if fuente == k and deps is not None
                             and k not in deps and deps <= fijadas})
            llaves = '; '.join(', '.join(sorted(llave)) for llave in unicas[x['nombre']]) or 'ninguna'
            iguala_txt = f"iguala {', '.join(iguala)}" if iguala else 'no iguala ninguna columna'
            if x['union'] in ('FROM', ','):
                filtro = ('sin WHERE' if donde is None else 'el WHERE tiene OR' if condicion_donde is None
                          else f'el filtro {iguala_txt}')
                razones.append(f"{x['nombre']}: {filtro} (llaves únicas: {llaves})")
            else:
                alias = f" ({x['alias']})" if x['alias'] else ''
                union = 'APPLY' if x['union'] == 'APPLY' else f"{x['union']} JOIN"
                razones.append(f"{x['nombre']}{alias} entra por un {union} que {iguala_txt}, sin cubrir ninguna "
                               f"llave única suya ({llaves})")
        variables = [v for v, a, b in asignadas if _dependencias(fs, a, b, fuentes_, columnas) & set(sueltas)]
        hallazgos.append(_hallazgo(
            'top_sin_order_by', m, f.linea,
            f"asigna {', '.join(variables)} sin TOP ni agregado desde un conjunto que puede traer varias filas: "
            f"{'; '.join(razones)}. La variable se queda con la última fila que entregue el plan",
            asigna_variable=True, forma='asignacion_multifila',
            tablas_sin_fijar=[fuentes_[k]['nombre'] for k in sueltas]))
    return hallazgos


def _seguido_de_over(fs: list[Ficha], abre: int) -> bool:
    k = cierre(fs, abre) + 1
    return k < len(fs) and fs[k].es('OVER')


def _asignadas(fs: list[Ficha], i: int, desde: int) -> list[tuple[str, int, int]]:
    """(variable, inicio, fin) de cada `@v = expresión` de la lista del SELECT que empieza en i."""
    nivel, resultado, k = fs[i].nivel, [], i + 1
    while k < desde:
        if fs[k].tipo == 'variable' and fs[k].nivel == nivel and k + 1 < desde and fs[k + 1].texto in (
                '=', '+=', '-=', '*=', '/='):
            fin = next((x for x in range(k + 2, desde) if fs[x].nivel == nivel and fs[x].texto == ','), desde)
            resultado.append((fs[k].texto, k + 2, fin))
            k = fin + 1
        else:
            k += 1
    return resultado


def _fijadas(fuentes_: list[dict], igualdades: list[tuple[int, str, frozenset[int] | None]],
             unicas: dict[str, list[set[str]]]) -> set[int]:
    """Fuentes que quedan en UNA fila: una llave única suya igualada a algo que ya está fijo. Lo que no tiene
    metadatos cuenta como fijo (no se puede juzgar y no se le quita la fijación a nadie)."""
    fijadas = {k for k, x in enumerate(fuentes_) if x['nombre'] not in unicas}
    cambio = True
    while cambio:
        cambio = False
        for k, x in enumerate(fuentes_):
            if k in fijadas:
                continue
            iguales = {c for fuente, c, deps in igualdades
                       if fuente == k and deps is not None and k not in deps and deps <= fijadas}
            if any(llave <= iguales for llave in unicas[x['nombre']]):
                fijadas.add(k)
                cambio = True
    return fijadas


# ── Fuentes de un FROM, columnas y condiciones (compartido por la asignación y la división entera) ──────────

_UNIONES = frozenset(('INNER', 'LEFT', 'RIGHT', 'FULL', 'OUTER', 'CROSS', 'JOIN', 'APPLY'))
_FIN_DEL_FROM = frozenset(('WHERE', 'GROUP', 'ORDER', 'HAVING', 'UNION', 'EXCEPT', 'INTERSECT', 'OPTION', 'FOR',
                           'WINDOW'))
_NO_ES_ALIAS = _UNIONES | _FIN_DEL_FROM | INICIO_SENTENCIA | frozenset((
    'ON', 'PIVOT', 'UNPIVOT', 'TABLESAMPLE', 'AS', 'OUTPUT', 'LOOP', 'HASH', 'REMOTE'))


def _es_union(fs: list[Ficha], k: int) -> bool:
    """INNER, LEFT, JOIN, APPLY… como palabra de unión (no la función LEFT( ) ni RIGHT( ))."""
    return fs[k].tipo == 'ident' and fs[k].mayus in _UNIONES and not (k + 1 < len(fs) and fs[k + 1].texto == '(')


def _fin_del_from(fs: list[Ficha], desde: int, fin: int) -> int:
    nivel = fs[desde].nivel
    return next((k for k in range(desde + 1, fin) if fs[k].nivel == nivel and fs[k].tipo == 'ident'
                 and fs[k].mayus in _FIN_DEL_FROM and not _es_tiempo_del_sistema(fs, k)), fin)


def _es_tiempo_del_sistema(fs: list[Ficha], k: int) -> bool:
    """`FOR SYSTEM_TIME …` de una tabla temporal (no es el FOR XML/JSON que cierra el FROM)."""
    return fs[k].es('FOR') and k + 1 < len(fs) and fs[k + 1].es('SYSTEM_TIME')


def _saltar_tiempo_del_sistema(fs: list[Ficha], k: int, fin: int) -> int:
    """Siguiente ficha después de `FOR SYSTEM_TIME AS OF e | FROM e TO e | BETWEEN e AND e | CONTAINED IN (…) | ALL`."""
    k += 2
    if k < fin and fs[k].es('ALL'):
        return k + 1
    if k + 1 < fin and fs[k].es('CONTAINED') and fs[k + 1].es('IN'):
        return cierre(fs, k + 2) + 1 if k + 2 < fin and fs[k + 2].texto == '(' else k + 2
    if k + 1 < fin and fs[k].es('AS') and fs[k + 1].es('OF'):
        return _primaria(fs, k + 2, fin) or k + 2
    if k < fin and fs[k].es('FROM', 'BETWEEN'):
        primera = _primaria(fs, k + 1, fin) or k + 1
        return (_primaria(fs, primera + 1, fin) or primera + 1) if primera < fin else primera
    return k


def fuentes(fs: list[Ficha], desde: int, fin: int) -> list[dict]:
    """Fuentes del FROM que empieza en la ficha `desde`, hasta `fin` (exclusivo), en su nivel.

    Cada una: {'nombre': 'esquema.tabla' (None si es tabla derivada, función, variable de tabla o temporal), 'alias',
    'union' (FROM, INNER, LEFT, RIGHT, FULL, CROSS, APPLY o ','), 'on': (inicio, fin) de su condición o None}.
    """
    nivel, resultado = fs[desde].nivel, []
    k, union = desde + 1, 'FROM'
    while k < fin:
        f, nombre = fs[k], None
        if f.texto == '(':
            k = cierre(fs, k) + 1
        elif f.tipo == 'variable':
            k += 1
        elif f.tipo == 'ident' and f.mayus not in _NO_ES_ALIAS:
            crudo, k = nombre_objeto(fs, k)
            if k < fin and fs[k].texto == '(':
                k = cierre(fs, k) + 1               # función con valores de tabla
            elif crudo and not crudo.startswith('#'):
                nombre = normalizar(crudo)
            if k < fin and _es_tiempo_del_sistema(fs, k):
                k = _saltar_tiempo_del_sistema(fs, k, fin)
        else:
            break
        alias = None
        if k < fin and fs[k].es('AS'):
            k += 1
        if k < fin and fs[k].tipo == 'ident' and fs[k].nivel == nivel and fs[k].mayus not in _NO_ES_ALIAS:
            alias = fs[k].texto.lower()
            k += 1
            if k < fin and fs[k].texto == '(' and nombre is None:
                k = cierre(fs, k) + 1               # columnas de una tabla derivada: d (a, b)
        if k + 1 < fin and fs[k].es('WITH') and fs[k + 1].texto == '(':
            k = cierre(fs, k + 1) + 1               # sugerencias de tabla
        on = None
        if k < fin and fs[k].es('ON'):
            inicio = k = k + 1
            while k < fin and not (fs[k].nivel == nivel and (_es_union(fs, k) or fs[k].texto == ',')):
                k += 1
            on = (inicio, k)
        resultado.append({'nombre': nombre, 'alias': alias, 'union': union, 'on': on})
        if k >= fin:
            break
        if fs[k].texto == ',' and fs[k].nivel == nivel:
            union, k = ',', k + 1
            continue
        palabras = []
        while k < fin and _es_union(fs, k) and not fs[k].es('JOIN', 'APPLY'):
            palabras.append(fs[k].mayus)
            k += 1
        while k < fin and fs[k].es('LOOP', 'HASH', 'MERGE', 'REMOTE'):
            k += 1                                  # sugerencias de unión
        if k < fin and fs[k].es('JOIN', 'APPLY'):
            union = 'APPLY' if fs[k].es('APPLY') else (palabras[0] if palabras else 'INNER')
            k += 1
            continue
        break
    return resultado


def _columna_en(fs: list[Ficha], j: int) -> tuple[str | None, str, int] | None:
    """Referencia a columna que empieza en j (`col`, `t.col`, `e.t.col`): (calificador, columna, siguiente ficha).
    None si no es un identificador o si es una función."""
    if fs[j].tipo != 'ident':
        return None
    partes, k = [fs[j].texto], j + 1
    while k + 1 < len(fs) and fs[k].texto == '.' and fs[k + 1].tipo == 'ident':
        partes.append(fs[k + 1].texto)
        k += 2
    if k < len(fs) and fs[k].texto == '(':
        return None
    return ('.'.join(partes[:-1]) or None), partes[-1].lower(), k


def _resolver(fuentes_: list[dict], calificador: str | None, columna: str,
              columnas: dict[str, set[str]]) -> int | None:
    """Fuente de una columna: por su calificador (alias, o el nombre de la tabla si no tiene alias) o, sin
    calificador, la única tabla con metadatos que tiene esa columna. None si no se puede saber."""
    if calificador:
        q = calificador.lower()
        candidatas = [k for k, x in enumerate(fuentes_) if x['alias'] == q or (
            x['alias'] is None and x['nombre'] is not None
            and (x['nombre'] == normalizar(q) if '.' in q else x['nombre'].split('.')[-1] == q))]
    else:
        candidatas = [k for k, x in enumerate(fuentes_) if columna in columnas.get(x['nombre'] or '', ())]
    return candidatas[0] if len(candidatas) == 1 else None


def _en_subconsulta(fs: list[Ficha], j: int, base: int) -> bool:
    """¿La ficha j está dentro de una subconsulta (un paréntesis que abre con SELECT) más honda que `base`?"""
    while fs[j].nivel > base:
        abre = apertura(fs, j)
        if abre is None:
            return False
        if abre + 1 < len(fs) and fs[abre + 1].es('SELECT'):
            return True
        j = abre
    return False


def _dependencias(fs: list[Ficha], a: int, b: int, fuentes_: list[dict],
                  columnas: dict[str, set[str]]) -> frozenset[int]:
    """Fuentes de este FROM cuyas columnas aparecen en la expresión [a, b), fuera de subconsultas. Variables,
    literales y lo que no se puede resolver no cuentan."""
    base, deps, j = fs[a].nivel if a < b else 0, set(), a
    while j < b:
        if fs[j].tipo == 'ident' and not (j and fs[j - 1].texto == '.') and not _en_subconsulta(fs, j, base):
            ref = _columna_en(fs, j)
            if ref is not None:
                fuente = _resolver(fuentes_, ref[0], ref[1], columnas)
                if fuente is not None:
                    deps.add(fuente)
                j = max(ref[2], j + 1)
                continue
        j += 1
    return frozenset(deps)


_CORTE_DE_TERMINO = frozenset(('AND', 'OR', 'NOT', 'ON', 'WHERE', 'WHEN', 'THEN', 'ELSE', 'HAVING', 'BETWEEN',
                               'LIKE', 'IS', 'IN'))


def _agrupa(fs: list[Ficha], abre: int) -> bool:
    """¿El '(' sólo agrupa condiciones (no es función, subconsulta, lista de IN ni un NOT ( … ))?"""
    previa = fs[abre - 1] if abre > 0 else None
    siguiente = fs[abre + 1] if abre + 1 < len(fs) else None
    return (previa is None or previa.texto == '(' or previa.es('AND', 'OR', 'WHERE', 'ON', 'HAVING')) and not (
        siguiente is not None and siguiente.es('SELECT'))


def _en_la_condicion(fs: list[Ficha], k: int, base: int) -> bool:
    """¿La ficha k pertenece a la condición (nivel `base`), fuera de CASE, funciones y subconsultas?"""
    if fs[k].en_caso:
        return False
    j = k
    while fs[j].nivel > base:
        abre = apertura(fs, j)
        if abre is None or not _agrupa(fs, abre):
            return False
        j = abre
    return True


def _igualdades(fs: list[Ficha], a: int, b: int, fuentes_: list[dict],
                columnas: dict[str, set[str]]) -> list[tuple[int, str, frozenset[int]]] | None:
    """Igualdades `columna = expresión` de la condición [a, b) que se suman con AND: (fuente, columna, fuentes de
    las que depende el otro lado). None si la condición tiene un OR: entonces no garantiza nada."""
    if a >= b:
        return []
    base, resultado = fs[a - 1].nivel if a else fs[a].nivel, []
    for k in range(a, b):
        if not _en_la_condicion(fs, k, base):
            continue
        if fs[k].es('OR'):
            return None
        if not (fs[k].tipo == 'op' and fs[k].texto == '='):
            continue
        nivel = fs[k].nivel
        x = k - 1
        while x >= a and fs[x].nivel >= nivel and not (fs[x].nivel == nivel and (
                fs[x].tipo == 'ident' and fs[x].mayus in _CORTE_DE_TERMINO)):
            x -= 1
        y = k + 1
        while y < b and fs[y].nivel >= nivel and not (fs[y].nivel == nivel and (
                (fs[y].tipo == 'ident' and fs[y].mayus in _CORTE_DE_TERMINO) or fs[y].texto == ')')):
            y += 1
        for (ini, fin), (otro_ini, otro_fin) in (((x + 1, k), (k + 1, y)), ((k + 1, y), (x + 1, k))):
            ref = _columna_en(fs, ini) if ini < fin else None
            if ref is None or ref[2] != fin:
                continue
            fuente = _resolver(fuentes_, ref[0], ref[1], columnas)
            if fuente is not None:
                resultado.append((fuente, ref[1], _dependencias(fs, otro_ini, otro_fin, fuentes_, columnas)))
    return resultado


# ── 4. IF EXISTS sin ELSE ────────────────────────────────────────────────────────────────────────────────────

def if_exists_sin_else(m: Modulo) -> list[dict]:
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not f.es('IF'):
            continue
        j = i + 1
        negado = j < len(fs) and fs[j].es('NOT')
        if negado:
            j += 1
        if j + 1 >= len(fs) or not fs[j].es('EXISTS') or fs[j + 1].texto != '(':
            continue
        cuerpo = _inicio_cuerpo(fs, i, cierre(fs, j + 1) + 1)
        if cuerpo is None:
            continue
        fin = _fin_de_bloque(fs, cuerpo)
        if fin < len(fs) and fs[fin].es('ELSE'):
            continue
        tipo = _tipo_de_cuerpo(fs[cuerpo:fin])
        condicion = f'IF {"NOT " if negado else ""}EXISTS'
        if tipo == 'DML':
            hallazgos.append(_hallazgo(
                'if_exists_sin_else', m, f.linea,
                f'{condicion} sin ELSE que escribe datos: cuando la condición no se cumple no pasa nada y nadie se '
                f'entera (camino silencioso)', cuerpo=tipo))
        else:
            # guarda (RETURN/THROW) o configuración idempotente (DDL): el camino no tomado no pierde datos
            hallazgos.append(_hallazgo('if_exists_guarda', m, f.linea,
                                       f'{condicion} sin ELSE con cuerpo {tipo}: guarda o configuración idempotente',
                                       cuerpo=tipo))
    return hallazgos


def _tipo_de_cuerpo(cuerpo: list[Ficha]) -> str:
    if any(f.es('INSERT', 'UPDATE', 'DELETE', 'MERGE') for f in cuerpo):
        return 'DML'
    if any(f.es('CREATE', 'ALTER', 'DROP', 'GRANT', 'DENY', 'REVOKE', 'EXEC', 'EXECUTE') for f in cuerpo):
        return 'DDL/EXEC'
    return 'guarda'



def _inicio_cuerpo(fs: list[Ficha], i_if: int, desde: int) -> int | None:
    nivel = fs[i_if].nivel
    for k in range(desde, len(fs)):
        if fs[k].nivel == nivel and inicia_sentencia(fs, k):
            return k
    return None


def _fin_de_bloque(fs: list[Ficha], i: int) -> int:
    """Índice de la ficha que sigue al cuerpo que empieza en i (BEGIN…END, otro IF o una sentencia)."""
    if fs[i].es('BEGIN') and not (i + 1 < len(fs) and fs[i + 1].es('TRAN', 'TRANSACTION', 'DISTRIBUTED')):
        abiertos = 0
        for k in range(i, len(fs)):
            if fs[k].es('BEGIN') and not (k + 1 < len(fs) and fs[k + 1].es('TRAN', 'TRANSACTION', 'DISTRIBUTED')):
                abiertos += 1
            elif fs[k].es('CASE'):
                abiertos += 1
            elif fs[k].es('END'):
                abiertos -= 1
                if abiertos == 0:
                    siguiente = k + 1
                    if siguiente < len(fs) and fs[siguiente].es('TRY', 'CATCH'):
                        siguiente += 1
                    if siguiente < len(fs) and fs[siguiente].texto == ';':
                        siguiente += 1
                    return siguiente
        return len(fs)
    if fs[i].es('IF'):
        abre = i + 1
        cuerpo = _inicio_cuerpo(fs, i, abre)
        if cuerpo is None:
            return len(fs)
        fin = _fin_de_bloque(fs, cuerpo)
        if fin < len(fs) and fs[fin].es('ELSE'):
            return _fin_de_bloque(fs, fin + 1)
        return fin
    return fin_de_sentencia(fs, i)


def fin_de_sentencia(fs: list[Ficha], i: int) -> int:
    nivel, primera = fs[i].nivel, fs[i].mayus
    continuaciones = 1 if primera == 'WITH' else 0
    for j in range(i + 1, len(fs)):
        f = fs[j]
        if f.nivel < nivel:
            return j
        if f.nivel != nivel:
            continue
        if f.tipo == 'op' and f.texto == ';':
            return j + 1
        if inicia_sentencia(fs, j):
            if f.mayus == 'SELECT' and (primera == 'INSERT' or fs[j - 1].es('UNION', 'ALL', 'EXCEPT', 'INTERSECT')):
                continue
            if f.mayus in ('EXEC', 'EXECUTE') and primera == 'INSERT':
                continue
            if f.mayus == 'SET' and primera == 'UPDATE':
                continue
            if continuaciones and f.mayus in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE'):
                continuaciones -= 1
                primera = f.mayus
                continue
            return j
    return len(fs)


# ── 5. Literales mágicos ─────────────────────────────────────────────────────────────────────────────────────

_TIPOS_CON_LARGO = frozenset(('VARCHAR', 'NVARCHAR', 'CHAR', 'NCHAR', 'VARBINARY', 'BINARY', 'DECIMAL', 'NUMERIC',
                              'FLOAT', 'DATETIME2', 'TIME', 'DATETIMEOFFSET'))


def literales(m: Modulo) -> list[dict]:
    """Números (≠ 0 y 1) y códigos de texto comparados en duro: reglas de negocio escondidas en el código."""
    fs = m.fichas
    vistos: dict[tuple[str, str], list[int]] = {}
    inicio = _inicio_cuerpo_modulo(fs)
    for i in range(inicio, len(fs)):
        f = fs[i]
        if f.tipo == 'numero':
            valor = f.texto
            if valor.rstrip('0').rstrip('.') in ('0', '1', '') or _es_largo_de_tipo(fs, i):
                continue
            if i and fs[i - 1].texto == '-' and (i < 2 or fs[i - 2].tipo == 'op' or fs[i - 2].es(*_REGLA)):
                valor = '-' + valor
            vistos.setdefault(('número', valor), []).append(f.linea)
        elif f.tipo == 'cadena' and i:
            previa = fs[i - 1]
            comparada = (previa.tipo == 'op' and previa.texto in ('=', '<>', '!=', '<', '>', '<=', '>=')
                         and not _es_asignacion(fs, i - 1)) or previa.es('WHEN')
            en_lista = previa.texto in ('(', ',') and _dentro_de_in(fs, i)
            if (comparada or en_lista) and f.texto not in ("''", "N''"):
                vistos.setdefault(('código', f.texto), []).append(f.linea)
    return [_hallazgo('literal_magico', m, lineas[0], f'{clase} en duro {valor} ({len(lineas)} vez/veces)',
                      clase=clase, valor=valor, lineas=lineas)
            for (clase, valor), lineas in vistos.items()]


def _es_largo_de_tipo(fs: list[Ficha], i: int) -> bool:
    k = i - 1
    while k >= 0 and (fs[k].texto == ',' or fs[k].tipo == 'numero'):
        k -= 1
    return k >= 1 and fs[k].texto == '(' and fs[k - 1].tipo == 'ident' and fs[k - 1].mayus in _TIPOS_CON_LARGO


def _es_asignacion(fs: list[Ficha], i_igual: int) -> bool:
    """¿El `=` es una asignación (SET x = 'A', @v = 'A') y no una comparación?"""
    k = i_igual - 1
    if k >= 0 and fs[k].tipo == 'variable':
        return not any(fs[j].es(*_REGLA) for j in range(max(k - 1, 0), k))
    while k >= 0 and (fs[k].tipo == 'ident' or fs[k].texto == '.'):
        k -= 1
    return k >= 0 and (fs[k].es('SET') or fs[k].texto == ',') and _sentencia_con_set(fs, k)


def _sentencia_con_set(fs: list[Ficha], k: int) -> bool:
    for j in range(k, -1, -1):
        if fs[j].nivel == fs[k].nivel and fs[j].es('SET', 'UPDATE'):
            return True
        if fs[j].nivel == fs[k].nivel and fs[j].es('WHERE', 'SELECT', 'IF', 'WHEN', 'ON'):
            return False
    return False


def _dentro_de_in(fs: list[Ficha], i: int) -> bool:
    abre = apertura(fs, i)
    return abre is not None and abre > 0 and fs[abre - 1].es('IN')


def _inicio_cuerpo_modulo(fs: list[Ficha]) -> int:
    """Salta el encabezado CREATE … AS (parámetros y sus valores por omisión)."""
    if not fs or not fs[0].es('CREATE', 'ALTER'):
        return 0
    for i, f in enumerate(fs):
        if f.es('AS') and f.nivel == 0:
            return i + 1
    return 0


# ── 6. Desfase horario fijo ──────────────────────────────────────────────────────────────────────────────────

def desfase_horario_fijo(m: Modulo) -> list[dict]:
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not (f.es('DATEADD') and i + 3 < len(fs) and fs[i + 1].texto == '('):
            continue
        if not fs[i + 2].es('HOUR', 'HH'):
            continue
        k = i + 4 if fs[i + 3].texto == ',' else None
        if k is None:
            continue
        signo = ''
        if fs[k].texto in ('-', '+'):
            signo, k = fs[k].texto, k + 1
        if k < len(fs) and fs[k].tipo == 'numero':
            hallazgos.append(_hallazgo(
                'desfase_horario_fijo', m, f.linea,
                f'DATEADD(hour, {signo}{fs[k].texto}, …): convierte zonas con un desfase fijo; con horario de verano '
                f'el desfase cambia según la fecha'))
    return hallazgos


# ── 7. ROUND que trunca ─────────────────────────────────────────────────────────────────────────────────────

def round_trunca(m: Modulo) -> list[dict]:
    """ROUND(x, n, f) con un tercer argumento distinto de 0 TRUNCA en lugar de redondear (gotcha de T-SQL)."""
    fs, hallazgos = m.fichas, []
    for i, f in enumerate(fs):
        if not (f.es('ROUND') and i + 1 < len(fs) and fs[i + 1].texto == '('):
            continue
        fin = cierre(fs, i + 1)
        nivel = fs[i + 1].nivel + 1
        comas = [k for k in range(i + 2, fin) if fs[k].texto == ',' and fs[k].nivel == nivel]
        if len(comas) != 2:
            continue
        tercero = fs[comas[1] + 1:fin]
        if len(tercero) == 1 and tercero[0].tipo == 'numero' and tercero[0].texto.strip('0.') == '':
            continue            # ROUND(x, n, 0): redondea
        literal = ' '.join(t.texto for t in tercero)
        hallazgos.append(_hallazgo('round_trunca', m, f.linea,
                                   f'ROUND(…, …, {literal}) trunca en vez de redondear: con montos, un centavo '
                                   f'de diferencia contra cualquier cálculo que redondee'))
    return hallazgos


# ── 7b. División entera ─────────────────────────────────────────────────────────────────────────────────────

ENTEROS = frozenset(('int', 'bigint', 'smallint', 'tinyint'))
_ENTERAS_SIEMPRE = frozenset(('COUNT', 'COUNT_BIG', 'DATEDIFF', 'DATEDIFF_BIG'))
_AGREGADOS_DEL_TIPO = frozenset(('SUM', 'MIN', 'MAX', 'AVG'))
# Palabras que no pueden ser un operando (cortan la expresión) aunque vengan antes de un '('.
_NO_OPERANDO = frozenset(('SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'NOT', 'AS', 'ON', 'WHEN', 'THEN', 'ELSE', 'END',
                          'IS', 'IN', 'LIKE', 'BETWEEN', 'EXISTS', 'VALUES', 'RETURN', 'IF', 'WHILE', 'SET', 'BY',
                          'HAVING', 'JOIN', 'APPLY', 'OVER', 'INTO', 'CASE', 'DISTINCT', 'ALL', 'TOP', 'ESCAPE'))


def division_entera(m: Modulo, tipos: dict[str, dict[str, str]]) -> list[dict]:
    """`a / b` con los DOS lados enteros: SQL Server trunca el cociente (y PostgreSQL también, salvo `avg`).

    Inferencia mínima de tipos, sin adivinar: son enteros los literales sin punto decimal, las columnas
    int/bigint/smallint/tinyint del esquema restaurado (resueltas por las fuentes del FROM de su consulta), las
    variables y parámetros declarados con esos tipos, COUNT/COUNT_BIG, DATEDIFF/DATEDIFF_BIG, SUM/MIN/MAX/AVG de un
    entero, CAST/CONVERT a un entero, ISNULL/NULLIF/COALESCE de enteros, un CASE cuyos resultados son todos enteros y la
    suma, resta, producto, cociente o módulo de enteros. Todo lo demás es «no se sabe» y NO se reporta.
    """
    fs, hallazgos = m.fichas, []
    enteras = variables_enteras(fs)
    columnas = {t: set(cols) for t, cols in tipos.items()}
    for k, f in enumerate(fs):
        if not (f.tipo == 'op' and f.texto == '/'):
            continue
        izquierda = _factores_a_la_izquierda(fs, k)
        derecha = _factor_a_la_derecha(fs, k)
        if not izquierda or derecha is None:
            continue
        tipo = _Tipos(fs, enteras, tipos, columnas, _fuentes_de_la_consulta(fs, k))
        if not (all(tipo.entero(a, b) for a, b in izquierda) and tipo.entero(*derecha)):
            continue
        inicio, fin = izquierda[-1][0], derecha[1]
        con_avg = any(fs[j].es('AVG') for j in range(inicio, fin))
        hallazgos.append(_hallazgo(
            'division_entera', m, f.linea,
            f'{_texto(fs, inicio, k)} / {_texto(fs, k + 1, fin)}: entero entre entero, el cociente se trunca'
            + ('; además AVG de un entero devuelve entero en SQL Server, y en PostgreSQL avg(integer) devuelve '
               'numeric: el mismo SQL da otro resultado' if con_avg else ''),
            expresion=_texto(fs, inicio, fin)))
    return hallazgos


def variables_enteras(fs: list[Ficha]) -> set[str]:
    """Variables y parámetros declarados int/bigint/smallint/tinyint (`@n int`, `@n AS int`), en mayúsculas."""
    resultado = set()
    for i, f in enumerate(fs):
        if f.tipo != 'variable':
            continue
        k = i + 1
        if k < len(fs) and fs[k].es('AS'):
            abre = apertura(fs, i)
            if abre is not None and abre > 0 and fs[abre - 1].es('CAST', 'TRY_CAST'):
                continue                    # CAST(@v AS int) no declara nada
            k += 1
        if k < len(fs) and fs[k].tipo == 'ident' and fs[k].texto.lower() in ENTEROS and not (
                k + 1 < len(fs) and fs[k + 1].texto == '.'):
            resultado.add(f.mayus)
    return resultado


def _texto(fs: list[Ficha], a: int, b: int, maximo: int = 90) -> str:
    partes: list[str] = []
    for j in range(a, b):
        t = fs[j].texto
        if partes and not (t in (')', ',', '.') or partes[-1].endswith(('(', '.'))
                           or (t == '(' and fs[j - 1].tipo == 'ident')):
            partes.append(' ')
        partes.append(t)
    texto = ''.join(partes)
    return texto if len(texto) <= maximo else texto[:maximo - 1] + '…'


def _primaria(fs: list[Ficha], a: int, b: int) -> int | None:
    """Fin (exclusivo) del operando primario que empieza en a: literal, variable, ( … ), CASE … END, columna o
    función (con su OVER ( … )). None si en a no empieza un operando."""
    if a >= b:
        return None
    f = fs[a]
    if f.tipo in ('numero', 'cadena', 'variable'):
        return a + 1
    if f.texto == '(':
        return cierre(fs, a) + 1
    if f.es('CASE'):
        return fin_de_caso(fs, a) + 1
    if f.tipo != 'ident' or f.mayus in _NO_OPERANDO:
        return None
    k = a
    while k + 2 < b and fs[k + 1].texto == '.' and fs[k + 2].tipo == 'ident':
        k += 2
    k += 1
    if k < b and fs[k].texto == '(':
        k = cierre(fs, k) + 1
        if k + 1 < b and fs[k].es('OVER') and fs[k + 1].texto == '(':
            k = cierre(fs, k + 1) + 1
    return k


def _primaria_hacia_atras(fs: list[Ficha], z: int) -> int | None:
    """Inicio del operando primario que termina en z (inclusive). None si en z no termina un operando."""
    if z < 0:
        return None
    f = fs[z]
    if f.tipo in ('numero', 'cadena', 'variable'):
        return z
    if f.tipo == 'op' and f.texto == ')':
        j = abre_de(fs, z)
        if j is None:
            return None
        if j >= 2 and fs[j - 1].es('OVER') and fs[j - 2].texto == ')':
            j = abre_de(fs, j - 2)          # SUM(x) OVER (…)
            if j is None:
                return None
        if j and fs[j - 1].tipo == 'ident' and fs[j - 1].mayus not in _NO_OPERANDO:
            j -= 1                          # nombre de la función (quizá calificado)
            while j >= 2 and fs[j - 1].texto == '.' and fs[j - 2].tipo == 'ident':
                j -= 2
        return j
    if f.es('END') and f.en_caso:
        return inicio_de_caso(fs, z)
    if f.tipo == 'ident' and f.mayus not in _NO_OPERANDO:
        j = z
        while j >= 2 and fs[j - 1].texto == '.' and fs[j - 2].tipo == 'ident':
            j -= 2
        return j
    return None


def _factores_a_la_izquierda(fs: list[Ficha], k: int) -> list[tuple[int, int]]:
    """Factores del dividendo de la '/' en k: los operandos unidos por *, / o % a su izquierda (misma precedencia,
    asociativos a la izquierda), del más cercano al más lejano. Vacío si no se reconoce un operando."""
    factores, z = [], k - 1
    while True:
        inicio = _primaria_hacia_atras(fs, z)
        if inicio is None:
            return []
        factores.append((inicio, z + 1))
        p = inicio - 1
        if p >= 1 and fs[p].tipo == 'op' and fs[p].texto in ('-', '+') and fs[p - 1].tipo == 'op' and \
                fs[p - 1].texto in ('*', '/', '%'):
            p -= 1                          # signo de un factor: a * -b / c
        if p >= 0 and fs[p].tipo == 'op' and fs[p].texto in ('*', '/', '%') and fs[p].nivel == fs[k].nivel:
            z = p - 1
            continue
        return factores


def _factor_a_la_derecha(fs: list[Ficha], k: int) -> tuple[int, int] | None:
    a = k + 1
    while a < len(fs) and fs[a].tipo == 'op' and fs[a].texto in ('-', '+'):
        a += 1                              # signo
    fin = _primaria(fs, a, len(fs))
    return (a, fin) if fin is not None else None


def _fuentes_de_la_consulta(fs: list[Ficha], k: int) -> list[dict]:
    """Fuentes del FROM de la consulta (SELECT o UPDATE) a la que pertenece la ficha k."""
    limite = fs[k].nivel
    for j in range(k - 1, -1, -1):
        limite = min(limite, fs[j].nivel)
        if fs[j].nivel != limite or not inicia_sentencia(fs, j):
            continue
        if fs[j].es('SET') and sentencia_actual(fs, j) == 'UPDATE':
            continue
        if not fs[j].es('SELECT', 'UPDATE'):
            return []
        fin = fin_de_consulta(fs, j) if fs[j].es('SELECT') else fin_de_sentencia(fs, j)
        desde = next((x for x in range(j + 1, fin) if fs[x].nivel == fs[j].nivel and fs[x].es('FROM')), None)
        if desde is not None:
            return fuentes(fs, desde, _fin_del_from(fs, desde, fin))
        if fs[j].es('UPDATE'):
            nombre, _sig = nombre_objeto(fs, j + 1)
            if nombre and not nombre.startswith('#'):
                return [{'nombre': normalizar(nombre), 'alias': None, 'union': 'FROM', 'on': None}]
        return []
    return []


class _Tipos:
    """Inferencia mínima: ¿la expresión es entera? (True sólo si se sabe; «no se sabe» es False)."""

    def __init__(self, fs: list[Ficha], enteras: set[str], tipos: dict[str, dict[str, str]],
                 columnas: dict[str, set[str]], fuentes_: list[dict]):
        self.fs, self.enteras, self.tipos, self.columnas, self.fuentes = fs, enteras, tipos, columnas, fuentes_

    def entero(self, a: int, b: int) -> bool:
        """El operando primario [a, b)."""
        fs = self.fs
        if a >= b:
            return False
        f = fs[a]
        if f.tipo == 'numero':
            return b == a + 1 and f.texto.isdigit()
        if f.tipo == 'variable':
            return b == a + 1 and f.mayus in self.enteras
        if f.texto == '(':
            return not (a + 1 < b and fs[a + 1].es('SELECT')) and self.expresion(a + 1, b - 1)
        if f.es('CASE'):
            return self._caso(a, b)
        if f.tipo != 'ident':
            return False
        ref = _columna_en(fs, a)
        if ref is not None:
            if ref[2] != b:
                return False
            fuente = _resolver(self.fuentes, ref[0], ref[1], self.columnas)
            nombre = self.fuentes[fuente]['nombre'] if fuente is not None else None
            return self.tipos.get(nombre or '', {}).get(ref[1]) in ENTEROS
        k = a + 1
        if k >= b or fs[k].texto != '(':
            return False                    # función calificada (dbo.f(…)): no se sabe
        return self._funcion(f.mayus, k, cierre(fs, k))

    def expresion(self, a: int, b: int) -> bool:
        """Operandos unidos por + - * / %, todos enteros."""
        fs, k = self.fs, a
        while True:
            while k < b and fs[k].tipo == 'op' and fs[k].texto in ('-', '+'):
                k += 1
            fin = _primaria(fs, k, b)
            if fin is None or fin > b or not self.entero(k, fin):
                return False
            if fin == b:
                return True
            if not (fs[fin].tipo == 'op' and fs[fin].texto in ('+', '-', '*', '/', '%')):
                return False
            k = fin + 1

    def _argumentos(self, abre: int, cierra: int) -> list[tuple[int, int]]:
        fs, nivel = self.fs, self.fs[abre].nivel + 1
        comas = [j for j in range(abre + 1, cierra) if fs[j].nivel == nivel and fs[j].texto == ',']
        limites = [abre, *comas, cierra]
        return [(limites[n] + 1, limites[n + 1]) for n in range(len(limites) - 1)]

    def _funcion(self, nombre: str, abre: int, cierra: int) -> bool:
        fs = self.fs
        argumentos = self._argumentos(abre, cierra)
        if nombre in _ENTERAS_SIEMPRE:
            return True
        if nombre in _AGREGADOS_DEL_TIPO and len(argumentos) == 1:
            a, b = argumentos[0]
            while a < b and fs[a].es('DISTINCT', 'ALL'):
                a += 1
            return self.expresion(a, b)
        if nombre in ('CAST', 'TRY_CAST') and len(argumentos) == 1:
            nivel = fs[abre].nivel + 1
            como = next((j for j in range(abre + 1, cierra) if fs[j].nivel == nivel and fs[j].es('AS')), None)
            return como is not None and como + 2 == cierra and fs[como + 1].texto.lower() in ENTEROS
        if nombre in ('CONVERT', 'TRY_CONVERT') and argumentos:
            a, b = argumentos[0]
            return b == a + 1 and fs[a].texto.lower() in ENTEROS
        if nombre in ('ISNULL', 'NULLIF') and argumentos:
            return self.expresion(*argumentos[0])
        if nombre == 'COALESCE' and argumentos:
            return all(self.expresion(a, b) for a, b in argumentos)
        return False

    def _caso(self, a: int, b: int) -> bool:
        """CASE … END con TODOS sus resultados (THEN y ELSE) enteros."""
        fs, nivel = self.fs, self.fs[a].nivel
        resultados, inicio, profundidad = [], None, 0
        for j in range(a + 1, b - 1):
            f = fs[j]
            if f.nivel != nivel:
                continue
            if f.es('CASE'):
                profundidad += 1
            elif f.es('END') and f.en_caso:
                profundidad -= 1
            if profundidad:
                continue
            if f.es('WHEN', 'ELSE') and inicio is not None:
                resultados.append((inicio, j))
                inicio = None
            if f.es('THEN', 'ELSE'):
                inicio = j + 1
        if inicio is not None:
            resultados.append((inicio, b - 1))
        return bool(resultados) and all(self.expresion(x, y) for x, y in resultados)


# ── 8. Columnas que ningún módulo lee ────────────────────────────────────────────────────────────────────────

_OBJETO_TRAS = frozenset(('FROM', 'JOIN', 'INTO', 'UPDATE', 'MERGE', 'USING', 'EXEC', 'EXECUTE', 'TABLE',
                          'TRUNCATE', 'APPLY'))


def lecturas(modulos: list[Modulo]) -> tuple[set[str], set[str]]:
    """(identificadores leídos, tablas leídas) en todos los módulos.

    No cuentan como lectura: las listas de columnas de un INSERT, el lado izquierdo de un SET en un UPDATE, los
    nombres de objeto y el encabezado del módulo (parámetros).
    """
    leidos: set[str] = set()
    tablas: set[str] = set()
    for m in modulos:
        fs = m.fichas
        excluir: set[int] = set(range(_inicio_cuerpo_modulo(fs)))
        for i, f in enumerate(fs):
            if f.tipo != 'ident':
                continue
            if f.mayus in _OBJETO_TRAS:
                nombre, sig = nombre_objeto(fs, i + 1)
                if nombre:
                    excluir.update(range(i + 1, sig))
                    # UPDATE también lee su tabla (WHERE y SET usan columnas; DELETE entra por su FROM); INSERT no
                    if f.mayus in ('FROM', 'JOIN', 'USING', 'APPLY', 'UPDATE'):
                        tablas.add(normalizar(nombre))
                    if f.mayus == 'INTO' and sig < len(fs) and fs[sig].texto == '(':
                        excluir.update(range(sig, cierre(fs, sig) + 1))
            elif f.mayus == 'SET' and _sentencia_con_set(fs, i):
                excluir.update(_destinos_de_set(fs, i))
        for i, f in enumerate(fs):
            if f.tipo == 'ident' and i not in excluir:
                leidos.add(f.mayus)
    return leidos, tablas


def _destinos_de_set(fs: list[Ficha], i_set: int) -> set[int]:
    nivel, destinos, k = fs[i_set].nivel, set(), i_set + 1
    esperando = True
    while k < len(fs):
        f = fs[k]
        if f.nivel < nivel or (f.nivel == nivel and (f.es('FROM', 'WHERE', 'OUTPUT') or f.texto == ';' or (
                inicia_sentencia(fs, k)))):
            break
        if f.nivel == nivel and f.texto == ',':
            esperando = True
        elif esperando:
            j = k
            while j + 2 < len(fs) and fs[j].tipo == 'ident' and fs[j + 1].texto == '.':
                j += 2
            if fs[j].tipo == 'ident' and j + 1 < len(fs) and fs[j + 1].texto in ('=', '+=', '-=', '*=', '/='):
                destinos.add(j)
            esperando = False
        k += 1
    return destinos


def columnas_sin_lectura(modulos: list[Modulo], columnas: dict[str, list[str]]) -> list[dict]:
    """columnas: {'esquema.tabla': [col, …]} (tablas de usuario)."""
    leidos, tablas_leidas = lecturas(modulos)
    hallazgos = []
    for tabla, cols in sorted(columnas.items()):
        if tabla not in tablas_leidas:
            hallazgos.append({'categoria': 'tabla_sin_lectura', 'objeto': tabla, 'tipo_objeto': 'TABLA',
                              'linea': None, 'fragmento': '',
                              'detalle': 'ningún procedimiento, vista, trigger ni job la lee (sólo se escribe o '
                                         'la lee otra aplicación)'})
            continue
        for col in cols:
            if col.upper() not in leidos:
                hallazgos.append({'categoria': 'columna_sin_lectura', 'objeto': f'{tabla}.{col.lower()}',
                                  'tipo_objeto': 'COLUMNA', 'linea': None, 'fragmento': '',
                                  'detalle': 'ningún procedimiento, vista, trigger ni job la lee: sólo una '
                                             'comparación de esquema columna por columna nota si se pierde'})
    return hallazgos


def analizar_codigo(modulos: list[Modulo], padres_de: dict[str, set[str]],
                    unicas: dict[str, list[set[str]]] | None = None,
                    columnas: dict[str, set[str]] | None = None,
                    tipos: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """tipos: {'esquema.tabla': {columna: tipo}} del esquema restaurado (para la división entera)."""
    hallazgos = []
    for m in modulos:
        hallazgos += top_sin_order_by(m)
        hallazgos += asignacion_multifila(m, unicas or {}, columnas or {})
        hallazgos += inner_join_hija(m, padres_de)
        hallazgos += reloj_en_regla(m)
        hallazgos += reloj_por_variable(m)
        hallazgos += if_exists_sin_else(m)
        hallazgos += desfase_horario_fijo(m)
        hallazgos += round_trunca(m)
        hallazgos += division_entera(m, tipos or {})
        hallazgos += literales(m)
    return hallazgos
