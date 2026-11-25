"""Mapeo columna por columna del legado al TO-BE y los PARCHES documentados (la única normalización permitida).

Cada columna del legado tiene exactamente un destino en el TO-BE o un motivo escrito para NO migrarse; cada columna
del TO-BE tiene un origen o está declarada como nueva. Lo usan la comparación de ESQUEMA (que caza la columna que
ningún reporte imprime, T6) y la comparación byte a byte (que aplica los parches y los cuenta).

Un parche es una transformación EXACTA con el predicado de su hallazgo, no una normalización amplia: sólo cambia los
valores que cumplen el predicado y deja todo lo demás como está, para que un defecto distinto en la misma columna
siga contando como diferencia. Cada parche declara su conteo esperado, que se mide en el ORIGEN en la misma corrida
(`paridad/migracion.py`), y tiene su control negativo. Las reglas para agregar uno están en `docs/parches.md`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from paridad.zonas import CDMX, NUEVA_YORK, a_utc


@dataclass(frozen=True)
class Parche:
    nombre: str
    decision: str          # ADR o regla que lo respalda
    descripcion: str       # el predicado, dicho en palabras


# Ronda 1 a ciegas, T3 (legado/TRAMPAS_CIEGAS.md y la ventana que midió la radiografía): una versión de la interfaz
# guardó la referencia con el relleno de su búfer de ancho fijo.
VENTANA_CIEGA1_T3 = (date(2022, 7, 4), date(2023, 1, 27))
ANCHO_CIEGA1_T3 = 35

PARCHES = {
    'char': Parche('char', 'tipo del legado', 'char(n): sólo si el valor mide exactamente n y lo que sobra al final '
                                              'son espacios; se quita ese relleno'),
    'T3_texto': Parche('T3_texto', 'ADR 0007', 'centinela: el texto exacto «NA» → NULL'),
    'T3_numero': Parche('T3_numero', 'ADR 0007', 'centinela: el número exacto 0 → NULL'),
    'T5_cdmx': Parche('T5_cdmx', 'ADR 0008', 'hora local de la Ciudad de México → instante UTC (hora repetida: '
                                             'primera ocurrencia)'),
    'T5_ny': Parche('T5_ny', 'ADR 0008', 'hora local de Nueva York → instante UTC'),
    'T5_cdmx_llegada': Parche('T5_cdmx_llegada', 'ADR 0008', 'como T5_cdmx, pero en la hora repetida decide el ORDEN '
                                                             'DE LLEGADA de las altas de órdenes (su identidad)'),
    'ciega1_T3': Parche('ciega1_T3', 'ADR 0007', 'referencia del corresponsal con fecha entre el 4-jul-2022 y el '
                                                 '27-ene-2023 (Nueva York), de exactamente 35 caracteres, cuyo final '
                                                 'son sólo espacios después de un último carácter que no es blanco: '
                                                 'se quita ese relleno'),
}


def _nombre(parche: str) -> tuple[str, int | None]:
    """'char:11' → ('char', 11)."""
    nombre, _, ancho = parche.partition(':')
    return nombre, int(ancho) if ancho else None


def parche_valido(parche: str) -> bool:
    """¿El parche existe y trae lo que necesita? (char exige su ancho)."""
    nombre, ancho = _nombre(parche)
    return nombre in PARCHES and (nombre != 'char' or (ancho is not None and ancho > 0))


def instante_no_antes_de(hora_local: datetime | None, zona, piso: datetime | None) -> datetime | None:
    """Hora local → instante; en la hora repetida, la primera ocurrencia que no quede antes de `piso`."""
    if hora_local is None:
        return None
    primera, segunda = a_utc(hora_local, zona, 0), a_utc(hora_local, zona, 1)
    if primera == segunda or piso is None or primera >= piso:
        return primera
    return segunda


def pisos_por_llegada(filas: list[dict]) -> dict:
    """id de cada fila de orden_pago → (piso de su registro, instante de su registro, piso de su envío). Recorre por
    identidad (orden de llegada): el piso del registro es el registro anterior; el del envío, el PRIMER registro de
    su documento (un re-registro repite el envío original y no sirve de piso)."""
    pisos, anterior, primero = {}, None, {}
    for fila in sorted(filas, key=lambda f: f['id']):
        registro = instante_no_antes_de(fila['fecha_registro'], CDMX, anterior)
        uetr = fila['uetr'].rstrip(' ')
        primero.setdefault(uetr, registro)
        pisos[fila['id']] = (anterior, registro, primero[uetr])
        anterior = registro
    return pisos


def relleno_fijo(valor: str, ancho: int) -> bool:
    """¿El valor mide exactamente `ancho` y termina en espacios después de un carácter que no es blanco?"""
    base = valor.rstrip(' ')
    return len(valor) == ancho and base != valor and (base == '' or not base[-1].isspace())


def en_ventana_ciega1_t3(fecha_hora: datetime | None) -> bool:
    return fecha_hora is not None and VENTANA_CIEGA1_T3[0] <= fecha_hora.date() <= VENTANA_CIEGA1_T3[1]


def aplicar(nombres: tuple[str, ...], valor, piso: datetime | None = None, fila: dict | None = None):
    """Aplica los parches en orden y devuelve el valor esperado en el TO-BE. `piso` lo usa T5_cdmx_llegada; `fila`
    (el renglón del legado), ciega1_T3 para su ventana de fechas. Lo que no cumple el predicado no se toca."""
    for parche in nombres:
        if valor is None:
            return None
        nombre, ancho = _nombre(parche)
        if nombre == 'char':
            if ancho is None:
                raise KeyError(f'{parche}: char necesita su ancho (char:n)')
            valor = valor.rstrip(' ') if relleno_fijo(valor, ancho) else valor
        elif nombre == 'ciega1_T3':
            fecha = (fila or {}).get('fecha_hora')
            if en_ventana_ciega1_t3(fecha) and relleno_fijo(valor, ANCHO_CIEGA1_T3):
                valor = valor.rstrip(' ')
        elif nombre == 'T3_texto':
            valor = None if valor == 'NA' else valor
        elif nombre == 'T3_numero':
            valor = None if Decimal(valor) == 0 else valor
        elif nombre == 'T5_cdmx':
            valor = a_utc(valor, CDMX)
        elif nombre == 'T5_ny':
            valor = a_utc(valor, NUEVA_YORK)
        elif nombre == 'T5_cdmx_llegada':
            valor = instante_no_antes_de(valor, CDMX, piso)
        else:
            raise KeyError(parche)
    return valor


@dataclass(frozen=True)
class Columna:
    destino: str | None              # columna del TO-BE (tabla.columna) o None si no se migra
    parches: tuple[str, ...] = ()
    motivo: str = ''                 # obligatorio si destino es None
    tipo_destino: str | None = None  # tipo esperado en el TO-BE (para el esquema)


@dataclass(frozen=True)
class Tabla:
    destino: str | None
    columnas: dict[str, Columna]
    motivo: str = ''
    llave_natural: tuple[str, ...] = ()
    notas: tuple[str, ...] = field(default_factory=tuple)


T = 'decant.'
MAPEO: dict[str, Tabla] = {
    'dbo.moneda': Tabla(T + 'moneda', {
        'codigo': Columna(T + 'moneda.codigo', ('char:3',)),
        'numerico': Columna(T + 'moneda.numerico', ('char:3',)),
        'nombre': Columna(T + 'moneda.nombre'),
        'decimales': Columna(T + 'moneda.decimales'),
        'activa': Columna(T + 'moneda.activa'),
    }, llave_natural=('codigo',)),
    'dbo.folio': Tabla(T + 'consecutivo', {
        'serie': Columna(T + 'consecutivo.serie'),
        'siguiente': Columna(T + 'consecutivo.siguiente'),
        'actualizado': Columna(None, motivo='inventario: sello GETDATE() del último consumo que nadie lee (veredicto '
                                            'de la radiografía); el corte se mide con MAX(id)'),
    }, llave_natural=('serie',)),
    'dbo.operacion': Tabla(T + 'operacion', {
        'id': Columna(T + 'operacion.id', tipo_destino='bigint'),
        'folio': Columna(T + 'operacion.folio'),
        'fecha_operacion': Columna(T + 'operacion.fecha_operacion', ('T5_cdmx',)),
        'sucursal': Columna(T + 'operacion.sucursal', ('char:4',)),
        'canal': Columna(T + 'operacion.canal'),
        'cliente': Columna(T + 'operacion.cliente'),
        'cuenta_clabe': Columna(T + 'operacion.cuenta_clabe', ('T3_texto',)),
        'tipo': Columna(T + 'operacion.tipo', ('char:1',)),
        'moneda': Columna(T + 'operacion.moneda', ('char:3',)),
        'monto_divisa': Columna(T + 'operacion.monto_divisa'),
        'tipo_cambio': Columna(T + 'operacion.tipo_cambio'),
        'tipo_cambio_referencia': Columna(T + 'operacion.tipo_cambio_referencia', ('T3_numero',)),
        'monto_mxn': Columna(T + 'operacion.monto_mxn'),
        'estatus': Columna(T + 'operacion.estatus'),
    }, llave_natural=('folio',)),
    'dbo.orden_pago': Tabla(T + 'orden_pago', {
        'id': Columna(T + 'registro_orden.id_legado', tipo_destino='bigint'),
        'operacion_id': Columna(T + 'orden_pago.operacion_id', tipo_destino='bigint'),
        'folio': Columna(T + 'orden_pago.folio'),
        'uetr': Columna(T + 'orden_pago.uetr', tipo_destino='uuid'),
        'referencia_mt103': Columna(T + 'orden_pago.referencia_mt103'),
        'fecha_registro': Columna(T + 'registro_orden.fecha_registro', ('T5_cdmx_llegada',)),
        'fecha_envio': Columna(T + 'orden_pago.fecha_envio', ('T5_cdmx_llegada',)),
        'fecha_valor': Columna(T + 'orden_pago.fecha_valor'),
        'bic_corresponsal': Columna(T + 'orden_pago.bic_corresponsal', ('char:11',)),
        'bic_intermediario': Columna(T + 'orden_pago.bic_intermediario', ('char:11', 'T3_texto')),
        'beneficiario': Columna(T + 'orden_pago.beneficiario'),
        'cuenta_beneficiario': Columna(T + 'orden_pago.cuenta_beneficiario'),
        'moneda': Columna(T + 'orden_pago.moneda', ('char:3',)),
        'monto': Columna(T + 'orden_pago.monto'),
        'gastos': Columna(T + 'orden_pago.gastos', ('char:3',)),
        'codigo_proposito': Columna(T + 'orden_pago.codigo_proposito', ('char:4',)),
        'estatus': Columna(T + 'orden_pago.estatus'),
        'horas_liquidacion': Columna(T + 'orden_pago.horas_liquidacion'),
    }, llave_natural=('uetr',), notas=(
        'Un DOCUMENTO por UETR: la fila vigente (estatus <> REEMPLAZADA) va a orden_pago; cada fila del legado (cada '
        'alta o re-registro, T9) va a registro_orden con su id y su fecha_registro.',)),
    # T4: el NOMBRE miente. La pantalla pinta partida_solicitada en «Liquidado por el corresponsal».
    'dbo.partida_solicitada': Tabla(T + 'partida_corresponsal', {
        'id': Columna(None, motivo='llave interna; la partida se cruza por (uetr, renglón)'),
        'orden_id': Columna(T + 'partida_corresponsal.uetr', tipo_destino='uuid'),
        'renglon': Columna(T + 'partida_corresponsal.renglon'),
        'concepto': Columna(T + 'partida_corresponsal.concepto'),
        'moneda': Columna(T + 'partida_corresponsal.moneda', ('char:3',)),
        'monto': Columna(T + 'partida_corresponsal.monto'),
        'fecha_hora': Columna(T + 'partida_corresponsal.fecha_hora', ('T5_ny',)),
        'referencia': Columna(T + 'partida_corresponsal.referencia', ('ciega1_T3',)),
    }, llave_natural=('uetr', 'renglon')),
    'dbo.partida_liquidada': Tabla(T + 'partida_cliente', {
        'id': Columna(None, motivo='llave interna; la partida se cruza por (uetr, renglón)'),
        'orden_id': Columna(T + 'partida_cliente.uetr', tipo_destino='uuid'),
        'renglon': Columna(T + 'partida_cliente.renglon'),
        'concepto': Columna(T + 'partida_cliente.concepto'),
        'moneda': Columna(T + 'partida_cliente.moneda', ('char:3',)),
        'monto': Columna(T + 'partida_cliente.monto'),
        'fecha_hora': Columna(T + 'partida_cliente.fecha_hora', ('T5_cdmx_llegada',)),
        'referencia': Columna(T + 'partida_cliente.referencia'),
    }, llave_natural=('uetr', 'renglon'), notas=(
        'Las partidas de las filas REEMPLAZADA no se migran: son copia de las del documento con la fecha de su '
        'registro (que sí vive en registro_orden). La verificación lo demuestra reconstruyéndolas.',)),
    'dbo.bitacora': Tabla(None, {
        c: Columna(None, motivo='retención') for c in
        ('id', 'tabla', 'llave', 'accion', 'estatus_anterior', 'estatus_nuevo', 'usuario', 'fecha')
    }, motivo='retención: bitácora de trigger, no se migra como tabla viva (veredicto de la radiografía); es fuente '
              'del replay (noches) y del arbitraje de «sólo marca»'),
}

# Columnas del TO-BE sin origen en el legado: cada una con su razón.
NUEVAS = {
    T + 'orden_pago.registros': 'cuántas veces dio de alta el documento la interfaz (T9)',
    T + 'orden_pago.fecha_registro': 'la fecha del registro más reciente (gana el más reciente, T9)',
    T + 'orden_pago.version_reglas': 'versión de las reglas que dejó el resultado (invariante del reproceso)',
    T + 'registro_orden.uetr': 'documento del registro',
    T + 'registro_orden.numero': 'orden del registro dentro del documento',
    T + 'liquidacion_descartada.*': 'D3 visible: la confirmación que el legado tiraba en silencio',
    T + 'marca.*': 'evidencia del modo «sólo marca»',
    T + 'corrida.*': 'qué carga o replay dejó el estado, con qué reglas y banderas',
    T + '__historial_migraciones.*': 'historial de migraciones de EF Core',
}


def destinos() -> dict[str, tuple[str, str]]:
    """Columna del TO-BE → (tabla.columna del legado) que la alimenta."""
    resultado = {}
    for tabla, mapeo in MAPEO.items():
        for columna, c in mapeo.columnas.items():
            if c.destino:
                resultado.setdefault(c.destino, (tabla, columna))
    return resultado


def validar() -> list[str]:
    """Errores del propio mapeo: columnas sin destino ni motivo, o parches que no existen."""
    errores = []
    for tabla, mapeo in MAPEO.items():
        for columna, c in mapeo.columnas.items():
            if c.destino is None and not (c.motivo or mapeo.motivo):
                errores.append(f'{tabla}.{columna}: no se migra y no dice por qué')
            for p in c.parches:
                if not parche_valido(p):
                    errores.append(f'{tabla}.{columna}: parche desconocido o sin su ancho: {p}')
    return errores
