"""Detectores por PATRÓN sobre el código de la base (procedimientos, vistas, triggers, funciones y pasos de jobs).

Son genéricos: buscan formas de código, no nombres conocidos. Cada uno devuelve hallazgos con el objeto, la línea
y el fragmento, para que una persona decida si es un defecto real (el control sobre una base pública mide cuántos
son ruido).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from radiografia.tsql import RELOJ, Ficha, apertura, cierre, fichas, fin_de_consulta, inicia_sentencia, nombre_objeto


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
            return 'asignacion'
        if f.tipo != 'ident':
            continue
        if f.mayus in _REGLA:
            return 'regla'
        if f.mayus in _ASIGNACION:
            return 'asignacion'
    return 'asignacion'


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


# ── 7. Columnas que ningún módulo lee ────────────────────────────────────────────────────────────────────────

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


def analizar_codigo(modulos: list[Modulo], padres_de: dict[str, set[str]]) -> list[dict]:
    hallazgos = []
    for m in modulos:
        hallazgos += top_sin_order_by(m)
        hallazgos += inner_join_hija(m, padres_de)
        hallazgos += reloj_en_regla(m)
        hallazgos += if_exists_sin_else(m)
        hallazgos += desfase_horario_fijo(m)
        hallazgos += literales(m)
    return hallazgos
