"""PARIDAD DE REPORTE: el reporte de órdenes del TO-BE (en sombra, con TODO el universo) contra el que el legado
PUBLICÓ al tomar el respaldo, fila por fila y por llave natural (uetr, concepto).

- **Orden por inversiones:** los pares con distinta fecha valor son contrato (`ORDER BY fecha_valor`) y deben dar 0;
  los empatados se juzgan contra el PISO de la misma corrida: el propio legado, re-corrido sobre el respaldo
  restaurado, contra lo que publicó. Si el legado no se repite a sí mismo (piso > 0), el orden de los empates no es
  contrato.
- **Arbitraje** de cada diferencia (renglón o celda) con `paridad/arbitraje.py`. El avance de producción se clasifica
  contra el corte MEDIDO y se audita en el legado VIVO: la misma partida existe allá con identidad mayor al corte.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from legado.generador.zonas import CDMX, NUEVA_YORK
from paridad import arbitraje, formato
from radiografia import cuadre, orden

LLAVE = ('uetr', 'concepto')
ZONA_DE = {'fecha_envio': CDMX, 'fecha_partida': NUEVA_YORK}
L_VIVO_PARTIDA = ('SELECT s.id, s.monto FROM dbo.partida_solicitada s JOIN dbo.orden_pago p ON p.id = s.orden_id '
                  'WHERE p.uetr = %s AND s.concepto = %s')
L_VIVO_ORDEN = ("SELECT TOP 1 estatus FROM dbo.orden_pago WHERE uetr = %s AND estatus <> 'REEMPLAZADA' "
                'ORDER BY id DESC')


def _indices(columnas: list[str], nombres) -> list[int]:
    return [columnas.index(n) for n in nombres]


def piso(cursor, publicada: dict, carpeta: Path) -> dict:
    """El legado re-corrido sobre el respaldo restaurado contra lo que publicó, EN ESTA corrida."""
    columnas, capturada = formato.leer(carpeta / publicada['archivo'])
    columnas_re, recorrida = cuadre.recorrer(cursor, publicada['procedimiento'], publicada['parametros'],
                                             publicada['conjunto'])
    if columnas_re != columnas:
        raise SystemExit('el reporte re-corrido no tiene las columnas del publicado')
    medida = orden.comparar([tuple(f) for f in capturada], [tuple(f) for f in recorrida],
                            _indices(columnas, LLAVE), _indices(columnas, publicada['llave_orden']))
    return medida


def _local(valor: str, zona) -> tuple[str, bool]:
    """'2023-12-01T10:15:00-06:00' → ('2023-12-01 10:15:00', ¿el desfase es el de la zona en ese instante?)."""
    instante = datetime.fromisoformat(valor)
    en_zona = instante.astimezone(zona)
    return en_zona.replace(tzinfo=None).isoformat(sep=' '), en_zona.utcoffset() == instante.utcoffset()


def arbitros(corte: dict, vivo, eventos: dict) -> list[arbitraje.Arbitro]:
    corte_utc = datetime.fromisoformat(corte['instante_utc'])
    max_partida = corte['tablas']['dbo.partida_solicitada']['max_id']

    def audita_avance(d: arbitraje.Diferencia) -> tuple[bool, str]:
        instante = d.contexto['instante_evento']
        if instante <= corte_utc:
            return False, f'el evento ({instante.isoformat()}) no es posterior al corte'
        if vivo is None:
            return False, 'sin legado vivo para auditar'
        cursor = vivo.cursor()
        uetr, concepto = d.contexto['uetr'], d.contexto['concepto']
        if d.regla == 'renglon':
            cursor.execute(L_VIVO_PARTIDA, (uetr, concepto))
            filas = cursor.fetchall()
            ok = len(filas) == 1 and filas[0][0] > max_partida and str(filas[0][1]) == d.contexto['monto']
            return ok, (f'evento {instante.isoformat()} > corte; legado vivo: {filas} (id > {max_partida} = '
                        f'posterior al corte por identidad)')
        cursor.execute(L_VIVO_ORDEN, (uetr,))
        fila = cursor.fetchone()
        ok = fila is not None and fila[0] == d.tobe
        return ok, f'evento {instante.isoformat()} > corte; el legado vivo llegó a {fila and fila[0]}'

    def audita_hora(d: arbitraje.Diferencia) -> tuple[bool, str]:
        local, desfase_ok = _local(d.tobe, ZONA_DE[d.regla])
        return local == d.legado and desfase_ok, f'hora local {local}; desfase de la zona: {desfase_ok}'

    return [
        arbitraje.Arbitro(
            'avance', arbitraje.AVANCE, 'corte medido (paridad/corte.py)',
            'el TO-BE ya vio una confirmación del corresponsal posterior al corte',
            aplica=lambda d: d.contexto.get('instante_evento') is not None
            and d.contexto['instante_evento'] > corte_utc,
            audita=audita_avance),
        arbitraje.Arbitro(
            'hora-local-sin-zona', arbitraje.REGLA, 'ADR 0008',
            'el legado publica la hora LOCAL sin zona (la nuestra de la Ciudad de México, la del corresponsal de '
            'Nueva York); el TO-BE publica la misma hora con su desfase y no replica el formato',
            aplica=lambda d: d.regla in ZONA_DE and d.tobe is not None and d.legado is not None,
            audita=audita_hora),
    ]


def comparar(publicada: dict, carpeta: Path, ruta_tobe: Path, piso_medido: dict, corte: dict, vivo,
             eventos: dict) -> dict:
    columnas, legado = formato.leer(carpeta / publicada['archivo'])
    columnas_t, tobe = formato.leer(ruta_tobe)
    if columnas_t != columnas:
        raise SystemExit(f'el reporte del TO-BE no tiene las columnas del publicado: {columnas_t}')
    i_llave = _indices(columnas, LLAVE)
    leg = {tuple(f[i] for i in i_llave): f for f in legado}
    tob = {tuple(f[i] for i in i_llave): f for f in tobe}
    if len(leg) != len(legado) or len(tob) != len(tobe):
        raise SystemExit('la llave natural (uetr, concepto) se repite en un reporte')

    diferencias: list[arbitraje.Diferencia] = []
    renglones_distintos = set()
    for llave, fila in tob.items():
        contexto = {'uetr': llave[0], 'concepto': llave[1], 'monto': fila[columnas.index('monto_partida')],
                    'instante_evento': eventos.get(llave[0])}
        if llave not in leg:
            diferencias.append(arbitraje.Diferencia('renglon', '/'.join(llave), None, 'sólo en el TO-BE', contexto))
            continue
        for i, col in enumerate(columnas):
            if fila[i] != leg[llave][i]:
                renglones_distintos.add(llave)
                diferencias.append(arbitraje.Diferencia(col, '/'.join(llave), leg[llave][i], fila[i], contexto))
    for llave in leg:
        if llave not in tob:
            diferencias.append(arbitraje.Diferencia('renglon', '/'.join(llave), 'sólo en el legado', None,
                                                    {'uetr': llave[0], 'concepto': llave[1]}))

    comunes = [k for k in leg if k in tob]
    i_orden = columnas.index('fecha_valor')
    proyeccion_l = [(k[0], k[1], leg[k][i_orden]) for k in (tuple(f[i] for i in i_llave) for f in legado)
                    if k in tob]
    proyeccion_t = [(k[0], k[1], tob[k][i_orden]) for k in (tuple(f[i] for i in i_llave) for f in tobe)
                    if k in leg]
    medida = orden.comparar(proyeccion_l, proyeccion_t, [0, 1], [2])
    contrato_ok = medida['inversiones_contrato'] == 0
    empates_libres = piso_medido['pct_empatados_invertidos'] > 0
    arbitrado = arbitraje.arbitrar(diferencias, arbitros(corte, vivo, eventos))
    por_tipo = {'renglones_solo_tobe': len(tob) - len(comunes), 'renglones_solo_legado': len(leg) - len(comunes),
                'renglones_comunes': len(comunes), 'renglones_comunes_con_celdas_distintas': len(renglones_distintos)}
    return {
        'publicado': {'archivo': publicada['archivo'], 'sha256': publicada['sha256'], 'renglones': len(legado)},
        'tobe': {'renglones': len(tobe)}, **por_tipo,
        'orden': {'tobe_contra_publicado': medida, 'piso_misma_corrida': piso_medido,
                  'contrato_en_cero': contrato_ok, 'empates_libres': empates_libres,
                  'veredicto': ('contrato en 0; los empates no son contrato: el propio legado invierte '
                                f"{piso_medido['pct_empatados_invertidos']} % de sus pares empatados en esta "
                                f"corrida y el TO-BE {medida['pct_empatados_invertidos']} %")
                  if contrato_ok and empates_libres else 'REVISAR: contrato roto o empates que el legado sí repite'},
        'arbitraje': arbitrado,
        'cumple': contrato_ok and empates_libres and arbitrado['por_categoria'][arbitraje.DEFECTO] == 0,
    }


def eventos_posteriores(universo: Path, corte_utc: datetime) -> dict[str, datetime]:
    """UETR → instante de su confirmación en el buzón, si es POSTERIOR al corte (lo único que puede ser avance)."""
    from universo.interfaces import leer_buzon
    resultado = {}
    for archivo in sorted((universo / 'interfaces' / 'corresponsal').glob('*.fin')):
        for c in leer_buzon(archivo.read_text(encoding='utf-8')):
            if c.instante_utc > corte_utc:
                resultado[c.uetr] = c.instante_utc.astimezone(timezone.utc)
    return resultado

