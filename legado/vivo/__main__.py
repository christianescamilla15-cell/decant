"""Legado «vivo» barato: inyecta el delta del MISMO día después del respaldo, por los procedimientos del legado.

    python -m legado.vivo                       # usa legado/datos/delta_<fecha>.json que dejó `legado cargar`

Fases (en hora local del día del respaldo):
  1. delta: operaciones nuevas, órdenes, RE-REGISTROS de la mañana (mismo documento, otra llave interna),
     liquidaciones del corresponsal y cambios de catálogo; los folios (consumibles) avanzan solos.
  2. congelamiento: se anotan los totales, el MAX(id) de cada tabla y el instante del servidor (GETDATE()).
  3. posterior al congelamiento: el legado SIGUE escribiendo un rato (lo que el barrido posterior al corte debe
     clasificar como duplicado huérfano o como pérdida).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from legado.conexion import RAIZ, conectar

TABLAS = ('moneda', 'folio', 'operacion', 'orden_pago', 'partida_solicitada', 'partida_liquidada', 'bitacora')

_OPERACION = """DECLARE @id int;
EXEC dbo.sp_registrar_operacion @fecha_operacion = %s, @sucursal = %s, @canal = %s, @cliente = %s,
     @cuenta_clabe = %s, @tipo = %s, @moneda = %s, @monto_divisa = %s, @tipo_cambio_referencia = %s,
     @tipo_cambio = %s, @id = @id OUTPUT;
SELECT @id;"""
_ORDEN = """DECLARE @id int;
EXEC dbo.sp_registrar_orden @operacion_id = %s, @uetr = %s, @referencia_mt103 = %s, @fecha_registro = %s,
     @fecha_envio = %s, @fecha_valor = %s, @bic_corresponsal = %s, @bic_intermediario = %s, @beneficiario = %s,
     @cuenta_beneficiario = %s, @moneda = %s, @monto = %s, @gastos = %s, @codigo_proposito = %s, @id = @id OUTPUT;
SELECT @id;"""
_LIQUIDACION = """EXEC dbo.sp_registrar_liquidacion @uetr = %s, @referencia = %s, @fecha_hora = %s, @abono = %s,
     @comision = %s;"""
_ALTA_MONEDA = 'INSERT INTO dbo.moneda (codigo, numerico, nombre, decimales, activa) VALUES (%s, %s, %s, %s, 1)'
_BAJA_MONEDA = 'UPDATE dbo.moneda SET activa = 0 WHERE codigo = %s'


def instante_servidor(cursor) -> str:
    """GETDATE() del servidor con sus milésimas (estilo 121): el reloj con el que sella la bitácora."""
    cursor.execute('SELECT CONVERT(varchar(23), GETDATE(), 121)')
    return cursor.fetchone()[0]


def foto(cursor, espera: float = 0.005) -> dict:
    """COUNT y MAX(id) de cada tabla y el instante del servidor: lo que el corte vería en este instante.

    El instante es el límite del camino por sellos (S3, criterio 3): lo escrito antes de la foto sella con un instante
    menor o igual, y la foto no regresa hasta que el reloj del servidor AVANZA, para que lo escrito después selle con
    uno mayor (la bitácora guarda `datetime`, con tics de 1/300 s: sin la espera, dos escrituras pueden empatar)."""
    instante = instante_servidor(cursor)
    resultado: dict = {'servidor': instante}
    for tabla in TABLAS:
        cursor.execute(
            "DECLARE @t nvarchar(300) = N'dbo.' + QUOTENAME(%s); "
            "DECLARE @sql nvarchar(max) = N'SELECT COUNT_BIG(*), ' + CASE WHEN COLUMNPROPERTY(OBJECT_ID(@t), 'id', "
            "'IsIdentity') = 1 THEN N'MAX(id)' ELSE N'NULL' END + N' FROM ' + @t; EXEC sp_executesql @sql",
            (tabla,))
        filas, maximo = cursor.fetchone()
        resultado[tabla] = {'filas': filas, 'max_id': maximo}
    cursor.execute('SELECT serie, siguiente FROM dbo.folio ORDER BY serie')
    resultado['folios'] = {serie.strip(): siguiente for serie, siguiente in cursor.fetchall()}
    # El catálogo completo (S3 paso 4): no tiene bitácora, así que el delta toma las monedas de ESTA foto y lo que
    # cambie después queda para el barrido posterior al corte.
    cursor.execute('SELECT codigo, numerico, nombre, decimales, activa FROM dbo.moneda ORDER BY codigo')
    resultado['catalogo'] = {'moneda': [[c, n, nombre, int(d), bool(a)] for c, n, nombre, d, a in cursor.fetchall()]}
    while instante_servidor(cursor) <= instante:       # estilo 121: ancho fijo, se compara como texto
        time.sleep(espera)
    return resultado


def choques(cursor, delta: dict, inicio: dict, congelamiento: dict) -> dict:
    """Lo que S3 tendrá que arbitrar: altas fechadas hacia atrás, documentos que también capturará el TO-BE y folios
    OP que el legado siguió usando después del congelamiento."""
    cursor.execute('SELECT id, folio, fecha_operacion, canal, sucursal FROM dbo.operacion '
                   'WHERE id > %s AND fecha_operacion < %s ORDER BY id',
                   (inicio['operacion']['max_id'], delta['fecha_negocio']))
    hacia_atras = [{'id': i, 'folio': f, 'fecha_operacion': str(fo), 'canal': c, 'sucursal': s}
                   for i, f, fo, c, s in cursor.fetchall()]
    cursor.execute('SELECT id, uetr, folio, fecha_registro FROM dbo.orden_pago WHERE id > %s ORDER BY id',
                   (congelamiento['orden_pago']['max_id'],))
    tras_congelar = [{'id': i, 'uetr': u, 'folio': f, 'fecha_registro': str(fr)} for i, u, f, fr in cursor.fetchall()]
    tambien_tobe = set(delta.get('choques', {}).get('tobe_tambien_captura', []))
    return {
        'altas_fechadas_hacia_atras': {
            'regla': 'ids mayores al MAX(id) del respaldo con fecha de negocio ANTERIOR al corte: un delta por fecha '
                     'las pierde; uno por id o por bitácora, no',
            'filas': hacia_atras},
        'documentos_tambien_en_tobe': {
            'regla': 'el legado los registró después del congelamiento y el TO-BE también los capturará (mismo '
                     'uetr): migrarlos duplica (huérfano) y no migrarlos sólo es seguro si el TO-BE los tiene',
            'filas': [f for f in tras_congelar if f['uetr'] in tambien_tobe]},
        'folios_op_tras_congelamiento': {
            'regla': f"el TO-BE numera desde OP {congelamiento['folios']['OP']} (el siguiente al congelamiento); el "
                     'legado siguió usando estos folios: colisión',
            'siguiente_al_congelamiento': congelamiento['folios']['OP'],
            'folios': sorted({f['folio'] for f in tras_congelar})},
    }


def ejecutar(paso: dict, cursor, ids_operacion: dict[str, int]) -> int | None:
    a = paso['args']
    accion = paso['accion']
    if accion == 'operacion':
        cursor.execute(_OPERACION, (a['fecha_operacion'], a['sucursal'], a['canal'], a['cliente'], a['cuenta_clabe'],
                                    a['tipo'], a['moneda'], a['monto_divisa'], a['tipo_cambio_referencia'],
                                    a['tipo_cambio']))
        nuevo = cursor.fetchone()[0]
        ids_operacion[paso['ref']] = nuevo
        return nuevo
    if accion == 'orden':
        operacion = a['operacion_id']
        if isinstance(operacion, str):
            operacion = ids_operacion[operacion]
        cursor.execute(_ORDEN, (operacion, a['uetr'], a['referencia_mt103'], a['fecha_registro'], a['fecha_envio'],
                                a['fecha_valor'], a['bic_corresponsal'], a['bic_intermediario'], a['beneficiario'],
                                a['cuenta_beneficiario'], a['moneda'], a['monto'], a['gastos'],
                                a['codigo_proposito']))
        return cursor.fetchone()[0]
    if accion == 'liquidacion':
        cursor.execute(_LIQUIDACION, (a['uetr'], a['referencia'], a['fecha_hora'], a['abono'], a['comision']))
        return None
    if accion == 'alta_moneda':
        cursor.execute(_ALTA_MONEDA, (a['codigo'], a['numerico'], a['nombre'], a['decimales']))
        return None
    if accion == 'baja_moneda':
        cursor.execute(_BAJA_MONEDA, (a['codigo'],))
        return None
    raise ValueError(f'acción desconocida: {accion}')


def inyectar(ruta: Path) -> dict:
    delta = json.loads(ruta.read_text(encoding='utf-8'))
    pasos = delta['pasos']
    ids_operacion: dict[str, int] = {}
    conteo: dict[str, dict[str, int]] = {'delta': {}, 'posterior_congelamiento': {}}
    reregistros = {'delta': 0, 'posterior_congelamiento': 0}
    with conectar() as conexion:
        cursor = conexion.cursor()
        inicio = foto(cursor)
        congelamiento = None
        for paso in pasos:
            fase = paso['fase']
            if fase == 'posterior_congelamiento' and congelamiento is None:
                congelamiento = foto(cursor)
            ejecutar(paso, cursor, ids_operacion)
            conteo[fase][paso['accion']] = conteo[fase].get(paso['accion'], 0) + 1
            if paso['accion'] == 'orden' and paso['args'].get('reregistro'):
                reregistros[fase] += 1
        if congelamiento is None:
            congelamiento = foto(cursor)
        final = foto(cursor)
        para_s3 = choques(cursor, delta, inicio, congelamiento)
    registro = {'fecha_negocio': delta['fecha_negocio'], 'congelamiento_utc': delta['congelamiento_utc'],
                'llamadas': conteo, 're_registros': reregistros, 'al_respaldo': inicio,
                'al_congelamiento': congelamiento, 'al_terminar': final, 'choques': para_s3}
    destino = ruta.with_name(f"vivo_{delta['fecha_negocio']}.json")
    destino.write_text(json.dumps(registro, indent=2) + '\n', encoding='utf-8')
    registro['ruta'] = str(destino)
    return registro


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m legado.vivo', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--delta', type=Path, help='guion del delta (por omisión, el único en legado/datos)')
    args = parser.parse_args(argv)
    ruta = args.delta
    if ruta is None:
        candidatos = sorted((RAIZ / 'datos').glob('delta_*.json'))
        if not candidatos:
            raise SystemExit('No hay guion del delta: corre antes `python -m legado cargar`.')
        ruta = candidatos[-1]
    r = inyectar(ruta)
    for fase, llamadas in r['llamadas'].items():
        print(f"{fase}: " + ', '.join(f'{n} {accion}' for accion, n in llamadas.items())
              + f" · re-registros {r['re_registros'][fase]}")
    for tabla in TABLAS:
        a, c, f = r['al_respaldo'][tabla], r['al_congelamiento'][tabla], r['al_terminar'][tabla]
        print(f"  {tabla:20s} respaldo {a['filas']:>9,} · congelamiento {c['filas']:>9,} · final {f['filas']:>9,}")
    c = r['choques']
    print(f"  para S3: {len(c['altas_fechadas_hacia_atras']['filas'])} altas fechadas hacia atrás · "
          f"{len(c['documentos_tambien_en_tobe']['filas'])} documentos que también capturará el TO-BE · "
          f"{len(c['folios_op_tras_congelamiento']['folios'])} folios OP usados tras el congelamiento")
    print(f"registro: {r['ruta']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
