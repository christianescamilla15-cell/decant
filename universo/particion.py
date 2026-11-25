"""Partición del legado POR COLUMNA: qué es entrada (universo) y qué es resultado (oráculo).

En una misma tabla conviven las dos cosas: en `orden_pago`, el monto, las fechas y los BIC entran de fuera, mientras
el estatus y las horas de liquidación los calcula el legado. El replay de S2 se alimenta SÓLO de las columnas de
`entrada` (más los archivos de interfaz y las noches del job). Las de `resultado` son lo que se compara.

- `llave_interna`: la asigna la identidad; no se compara directo, se cruza por llave natural.
- `entrada`: viene de fuera. El texto dice de dónde y, si el legado la transforma al guardarla, cómo.
- `resultado`: la calcula el código del legado (procedimiento, trigger o job). El texto dice cuál.
- `mixta`: depende del caso; el texto da la regla.
"""
from __future__ import annotations

PARTICION: dict[str, dict[str, dict[str, str]]] = {
    'dbo.moneda': {
        'entrada': {
            'codigo': 'catálogo ISO 4217',
            'numerico': 'catálogo ISO 4217',
            'nombre': 'catálogo',
            'decimales': 'catálogo ISO 4217 (el legado no lo aplica: D2)',
            'activa': 'mantenimiento del catálogo (alta y baja manual, sin fecha)',
        },
    },
    'dbo.folio': {
        'entrada': {'serie': 'catálogo de series'},
        'resultado': {
            'siguiente': 'consumible: cada alta lo avanza (sp_registrar_operacion, sp_registrar_orden)',
            'actualizado': 'GETDATE() del último alta',
        },
    },
    'dbo.operacion': {
        'llave_interna': {'id': 'identidad'},
        'entrada': {
            'fecha_operacion': 'front o archivo de sucursales; hora LOCAL al minuto (en ARCHIVO, a la hora)',
            'sucursal': 'front o archivo de sucursales',
            'canal': 'front o archivo de sucursales',
            'cliente': 'front; en ARCHIVO el archivo de sucursales lo trae sano (el legado lo leyó como latin-1: T7)',
            'cuenta_clabe': 'front; sin cuenta llega NULL y el legado guarda «NA» (T3)',
            'tipo': 'front',
            'moneda': 'front',
            'monto_divisa': 'front',
            'tipo_cambio_referencia': 'front; sin referencia llega NULL y el legado guarda 0 (T3)',
            'estatus': 'front (la cancelación la marca la sucursal)',
        },
        'resultado': {
            'folio': 'consumible FX (sp_registrar_operacion)',
            'monto_mxn': 'ROUND(monto_divisa × tipo_cambio, 2) (sp_registrar_operacion)',
        },
        'mixta': {
            'tipo_cambio': 'entrada si el cajero lo teclea (tipo_cambio_referencia = 0); si no, resultado: '
                           'referencia × 1.0035 en venta, × 0.9965 en compra (sp_registrar_operacion)',
        },
    },
    'dbo.orden_pago': {
        'llave_interna': {'id': 'identidad (cambia en cada re-registro: T9)'},
        'entrada': {
            'uetr': 'interfaz de órdenes; LLAVE NATURAL del documento',
            'referencia_mt103': 'interfaz de órdenes (:20: de nuestro MT103)',
            'fecha_registro': 'interfaz de órdenes: hora del alta o del re-registro de cada mañana',
            'fecha_envio': 'interfaz de órdenes, hora local',
            'fecha_valor': 'interfaz de órdenes',
            'bic_corresponsal': 'interfaz de órdenes',
            'bic_intermediario': 'interfaz de órdenes; sin intermediario llega NULL y el legado guarda «NA» (T3)',
            'beneficiario': 'interfaz de órdenes',
            'cuenta_beneficiario': 'interfaz de órdenes',
            'moneda': 'interfaz de órdenes',
            'monto': 'interfaz de órdenes',
            'gastos': 'interfaz de órdenes (:71A: OUR/SHA/BEN)',
            'codigo_proposito': 'interfaz de órdenes (pacs.008 Purp/Cd); ningún módulo la lee (T6)',
        },
        'resultado': {
            'operacion_id': 'id interno de la operación que originó la orden',
            'folio': 'consumible OP (sp_registrar_orden); el re-registro lo conserva',
            'estatus': 'máquina de estados: alta y re-registro (sp_registrar_orden), liquidación '
                       '(sp_registrar_liquidacion), conciliación y vencimiento con GETDATE() (sp_conciliar: T8)',
            'horas_liquidacion': 'sp_conciliar con desfase fijo de una hora (T5)',
        },
    },
    'dbo.partida_solicitada': {        # el nombre miente: es lo que LIQUIDÓ el corresponsal (T4)
        'llave_interna': {'id': 'identidad'},
        'entrada': {
            'monto': 'buzón del corresponsal: :32A: (abono) o :71F: (gastos)',
            'fecha_hora': 'buzón del corresponsal: :13D: SIN su desfase UTC',
            'referencia': 'buzón del corresponsal: :20: (la referencia propia del corresponsal)',
        },
        'resultado': {
            'orden_id': 'sp_registrar_liquidacion: TOP 1 por uetr y estatus ENVIADA',
            'renglon': 'sp_registrar_liquidacion: 1 el abono, 2 los gastos',
            'concepto': 'sp_registrar_liquidacion: ABONO o COMISION_CORRESPONSAL según el campo',
            'moneda': 'sp_registrar_liquidacion: la de la ORDEN, no la del mensaje',
        },
    },
    'dbo.partida_liquidada': {         # el nombre miente: es lo que SOLICITÓ el cliente (T4)
        'llave_interna': {'id': 'identidad'},
        'resultado': {
            'orden_id': 'sp_registrar_orden (cada re-registro la repite)',
            'renglon': 'sp_registrar_orden',
            'concepto': 'sp_registrar_orden: PRINCIPAL, COMISION, IVA y GASTOS_OUR',
            'moneda': 'sp_registrar_orden',
            'monto': 'sp_registrar_orden: el principal copia la orden; la comisión TRUNCA (D1); IVA 16 %; '
                     'GASTOS_OUR 25 USD fijos',
            'fecha_hora': 'sp_registrar_orden: la fecha_registro de la orden',
            'referencia': 'sp_registrar_orden: el folio de la orden',
        },
    },
    'dbo.bitacora': {
        'llave_interna': {'id': 'identidad'},
        'resultado': {
            'tabla': 'tr_orden_pago_bitacora',
            'llave': 'tr_orden_pago_bitacora',
            'accion': 'tr_orden_pago_bitacora',
            'estatus_anterior': 'tr_orden_pago_bitacora',
            'estatus_nuevo': 'tr_orden_pago_bitacora',
            'usuario': 'SUSER_SNAME() de quien escribió (svc_interfaz, svc_swift, svc_agente)',
            'fecha': 'GETDATE() del servidor; con usuario svc_agente es la NOCHE del job (universo del reloj)',
        },
    },
}

# Lo que entra al replay además de las columnas de entrada.
UNIVERSO_FUERA_DE_TABLAS = {
    'noches del job': 'horario del job en msdb (todas las noches a las 23:30) y sellos svc_agente de '
                      'bitacora.fecha: el reloj que se inyecta al replay (T8) y el orden entre una llegada y el '
                      'vencimiento (D3)',
    'buzón del corresponsal': 'legado/datos/interfaces/corresponsal/*.fin: todas las confirmaciones, también las '
                              'que el legado descartó (D3), con la hora de Nueva York y su desfase (T5)',
    'archivo de sucursales': 'legado/datos/interfaces/sucursales/*.csv: el canal ARCHIVO en UTF-8 sano (T7), con '
                             'su referencia natural y los reenvíos tardíos',
}

CATEGORIAS = ('llave_interna', 'entrada', 'resultado', 'mixta')


def columnas_de(tabla: str, categoria: str) -> list[str]:
    return list(PARTICION[tabla].get(categoria, {}))


def validar(esquema: dict[str, list[str]]) -> list[str]:
    """Errores de la partición frente al esquema real: cada columna en UNA sola categoría, ninguna de más."""
    errores = []
    for tabla, columnas in esquema.items():
        if tabla not in PARTICION:
            errores.append(f'{tabla}: la tabla no está en la partición')
            continue
        vistas: dict[str, str] = {}
        for categoria in CATEGORIAS:
            for columna in PARTICION[tabla].get(categoria, {}):
                if columna in vistas:
                    errores.append(f'{tabla}.{columna}: está en {vistas[columna]} y en {categoria}')
                vistas[columna] = categoria
        for columna in columnas:
            if columna not in vistas:
                errores.append(f'{tabla}.{columna}: sin categoría')
        for columna in vistas:
            if columna not in columnas:
                errores.append(f'{tabla}.{columna}: no existe en el esquema')
    return errores
