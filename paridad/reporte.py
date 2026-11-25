"""PARIDAD DE REPORTE: el reporte de órdenes del TO-BE (en sombra, con TODO el universo) contra el que el legado
PUBLICÓ al tomar el respaldo, fila por fila y por llave natural (uetr, concepto).

- **Orden por inversiones:** los pares con distinta fecha valor son contrato (`ORDER BY fecha_valor`) y deben dar 0;
  los empatados se juzgan contra el PISO de la misma corrida: el propio legado, re-corrido sobre el respaldo
  restaurado, contra lo que publicó. Si el legado no se repite a sí mismo (piso > 0), el orden de los empates no es
  contrato.
- **Arbitraje** de cada diferencia (renglón o celda) con `paridad/arbitraje.py`. El avance de producción se clasifica
  contra el corte MEDIDO y se audita en el legado VIVO: la misma partida existe allá con identidad mayor al corte.
- **Control negativo del comparador:** el piso calibra el ruido del legado, pero no demuestra que la comparación pueda
  fallar. `mutantes()` altera el reporte del TO-BE (un par de contrato invertido, un renglón quitado o duplicado, un
  centavo, una hora corrida con el desfase bien escrito, un avance que el legado vivo no tiene) y cada uno DEBE
  fallar.
- **Llaves secundarias candidatas:** si el legado NUNCA invierte los empates por alguna (en ninguna variante del
  plan), puede ser un orden de hecho: se publica como pregunta a negocio y el TO-BE no la puede invertir.
- **Punto ciego declarado:** en la hora que se repite, comparar la hora local por texto no distingue la primera vuelta
  de la segunda; se cuentan esas celdas.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from paridad import arbitraje, formato
from paridad.zonas import CDMX, NUEVA_YORK, es_ambigua
from radiografia import cuadre, orden

LLAVE = ('uetr', 'concepto')
ZONA_DE = {'fecha_envio': CDMX, 'fecha_partida': NUEVA_YORK}
L_VIVO_PARTIDA = ('SELECT s.id, s.monto FROM dbo.partida_solicitada s JOIN dbo.orden_pago p ON p.id = s.orden_id '
                  'WHERE p.uetr = %s AND s.concepto = %s')
L_VIVO_ORDEN = ("SELECT TOP 1 estatus FROM dbo.orden_pago WHERE uetr = %s AND estatus <> 'REEMPLAZADA' "
                'ORDER BY id DESC')


# Llaves secundarias candidatas (después de fecha_valor): ¿alguna ordena DE HECHO los empates del legado?
CANDIDATAS = ('moneda', 'bic_corresponsal', 'concepto', 'folio', 'uetr', 'estatus', 'fecha_envio', 'fecha_partida',
              'monto_partida')


def _indices(columnas: list[str], nombres) -> list[int]:
    return [columnas.index(n) for n in nombres]


# El piso es el CONTROL NEGATIVO: el legado contra sí mismo. Una sola re-corrida puede salir en 0 % aunque el orden de
# los empates no sea contrato (pasó en un clon limpio: 0 % aquí y 13.78 % en la radiografía del mismo ciclo). Se
# mide con el plan variado como en legado/VOLUMEN.md, sobre el contenedor LIMPIO (desechable): tal cual, con
# estadísticas nuevas y la caché de planes vacía, y con MAXDOP 4. El piso es el mayor; se publican los tres.
VARIANTES = (
    ('tal cual', ()),
    ('estadísticas nuevas y caché de planes vacía', (
        'UPDATE STATISTICS dbo.orden_pago WITH FULLSCAN', 'UPDATE STATISTICS dbo.partida_solicitada WITH FULLSCAN',
        'DBCC FREEPROCCACHE')),
    ('MAXDOP 4 (los núcleos del runner de GitHub)', (
        "EXEC sp_configure 'show advanced options', 1", 'RECONFIGURE',
        "EXEC sp_configure 'max degree of parallelism', 4", 'RECONFIGURE', 'DBCC FREEPROCCACHE')),
)


def piso(cursor, publicada: dict, carpeta: Path) -> dict:
    """El legado re-corrido sobre el respaldo restaurado contra lo que publicó, EN ESTA corrida, con el plan variado.
    En cada variante mide también las llaves secundarias candidatas."""
    columnas, capturada = formato.leer(carpeta / publicada['archivo'])
    natural = _indices(columnas, LLAVE)
    i_fecha = columnas.index('fecha_valor')
    muestras, candidatas = [], {c: [] for c in CANDIDATAS if c in columnas}
    for nombre, preparacion in VARIANTES:
        for sentencia in preparacion:
            cursor.execute(sentencia)
            while cursor.nextset():
                pass
        columnas_re, recorrida = cuadre.recorrer(cursor, publicada['procedimiento'], publicada['parametros'],
                                                 publicada['conjunto'])
        if columnas_re != columnas:
            raise SystemExit('el reporte re-corrido no tiene las columnas del publicado')
        a, b = [tuple(f) for f in capturada], [tuple(f) for f in recorrida]
        medida = orden.comparar(a, b, natural, _indices(columnas, publicada['llave_orden']))
        muestras.append({'variante': nombre, **medida})
        for c in candidatas:
            m = orden.comparar(a, b, natural, [i_fecha, columnas.index(c)])
            candidatas[c].append(m['inversiones_contrato'])
    mayor = max(muestras, key=lambda m: m['pct_empatados_invertidos'])
    return {**mayor, 'inversiones_contrato': max(m['inversiones_contrato'] for m in muestras),
            'mismo_contenido': all(m['mismo_contenido'] for m in muestras),
            'muestras': [{k: m[k] for k in ('variante', 'inversiones_contrato', 'inversiones_empatados',
                                            'pct_empatados_invertidos', 'mismo_contenido')} for m in muestras],
            'candidatas': {c: {'inversiones_por_variante': v, 'orden_de_hecho_posible': max(v) == 0}
                           for c, v in candidatas.items()}}


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


def _celdas_en_hora_repetida(columnas: list[str], filas: list[list]) -> int:
    """Celdas cuya hora local se repite en su zona: ahí el texto local no distingue la primera vuelta de la segunda."""
    n = 0
    for col, zona in ZONA_DE.items():
        i = columnas.index(col)
        for f in filas:
            if f[i] and es_ambigua(datetime.fromisoformat(f[i]).replace(tzinfo=None), zona):
                n += 1
    return n


def comparar(publicada: dict, carpeta: Path, ruta_tobe: Path, piso_medido: dict, corte: dict, vivo,
             eventos: dict) -> dict:
    columnas, legado = formato.leer(carpeta / publicada['archivo'])
    columnas_t, tobe = formato.leer(ruta_tobe)
    if columnas_t != columnas:
        raise SystemExit(f'el reporte del TO-BE no tiene las columnas del publicado: {columnas_t}')
    i_llave = _indices(columnas, LLAVE)
    leg = {tuple(f[i] for i in i_llave): f for f in legado}
    tob = {tuple(f[i] for i in i_llave): f for f in tobe}

    diferencias: list[arbitraje.Diferencia] = []
    # una llave natural repetida no se arbitra: es defecto (el reporte ya no se puede cruzar renglón a renglón)
    for lado, filas in (('TO-BE', tobe), ('legado', legado)):
        vistas = set()
        for f in filas:
            llave = tuple(f[i] for i in i_llave)
            if llave in vistas:
                diferencias.append(arbitraje.Diferencia('llave repetida', '/'.join(llave), lado, lado, {}))
            vistas.add(llave)
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
    i_fecha = columnas.index('fecha_valor')

    def proyeccion(filas, otras, extra: str | None = None):
        vistas, resultado = set(), []
        for f in filas:
            k = tuple(f[i] for i in i_llave)
            if k in otras and k not in vistas:
                vistas.add(k)
                resultado.append((k[0], k[1], f[i_fecha]) + ((f[columnas.index(extra)],) if extra else ()))
        return resultado

    medida = orden.comparar(proyeccion(legado, tob), proyeccion(tobe, leg), [0, 1], [2])
    contrato_ok = medida['inversiones_contrato'] == 0
    empates_libres = piso_medido['pct_empatados_invertidos'] > 0
    ordenes_de_hecho = {}
    for c, info in piso_medido.get('candidatas', {}).items():
        if info['orden_de_hecho_posible']:
            m = orden.comparar(proyeccion(legado, tob, c), proyeccion(tobe, leg, c), [0, 1], [2, 3])
            ordenes_de_hecho[c] = {'inversiones_del_tobe': m['inversiones_contrato'],
                                   'pregunta': f'¿El reporte debe ordenar por fecha valor y luego por {c}? El legado '
                                               'nunca invirtió ese orden en ninguna variante del plan.'}
    respeta_hecho = all(x['inversiones_del_tobe'] == 0 for x in ordenes_de_hecho.values())
    arbitrado = arbitraje.arbitrar(diferencias, arbitros(corte, vivo, eventos))
    por_tipo = {'renglones_solo_tobe': len(tob) - len(comunes), 'renglones_solo_legado': len(leg) - len(comunes),
                'renglones_comunes': len(comunes), 'renglones_comunes_con_celdas_distintas': len(renglones_distintos),
                'llaves_repetidas': sum(1 for d in diferencias if d.regla == 'llave repetida')}
    if contrato_ok and empates_libres:
        veredicto = ('contrato en 0; los empates no son contrato: el propio legado invierte hasta '
                     f"{piso_medido['pct_empatados_invertidos']} % de sus pares empatados en esta corrida (con el "
                     f"plan variado) y el TO-BE {medida['pct_empatados_invertidos']} %")
    else:
        veredicto = 'REVISAR: contrato roto o empates que el legado sí repite'
    return {
        'publicado': {'archivo': publicada['archivo'], 'sha256': publicada['sha256'], 'renglones': len(legado)},
        'tobe': {'renglones': len(tobe)}, **por_tipo,
        'orden': {'tobe_contra_publicado': medida, 'piso_misma_corrida': piso_medido,
                  'contrato_en_cero': contrato_ok, 'empates_libres': empates_libres,
                  'ordenes_de_hecho': ordenes_de_hecho, 'veredicto': veredicto},
        'punto_ciego': {'celdas_en_hora_repetida': _celdas_en_hora_repetida(columnas, legado),
                        'lectura': 'en la hora que se repite, la hora local por texto no distingue la primera vuelta '
                                   'de la segunda; esas celdas no quedan verificadas por este nivel'},
        'arbitraje': arbitrado,
        'cumple': contrato_ok and empates_libres and respeta_hecho
        and arbitrado['por_categoria'][arbitraje.DEFECTO] == 0,
    }


def _hora(valor: str, zona, horas: int) -> str:
    """Corre una hora el instante y la vuelve a escribir con el desfase CORRECTO de su zona."""
    instante = datetime.fromisoformat(valor) + timedelta(hours=horas)
    return instante.astimezone(zona).isoformat(timespec='seconds')


def mutantes(publicada: dict, carpeta: Path, ruta_tobe: Path, piso_medido: dict, corte: dict, vivo, eventos: dict,
             trabajo: Path) -> list[dict]:
    """Copias alteradas del reporte del TO-BE que la comparación DEBE rechazar (control negativo del comparador)."""
    columnas, tobe = formato.leer(ruta_tobe)
    _, legado = formato.leer(carpeta / publicada['archivo'])
    i = {c: k for k, c in enumerate(columnas)}
    llaves_legado = {(f[i['uetr']], f[i['concepto']]) for f in legado}
    comunes = [k for k, f in enumerate(tobe) if (f[i['uetr']], f[i['concepto']]) in llaves_legado]
    corte_utc = datetime.fromisoformat(corte['instante_utc'])
    k = comunes[len(comunes) // 2]
    en_comun = set(comunes)
    salto = next(j for j in comunes if j + 1 in en_comun
                 and tobe[j][i['fecha_valor']] != tobe[j + 1][i['fecha_valor']])

    def copia():
        return [list(f) for f in tobe]

    invertido = copia()
    invertido[salto], invertido[salto + 1] = invertido[salto + 1], invertido[salto]
    sin_renglon = copia()
    del sin_renglon[k]
    duplicado = copia()
    duplicado.insert(k, list(tobe[k]))
    centavo = copia()
    centavo[k][i['monto_partida']] = str(Decimal(tobe[k][i['monto_partida']]) + Decimal('0.01'))
    hora = copia()
    hora[k][i['fecha_partida']] = _hora(tobe[k][i['fecha_partida']], NUEVA_YORK, 1)
    falso = '00000000-0000-4000-8000-00000000dead'
    avance = copia()
    nuevo = list(tobe[k])
    nuevo[i['uetr']] = falso
    avance.append(nuevo)
    eventos_falsos = {**eventos, falso: corte_utc + timedelta(hours=2)}

    def defectos(r):
        return r['arbitraje']['por_categoria'][arbitraje.DEFECTO]

    casos = (
        ('un par de contrato invertido', invertido, eventos,
         'inversiones de contrato = 1', lambda r: r['orden']['tobe_contra_publicado']['inversiones_contrato'] == 1),
        ('un renglón quitado', sin_renglon, eventos, '«sólo en el legado» = 1 y defecto nuestro = 1',
         lambda r: r['renglones_solo_legado'] == 1 and defectos(r) == 1),
        ('un renglón duplicado', duplicado, eventos, 'llave repetida = 1 y defecto nuestro = 1',
         lambda r: r['llaves_repetidas'] == 1 and defectos(r) == 1),
        ('un centavo distinto', centavo, eventos, 'defecto nuestro = 1', lambda r: defectos(r) == 1),
        ('una hora corrida 1 h con el desfase bien escrito', hora, eventos,
         'defecto nuestro = 1 (la regla «hora local sin zona» la rechaza)', lambda r: defectos(r) == 1),
        ('un avance que el legado vivo no tiene', avance, eventos_falsos,
         'defecto nuestro = 1 (la auditoría del avance lo rechaza)', lambda r: defectos(r) == 1),
    )
    resultados = []
    trabajo.mkdir(parents=True, exist_ok=True)
    for n, (nombre, filas, evs, debe, verifica) in enumerate(casos):
        ruta = trabajo / f'mutante_{n}.jsonl'
        formato.escribir(ruta, columnas, filas)
        r = comparar(publicada, carpeta, ruta, piso_medido, corte, vivo, evs)
        resultados.append({'mutante': nombre, 'debe': debe, 'cumple_la_paridad': r['cumple'],
                           'defectos': defectos(r),
                           'inversiones_contrato': r['orden']['tobe_contra_publicado']['inversiones_contrato'],
                           'falla_como_debe': (not r['cumple']) and verifica(r)})
    return resultados


def eventos_posteriores(universo: Path, corte_utc: datetime) -> dict[str, datetime]:
    """UETR → instante de su confirmación en el buzón, si es POSTERIOR al corte (lo único que puede ser avance)."""
    from universo.interfaces import leer_buzon
    resultado = {}
    for archivo in sorted((universo / 'interfaces' / 'corresponsal').glob('*.fin')):
        for c in leer_buzon(archivo.read_text(encoding='utf-8')):
            if c.instante_utc > corte_utc:
                resultado[c.uetr] = c.instante_utc.astimezone(timezone.utc)
    return resultado

