"""El corte medido por DOS CAMINOS (criterio 3 del plan de S3, ADR 0013 y 0016). Sin base: aquí está el cálculo de
conjuntos; las consultas las corre `corte/medir.py`.

- **Camino por identidad:** `MAX(id)` de cada tabla en la foto del respaldo (el corte) y en la del congelamiento.
  Una fila es del DELTA si su id está entre los dos, y POSTERIOR si pasa al del congelamiento.
- **Camino por sellos:** cada tabla con identidad declara cómo sabe CUÁNDO se escribió una fila sin mirar su id:
  - la bitácora, que sella con el reloj del servidor (`GETDATE()` del trigger), y por ella sus partidas;
  - `fecha_registro`, la hora de negocio con la que la interfaz registra la orden (y que copia a sus partidas);
  - el folio FX, el consumible que la operación toma al registrarse (no tiene bitácora ni `fecha_registro`).
  Los límites son los de las mismas dos fotos: el instante del servidor, la hora de negocio y el folio siguiente.

La discrepancia es DIFERENCIA DE CONJUNTOS: los ids mayores al corte que un camino ve y el otro no, y lo mismo del
lado del congelamiento. Contar no basta: un hueco de identidad (una inserción revertida consume su id) hace que
`MAX(id) - corte` no sea el número de filas sin que haya ningún error, y dos errores opuestos se cancelan en una
cuenta. Por eso se comparan los ids, uno por uno.

Las tablas salen del inventario del código (`objetos.json`, la llave `tablas`), nunca de una lista fija: una tabla con
identidad sin camino por sellos, o un camino de una tabla que el código ya no tiene, detiene el corte.

Control negativo, sobre el legado vivo: el camino por `fecha_operacion` (la fecha de NEGOCIO, no un sello de
registro) pierde las altas que la sucursal reenvió fechadas hacia atrás, y la comparación falla nombrándolas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

CDMX = ZoneInfo('America/Mexico_City')
DELTA, POSTERIOR = 'delta', 'posterior'
CLASES = (DELTA, POSTERIOR)
MUESTRA = 50                     # ids que se listan por diferencia (los conteos son completos)


@dataclass(frozen=True)
class Camino:
    """Un camino por sellos de una tabla. La consulta es UN literal con un solo parámetro (el límite inferior, ya
    en el tipo de su reloj) y devuelve `(id, sello)` de cada fila sellada DESPUÉS del corte."""
    tabla: str
    nombre: str
    reloj: str                   # 'servidor' | 'negocio' | 'folio:FX'
    que_sella: str
    consulta: str
    control_negativo: bool = False


# Los relojes `servidor` y `negocio` devuelven el sello en estilo 121 (aaaa-mm-dd hh:mi:ss.mmm); el folio, su número.
CAMINOS: tuple[Camino, ...] = (
    Camino('dbo.bitacora', 'bitácora (su fecha)', 'servidor',
           'la fecha de cada renglón: GETDATE() del servidor en el trigger',
           """SELECT id, CONVERT(varchar(23), fecha, 121) FROM dbo.bitacora
WHERE fecha > CONVERT(datetime, %s, 121)"""),
    Camino('dbo.orden_pago', 'bitácora (alta)', 'servidor',
           'el renglón «I» que el trigger escribe al insertar la orden',
           """SELECT b.llave, CONVERT(varchar(23), b.fecha, 121) FROM dbo.bitacora b
WHERE b.tabla = N'orden_pago' AND b.accion = 'I' AND b.fecha > CONVERT(datetime, %s, 121)"""),
    Camino('dbo.orden_pago', 'fecha_registro', 'negocio',
           'la hora de negocio con la que la interfaz registra (o re-registra) la orden',
           """SELECT id, CONVERT(varchar(23), fecha_registro, 121) FROM dbo.orden_pago
WHERE fecha_registro > CONVERT(datetime, %s, 126)"""),
    Camino('dbo.partida_liquidada', 'bitácora (alta de su orden)', 'servidor',
           'la escribe sp_registrar_orden en la misma llamada que da de alta la orden: el renglón «I» de su orden',
           """SELECT p.id, CONVERT(varchar(23), b.fecha, 121)
FROM dbo.partida_liquidada p
JOIN dbo.bitacora b ON b.tabla = N'orden_pago' AND b.accion = 'I' AND b.llave = p.orden_id
WHERE b.fecha > CONVERT(datetime, %s, 121)"""),
    Camino('dbo.partida_liquidada', 'fecha_hora (= fecha_registro)', 'negocio',
           'sp_registrar_orden le copia la fecha_registro de su orden',
           """SELECT id, CONVERT(varchar(23), fecha_hora, 121) FROM dbo.partida_liquidada
WHERE fecha_hora > CONVERT(datetime, %s, 126)"""),
    Camino('dbo.partida_solicitada', 'bitácora (liquidación de su orden)', 'servidor',
           'la escribe sp_registrar_liquidacion en la misma llamada que pasa la orden a LIQUIDADA: ese renglón «U»',
           """SELECT s.id, CONVERT(varchar(23), b.fecha, 121)
FROM dbo.partida_solicitada s
JOIN dbo.bitacora b ON b.tabla = N'orden_pago' AND b.accion = 'U' AND b.estatus_nuevo = 'LIQUIDADA'
     AND b.llave = s.orden_id
WHERE b.fecha > CONVERT(datetime, %s, 121)"""),
    Camino('dbo.operacion', 'folio FX (consumible)', 'folio:FX',
           'el folio que sp_registrar_operacion toma de dbo.folio al registrar: un contador aparte de la identidad',
           """SELECT id, TRY_CAST(SUBSTRING(folio, 4, 20) AS bigint) FROM dbo.operacion
WHERE folio LIKE 'FX-%%' AND TRY_CAST(SUBSTRING(folio, 4, 20) AS bigint) > %s"""),
    Camino('dbo.operacion', 'fecha_operacion (control negativo)', 'negocio',
           'la fecha de NEGOCIO que manda la sucursal: no es un sello de registro',
           """SELECT id, CONVERT(varchar(23), fecha_operacion, 121) FROM dbo.operacion
WHERE fecha_operacion > CONVERT(datetime, %s, 126)""",
           control_negativo=True),
)


@dataclass(frozen=True)
class Clases:
    """Ids del delta (corte < x ≤ congelamiento) y posteriores (x > congelamiento) según un camino."""
    delta: frozenset[int]
    posterior: frozenset[int]

    def mayores_al_corte(self) -> frozenset[int]:
        return self.delta | self.posterior

    def de(self, clase: str) -> frozenset[int]:
        return self.delta if clase == DELTA else self.posterior


def por_identidad(ids, corte: int, congelamiento: int) -> Clases:
    ids = {int(i) for i in ids if int(i) > corte}
    return Clases(frozenset(i for i in ids if i <= congelamiento), frozenset(i for i in ids if i > congelamiento))


def por_sello(filas, desde, hasta) -> Clases:
    """`filas` = (id, sello). El sello ya en el tipo de su reloj (datetime o entero), igual que los límites."""
    delta, posterior = set(), set()
    for id_, sello in filas:
        if sello is None or sello <= desde:
            continue                                      # la consulta ya filtra; un sello nulo no ubica la fila
        (delta if sello <= hasta else posterior).add(int(id_))
    return Clases(frozenset(delta), frozenset(posterior))


def comparar(identidad: Clases, sellos: Clases) -> dict:
    """Diferencia de conjuntos entre los dos caminos: primero los ids mayores al corte, luego la frontera del
    congelamiento. `coincide` sólo si no hay NINGÚN id de un lado que falte del otro."""
    def lado(a: frozenset[int], b: frozenset[int]) -> dict:
        solo_a, solo_b = sorted(a - b), sorted(b - a)
        return {'solo_por_identidad': len(solo_a), 'solo_por_sellos': len(solo_b),
                'muestra_solo_por_identidad': solo_a[:MUESTRA], 'muestra_solo_por_sellos': solo_b[:MUESTRA]}

    resultado = {'mayores_al_corte': lado(identidad.mayores_al_corte(), sellos.mayores_al_corte())}
    for clase in CLASES:
        resultado[clase] = lado(identidad.de(clase), sellos.de(clase))
    resultado['coincide'] = all(r['solo_por_identidad'] == 0 and r['solo_por_sellos'] == 0
                                for r in resultado.values() if isinstance(r, dict))
    return resultado


def huecos(ids, desde: int, hasta: int) -> list[int]:
    """Ids que la identidad saltó entre `desde` (excluido) y `hasta`: inserciones revertidas, no filas perdidas."""
    presentes = {int(i) for i in ids}
    return [i for i in range(desde + 1, hasta + 1) if i not in presentes]


def nombres(ids, por_id: dict[int, str] | None = None) -> list[str]:
    por_id = por_id or {}
    return [f'{i} ({por_id[i]})' if i in por_id else str(i) for i in sorted(ids)]


# ── límites de cada reloj, desde las fotos del legado vivo ─────────────────────────────────────────────────────

def a_local(instante_utc: str) -> datetime:
    """Instante UTC (ISO) a la hora de negocio de la Ciudad de México, sin zona (como la guarda el legado)."""
    return datetime.fromisoformat(instante_utc).astimezone(CDMX).replace(tzinfo=None)


def limites(reloj: str, vivo: dict, delta: dict) -> dict:
    """El corte y el congelamiento en el reloj de un camino: `desde`/`hasta` para clasificar y `parametro` para la
    consulta (el límite inferior en el formato que su CONVERT espera)."""
    respaldo, congelamiento = vivo['al_respaldo'], vivo['al_congelamiento']
    if reloj == 'servidor':
        for foto in (respaldo, congelamiento):
            if not foto.get('servidor'):
                raise ValueError('la foto del legado vivo no trae el instante del servidor: corre de nuevo '
                                 '`python -m legado.vivo` (lo anota desde S3, paso 2)')
        return {'desde': datetime.fromisoformat(respaldo['servidor']),
                'hasta': datetime.fromisoformat(congelamiento['servidor']), 'parametro': respaldo['servidor'],
                'fuente': 'GETDATE() del servidor en las fotos del respaldo y del congelamiento (legado/vivo)'}
    if reloj == 'negocio':
        desde, hasta = a_local(delta['respaldo_utc']), a_local(delta['congelamiento_utc'])
        return {'desde': desde, 'hasta': hasta, 'parametro': desde.isoformat(timespec='seconds'),
                'fuente': 'respaldo_utc y congelamiento_utc del guion del delta, en hora de la Ciudad de México'}
    if reloj.startswith('folio:'):
        serie = reloj.split(':', 1)[1]
        # `siguiente` es el folio que se usará: lo tomado antes de la foto es menor
        desde, hasta = respaldo['folios'][serie] - 1, congelamiento['folios'][serie] - 1
        return {'desde': desde, 'hasta': hasta, 'parametro': desde,
                'fuente': f'dbo.folio.siguiente de la serie {serie} en las fotos del respaldo y del congelamiento'}
    raise ValueError(f'reloj desconocido: {reloj}')


def sello(reloj: str, valor):
    """El sello que devuelve la consulta, en el mismo tipo que sus límites."""
    if valor is None:
        return None
    if reloj in ('servidor', 'negocio'):
        return datetime.fromisoformat(valor) if isinstance(valor, str) else valor
    return int(valor)


# ── cobertura: las tablas del inventario contra los caminos declarados ────────────────────────────────────────

def cobertura(tablas: dict, caminos: tuple[Camino, ...] = CAMINOS) -> dict:
    """`tablas` es la llave `tablas` del inventario (`objetos.json`). Cada tabla con identidad necesita al menos un
    camino por sellos que no sea control negativo; un camino de una tabla que el código no tiene es huérfano."""
    con_identidad = sorted(t for t, d in tablas.items() if d.get('identidad'))
    sin_identidad = sorted(t for t, d in tablas.items() if not d.get('identidad'))
    validos = {c.tabla for c in caminos if not c.control_negativo}
    return {
        'con_identidad': con_identidad,
        'sin_identidad': sin_identidad,
        'sin_camino': [t for t in con_identidad if t not in validos],
        'caminos_huerfanos': sorted({f'{c.tabla} · {c.nombre}' for c in caminos if c.tabla not in tablas}),
        'caminos_de_tabla_sin_identidad': sorted({f'{c.tabla} · {c.nombre}' for c in caminos
                                                  if c.tabla in tablas and c.tabla in sin_identidad}),
    }


def veredicto(resultado: dict) -> list[str]:
    """Lo que detiene el corte, nombrado. Vacío = el corte medido por los dos caminos coincide."""
    faltas = []
    cob = resultado['cobertura']
    faltas += [f'tabla con identidad sin camino por sellos: {t}' for t in cob['sin_camino']]
    faltas += [f'camino huérfano (su tabla ya no está en el código): {c}' for c in cob['caminos_huerfanos']]
    faltas += [f'camino sobre una tabla sin identidad: {c}' for c in cob['caminos_de_tabla_sin_identidad']]
    for tabla, t in resultado['tablas'].items():
        for problema in t.get('fotos_inconsistentes', []):
            faltas.append(f'{tabla}: {problema}')
        for c in t.get('caminos', []):
            if c['control_negativo']:
                continue
            if not c['comparacion']['coincide']:
                m = c['comparacion']['mayores_al_corte']
                faltas.append(f"{tabla} · {c['nombre']}: {m['solo_por_identidad']} ids sólo por identidad "
                              f"{m['muestra_solo_por_identidad'][:10]} y {m['solo_por_sellos']} sólo por sellos "
                              f"{m['muestra_solo_por_sellos'][:10]}"
                              + _frontera(c['comparacion']))
    negativo = resultado.get('control_negativo')
    if negativo is not None and not negativo['detectado']:
        faltas.append('el control negativo (camino por fecha_operacion) NO falló nombrando las altas fechadas '
                      f"hacia atrás: nombró {negativo['nombradas']} de {negativo['esperadas']}")
    return faltas


def _frontera(comparacion: dict) -> str:
    partes = [f"{clase}: {comparacion[clase]['solo_por_identidad']}/{comparacion[clase]['solo_por_sellos']}"
              for clase in CLASES if comparacion[clase]['solo_por_identidad'] or comparacion[clase]['solo_por_sellos']]
    return (' · por clase (sólo identidad/sólo sellos) ' + ', '.join(partes)) if partes else ''
