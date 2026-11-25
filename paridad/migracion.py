"""Ejercicio 1, «VERIFICAR LA MIGRACIÓN»: la carga histórica contra el legado restaurado.

1. **Byte a byte.** Cada columna de cada tabla del legado (los mismos SELECT que alimentaron la carga) contra el
   volcado del TO-BE, cruzando por llave natural. Al legado sólo se le aplican los parches documentados de
   `paridad/mapeo.py`, y cada uno se cuenta. Después de los parches, los dos textos deben ser IDÉNTICOS en UTF-8.
2. **Esquema** columna por columna (`paridad/esquema.py`), después de cada carga.
3. **Cuadre interno por lado** («Σ partes = total del encabezado»), en el legado y en el TO-BE: atrapa un desglose
   en 0 o una lista cruzada desde el primer día.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from paridad.formato import texto
from paridad.mapeo import aplicar, pisos_por_llegada

# ── consultas del legado (restaurado) y del TO-BE ─────────────────────────────────────────────────────────────

LEGADO = {
    'moneda': 'SELECT codigo, numerico, nombre, decimales, activa FROM dbo.moneda',
    'folio': 'SELECT serie, siguiente FROM dbo.folio',
    'operacion': 'SELECT id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda, '
                 'monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus FROM dbo.operacion',
    'orden_pago': 'SELECT id, operacion_id, folio, uetr, referencia_mt103, fecha_registro, fecha_envio, fecha_valor, '
                  'bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, gastos, '
                  'codigo_proposito, estatus, horas_liquidacion FROM dbo.orden_pago',
    'partida_solicitada': 'SELECT s.orden_id, p.uetr, s.renglon, s.concepto, s.moneda, s.monto, s.fecha_hora, '
                          's.referencia FROM dbo.partida_solicitada s JOIN dbo.orden_pago p ON p.id = s.orden_id',
    'partida_liquidada': 'SELECT l.orden_id, p.uetr, l.renglon, l.concepto, l.moneda, l.monto, l.fecha_hora, '
                         'l.referencia FROM dbo.partida_liquidada l JOIN dbo.orden_pago p ON p.id = l.orden_id',
}
TOBE = {
    'moneda': 'SELECT codigo, numerico, nombre, decimales, activa FROM decant.moneda',
    'consecutivo': 'SELECT serie, siguiente FROM decant.consecutivo',
    'operacion': 'SELECT id, folio, fecha_operacion, sucursal, canal, cliente, cuenta_clabe, tipo, moneda, '
                 'monto_divisa, tipo_cambio, tipo_cambio_referencia, monto_mxn, estatus FROM decant.operacion',
    'orden_pago': 'SELECT uetr, operacion_id, folio, referencia_mt103, fecha_registro, fecha_envio, fecha_valor, '
                  'bic_corresponsal, bic_intermediario, beneficiario, cuenta_beneficiario, moneda, monto, gastos, '
                  'codigo_proposito, estatus, horas_liquidacion, registros FROM decant.orden_pago',
    'registro_orden': 'SELECT id_legado, uetr, fecha_registro FROM decant.registro_orden',
    'partida_corresponsal': 'SELECT uetr, renglon, concepto, moneda, monto, fecha_hora, referencia '
                            'FROM decant.partida_corresponsal',
    'partida_cliente': 'SELECT uetr, renglon, concepto, moneda, monto, fecha_hora, referencia '
                       'FROM decant.partida_cliente',
}

# (columna del legado, columna del TO-BE, parches)
COL_OPERACION = [
    ('id', 'id', ()), ('fecha_operacion', 'fecha_operacion', ('T5_cdmx',)), ('sucursal', 'sucursal', ('char',)),
    ('canal', 'canal', ()), ('cliente', 'cliente', ()), ('cuenta_clabe', 'cuenta_clabe', ('T3_texto',)),
    ('tipo', 'tipo', ('char',)), ('moneda', 'moneda', ('char',)), ('monto_divisa', 'monto_divisa', ()),
    ('tipo_cambio', 'tipo_cambio', ()), ('tipo_cambio_referencia', 'tipo_cambio_referencia', ('T3_numero',)),
    ('monto_mxn', 'monto_mxn', ()), ('estatus', 'estatus', ()),
]
COL_ORDEN = [
    ('operacion_id', 'operacion_id', ()), ('folio', 'folio', ()), ('referencia_mt103', 'referencia_mt103', ()),
    ('fecha_registro', 'fecha_registro', ('T5_cdmx_llegada',)),
    ('fecha_envio', 'fecha_envio', ('T5_cdmx_llegada',)),
    ('fecha_valor', 'fecha_valor', ()), ('bic_corresponsal', 'bic_corresponsal', ('char',)),
    ('bic_intermediario', 'bic_intermediario', ('char', 'T3_texto')), ('beneficiario', 'beneficiario', ()),
    ('cuenta_beneficiario', 'cuenta_beneficiario', ()), ('moneda', 'moneda', ('char',)), ('monto', 'monto', ()),
    ('gastos', 'gastos', ('char',)), ('codigo_proposito', 'codigo_proposito', ('char',)),
    ('estatus', 'estatus', ()), ('horas_liquidacion', 'horas_liquidacion', ()),
]
COL_PARTIDA_CORRESPONSAL = [
    ('concepto', 'concepto', ()), ('moneda', 'moneda', ('char',)), ('monto', 'monto', ()),
    ('fecha_hora', 'fecha_hora', ('T5_ny',)), ('referencia', 'referencia', ('ciega1_T3',)),
]
COL_PARTIDA_CLIENTE = [
    ('concepto', 'concepto', ()), ('moneda', 'moneda', ('char',)), ('monto', 'monto', ()),
    ('fecha_hora', 'fecha_hora', ('T5_cdmx_llegada',)), ('referencia', 'referencia', ()),
]
# Entradas que un re-registro repite: deben ser IDÉNTICAS a las del documento (prueba de que no se pierde nada).
COL_DUPLICADAS = ['operacion_id', 'folio', 'uetr', 'referencia_mt103', 'fecha_envio', 'fecha_valor',
                  'bic_corresponsal', 'bic_intermediario', 'beneficiario', 'cuenta_beneficiario', 'moneda', 'monto',
                  'gastos', 'codigo_proposito']


def _filas(cursor, consulta: str) -> list[dict]:
    cursor.execute(consulta)
    nombres = [d[0] for d in cursor.description]
    return [dict(zip(nombres, f)) for f in cursor.fetchall()]


class Comparacion:
    """Acumula una tabla: faltan, sobran, celdas distintas, celdas y bytes comparados, y parches aplicados."""

    def __init__(self, nombre: str, llave: str):
        self.nombre, self.llave = nombre, llave
        self.faltan: list = []
        self.sobran: list = []
        self.distintas: Counter = Counter()
        self.ejemplos: list[dict] = []
        self.parches: Counter = Counter()
        self.filas = self.celdas = self.bytes = 0

    def celda(self, llave, col_legado: str, valor_legado, col_tobe: str, valor_tobe, parches: tuple[str, ...],
              piso=None):
        esperado = valor_legado
        for p in parches:
            antes = texto(esperado)
            esperado = aplicar((p,), esperado, piso)
            if texto(esperado) != antes:
                self.parches[p] += 1
        a, b = texto(esperado), texto(valor_tobe)
        self.celdas += 1
        self.bytes += len((a or '').encode('utf-8'))
        if a != b:
            self.distintas[col_tobe] += 1
            if len(self.ejemplos) < 8:
                self.ejemplos.append({'llave': str(llave), 'columna': col_legado, 'legado': texto(valor_legado),
                                      'esperado': a, 'tobe': b})

    def resumen(self) -> dict:
        return {'tabla': self.nombre, 'llave': self.llave, 'filas': self.filas, 'celdas': self.celdas,
                'bytes': self.bytes, 'faltan': len(self.faltan), 'sobran': len(self.sobran),
                'ejemplos_faltan': [str(x) for x in self.faltan[:5]],
                'ejemplos_sobran': [str(x) for x in self.sobran[:5]],
                'celdas_distintas': dict(self.distintas), 'ejemplos': self.ejemplos,
                'parches': dict(self.parches),
                'cuadra': not self.faltan and not self.sobran and not self.distintas}


def _cruzar(c: Comparacion, legado: dict, tobe: dict, columnas, pisos: dict | None = None) -> None:
    """`pisos`: id de la fila de orden → (piso del registro, instante del registro), para T5_cdmx_llegada."""
    c.faltan = [k for k in legado if k not in tobe]
    c.sobran = [k for k in tobe if k not in legado]
    for llave, fila in legado.items():
        otra = tobe.get(llave)
        if otra is None:
            continue
        c.filas += 1
        piso_registro, registro, piso_envio = (pisos or {}).get(fila.get('_orden'), (None, None, None))
        for col_legado, col_tobe, parches in columnas:
            piso = {'fecha_envio': piso_envio, 'fecha_hora': registro}.get(col_legado, piso_registro)
            c.celda(llave, col_legado, fila[col_legado], col_tobe, otra[col_tobe], parches, piso)


def byte_a_byte(cursor_legado, cursor_tobe) -> list[dict]:
    resultado = []

    c = Comparacion('dbo.moneda → decant.moneda', 'codigo')
    leg = {f['codigo'].rstrip(): f for f in _filas(cursor_legado, LEGADO['moneda'])}
    tob = {f['codigo']: f for f in _filas(cursor_tobe, TOBE['moneda'])}
    _cruzar(c, leg, tob, [('codigo', 'codigo', ('char',)), ('numerico', 'numerico', ('char',)),
                          ('nombre', 'nombre', ()), ('decimales', 'decimales', ()), ('activa', 'activa', ())])
    resultado.append(c.resumen())

    c = Comparacion('dbo.folio → decant.consecutivo', 'serie')
    leg = {f['serie'].rstrip(): f for f in _filas(cursor_legado, LEGADO['folio'])}
    tob = {f['serie']: f for f in _filas(cursor_tobe, TOBE['consecutivo'])}
    _cruzar(c, leg, tob, [('siguiente', 'siguiente', ())])
    resultado.append(c.resumen())

    c = Comparacion('dbo.operacion → decant.operacion', 'folio')
    leg = {f['folio']: f for f in _filas(cursor_legado, LEGADO['operacion'])}
    tob = {f['folio']: f for f in _filas(cursor_tobe, TOBE['operacion'])}
    _cruzar(c, leg, tob, COL_OPERACION)
    resultado.append(c.resumen())
    del leg, tob

    # órdenes: el documento (fila vigente), su historia de registros y las filas reemplazadas
    ordenes = _filas(cursor_legado, LEGADO['orden_pago'])
    pisos = pisos_por_llegada(ordenes)
    por_uetr: dict[str, list[dict]] = defaultdict(list)
    for f in ordenes:
        f['_orden'] = f['id']
        por_uetr[f['uetr'].rstrip()].append(f)
    vigentes = {}
    for uetr, filas in por_uetr.items():
        v = [f for f in filas if f['estatus'] != 'REEMPLAZADA']
        if len(v) == 1:
            vigentes[uetr] = v[0]
    c = Comparacion('dbo.orden_pago (fila vigente) → decant.orden_pago', 'uetr')
    tob = {str(f['uetr']): f for f in _filas(cursor_tobe, TOBE['orden_pago'])}
    _cruzar(c, vigentes, tob, COL_ORDEN, pisos)
    sin_vigente = [u for u in por_uetr if u not in vigentes]
    registros_distintos = sum(1 for u, fs in por_uetr.items() if u in tob and tob[u]['registros'] != len(fs))
    resumen = c.resumen()
    resumen.update({'documentos_sin_una_fila_vigente': len(sin_vigente),
                    'documentos_con_otro_numero_de_registros': registros_distintos})
    resumen['cuadra'] = resumen['cuadra'] and not sin_vigente and not registros_distintos
    resultado.append(resumen)

    c = Comparacion('dbo.orden_pago (cada fila = un registro, T9) → decant.registro_orden', 'id_legado')
    leg = {f['id']: {'uetr': f['uetr'], 'fecha_registro': f['fecha_registro'], '_orden': f['id']} for f in ordenes}
    tob = {f['id_legado']: f for f in _filas(cursor_tobe, TOBE['registro_orden'])}
    _cruzar(c, leg, tob, [('uetr', 'uetr', ('uuid',)), ('fecha_registro', 'fecha_registro', ('T5_cdmx_llegada',))],
            pisos)
    resultado.append(c.resumen())

    # las filas REEMPLAZADA repiten el documento: si alguna entrada difiere, migrar sólo la vigente perdería datos
    reemplazadas = [f for f in ordenes if f['estatus'] == 'REEMPLAZADA']
    distintas = Counter()
    for f in reemplazadas:
        v = vigentes.get(f['uetr'].rstrip())
        for col in COL_DUPLICADAS:
            if v is None or texto(f[col]) != texto(v[col]):
                distintas[col] += 1
    resultado.append({'tabla': 'dbo.orden_pago (filas REEMPLAZADA = copias del documento)', 'llave': 'uetr',
                      'filas': len(reemplazadas), 'celdas': len(reemplazadas) * len(COL_DUPLICADAS),
                      'columnas_distintas_al_documento': dict(distintas), 'cuadra': not distintas,
                      'faltan': 0, 'sobran': 0})
    id_vigente = {f['id']: True for f in vigentes.values()}
    del ordenes, por_uetr, tob

    c = Comparacion('dbo.partida_solicitada → decant.partida_corresponsal (T4)', '(uetr, renglon)')
    leg = {(f['uetr'].rstrip(), f['renglon']): f for f in _filas(cursor_legado, LEGADO['partida_solicitada'])}
    tob = {(str(f['uetr']), f['renglon']): f for f in _filas(cursor_tobe, TOBE['partida_corresponsal'])}
    _cruzar(c, leg, tob, COL_PARTIDA_CORRESPONSAL)
    resultado.append(c.resumen())
    del leg, tob

    # partidas del cliente: las de la fila vigente se comparan; las de filas reemplazadas se RECONSTRUYEN
    liquidadas = _filas(cursor_legado, LEGADO['partida_liquidada'])
    for f in liquidadas:
        f['_orden'] = f['orden_id']
    tob = {(str(f['uetr']), f['renglon']): f for f in _filas(cursor_tobe, TOBE['partida_cliente'])}
    registro = {f['id_legado']: f['fecha_registro'] for f in _filas(cursor_tobe, TOBE['registro_orden'])}
    c = Comparacion('dbo.partida_liquidada (fila vigente) → decant.partida_cliente (T4)', '(uetr, renglon)')
    leg = {(f['uetr'].rstrip(), f['renglon']): f for f in liquidadas if f['orden_id'] in id_vigente}
    _cruzar(c, leg, tob, COL_PARTIDA_CLIENTE, pisos)
    resultado.append(c.resumen())
    reconstruibles, no = 0, []
    for f in liquidadas:
        if f['orden_id'] in id_vigente:
            continue
        actual = tob.get((f['uetr'].rstrip(), f['renglon']))
        fecha = registro.get(f['orden_id'])
        iguales = actual is not None and all(
            texto(aplicar(p, f[cl])) == texto(actual[ct]) for cl, ct, p in COL_PARTIDA_CLIENTE if cl != 'fecha_hora'
        ) and texto(aplicar(('T5_cdmx_llegada',), f['fecha_hora'], pisos[f['orden_id']][1])) == texto(fecha)
        if iguales:
            reconstruibles += 1
        else:
            no.append(f"{f['uetr']}/{f['renglon']}")
    resultado.append({'tabla': 'dbo.partida_liquidada (filas REEMPLAZADA) → reconstruibles de partida_cliente + '
                               'registro_orden', 'llave': '(uetr, renglon, registro)',
                      'filas': reconstruibles + len(no), 'reconstruibles': reconstruibles,
                      'no_reconstruibles': len(no), 'ejemplos': no[:5], 'cuadra': not no, 'faltan': len(no),
                      'sobran': 0})
    return resultado


# ── cuadre interno por lado: Σ partes = total del encabezado ─────────────────────────────────────────────────

# El lado del cliente es la tabla que la pantalla pinta en «Solicitado por el cliente» (T4, ver binding.py).
CUADRE_LEGADO = {
    'dbo.partida_liquidada': """
        SELECT p.uetr, p.monto, p.estatus,
               (SELECT SUM(monto) FROM dbo.partida_liquidada c WHERE c.orden_id = p.id AND c.concepto = 'PRINCIPAL'),
               (SELECT COUNT(*) FROM dbo.partida_liquidada c WHERE c.orden_id = p.id),
               (SELECT SUM(monto) FROM dbo.partida_solicitada s WHERE s.orden_id = p.id),
               (SELECT COUNT(*) FROM dbo.partida_solicitada s WHERE s.orden_id = p.id)
        FROM dbo.orden_pago p WHERE p.estatus <> 'REEMPLAZADA'""",
    # control negativo: los lados según el NOMBRE de la tabla (cruzados)
    'dbo.partida_solicitada': """
        SELECT p.uetr, p.monto, p.estatus,
               (SELECT SUM(monto) FROM dbo.partida_solicitada c WHERE c.orden_id = p.id AND c.concepto = 'PRINCIPAL'),
               (SELECT COUNT(*) FROM dbo.partida_solicitada c WHERE c.orden_id = p.id),
               (SELECT SUM(monto) FROM dbo.partida_liquidada s WHERE s.orden_id = p.id),
               (SELECT COUNT(*) FROM dbo.partida_liquidada s WHERE s.orden_id = p.id)
        FROM dbo.orden_pago p WHERE p.estatus <> 'REEMPLAZADA'""",
}
CUADRE_TOBE = """
    SELECT o.uetr, o.monto, o.estatus,
           (SELECT SUM(monto) FROM decant.partida_cliente c WHERE c.uetr = o.uetr AND c.concepto = 'PRINCIPAL'),
           (SELECT COUNT(*) FROM decant.partida_cliente c WHERE c.uetr = o.uetr),
           (SELECT SUM(monto) FROM decant.partida_corresponsal s WHERE s.uetr = o.uetr),
           (SELECT COUNT(*) FROM decant.partida_corresponsal s WHERE s.uetr = o.uetr)
    FROM decant.orden_pago o"""


def evaluar_cuadre(filas) -> dict:
    """Reglas por documento:
    - cliente: el principal = el monto del encabezado, y el desglose trae al menos principal, comisión e IVA;
    - corresponsal: Σ = monto si CONCILIADA; Σ ≠ monto si DIFERENCIA; con partidas si LIQUIDADA; sin partidas si
      ENVIADA o VENCIDA."""
    violaciones: Counter = Counter()
    ejemplos: dict[str, str] = {}
    n = 0
    for uetr, monto, estatus, principal, n_cliente, abonado, n_corresponsal in filas:
        n += 1
        reglas = {
            'cliente: principal ≠ total del encabezado': principal != monto,
            'cliente: desglose incompleto (< 3 partidas)': n_cliente < 3,
        }
        if estatus == 'CONCILIADA':
            reglas['corresponsal: CONCILIADA y Σ ≠ total'] = not n_corresponsal or abonado != monto
        elif estatus == 'DIFERENCIA':
            reglas['corresponsal: DIFERENCIA y Σ = total'] = not n_corresponsal or abonado == monto
        elif estatus == 'LIQUIDADA':
            reglas['corresponsal: LIQUIDADA sin partidas'] = not n_corresponsal
        else:
            reglas[f'corresponsal: {estatus} con partidas'] = bool(n_corresponsal)
        for regla, falla in reglas.items():
            if falla:
                violaciones[regla] += 1
                ejemplos.setdefault(regla, str(uetr).rstrip())
    return {'documentos': n, 'violaciones': dict(violaciones), 'ejemplos': ejemplos,
            'documentos_con_violacion': sum(violaciones.values()), 'cuadra': not violaciones}


def cuadre_legado(cursor, tabla_cliente: str) -> dict:
    cursor.execute(CUADRE_LEGADO[tabla_cliente])
    return evaluar_cuadre(cursor.fetchall())


def cuadre_tobe(cursor) -> dict:
    cursor.execute(CUADRE_TOBE)
    return evaluar_cuadre(cursor.fetchall())
