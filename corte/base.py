"""La base cerrada del corte como foto restaurable (S3 paso 4; ADR 0013, segunda línea de defensa: «restaurar desde la
corrida anterior»).

- **Volcar:** la nocturna, después del cierre, vuelca la base (`pg_dump` en formato propio, corrido DENTRO del
  contenedor: la misma versión que el servidor) y deja junto al volcado `destino.json`, con su sha256, la huella del
  destino al cerrar (las 7 tablas, las secuencias y los folios), el plan y el cierre.
- **Restaurar:** en una base limpia, con los roles del servidor creados antes (el volcado no los lleva y sus GRANT
  los nombran). Primero el sha256 del volcado.
- **Verificar:** no se le cree a la foto. Después de restaurar: la huella es la que dejó el cierre; el plan de ESTA
  corrida (mismos rangos, filas y montos por mes, medidos sobre el respaldo de esta corrida) es el de la foto; los 36
  meses están aplicados con ese plan; el corte del destino coincide por sus dos caminos y es el del respaldo; las
  llaves foráneas del cierre están; los totales (filas, MAX(id) y montos) son los del origen hasta el corte; no hay
  punto de no retorno ni automatismos encendidos.
- **Construir:** si no hay volcado (la primera corrida, o el artefacto se venció), los 36 meses con el mismo runbook
  (ensayo → aplicar) y el cierre.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import time
from pathlib import Path

from corte import carga, delta, runbook
from corte.carga import CON_IDENTIDAD
from corte.runbook import Negado

DUMP, META = 'destino.dump', 'destino.json'
EN_CONTENEDOR = '/tmp/decant-destino.dump'
# Los roles del servidor que nombran los GRANT del volcado (los de la carga por mes y, si alguna vez se volcara con el
# delta preparado, los del delta).
ROLES = ('decant_corte_aplica', 'decant_corte_revierte', 'decant_corte_delta_aplica', 'decant_corte_delta_revierte')


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as archivo:
        for bloque in iter(lambda: archivo.read(1 << 20), b''):
            h.update(bloque)
    return h.hexdigest()


def _nombre(base: str) -> str:
    if not base.replace('_', '').isalnum() or not base.isascii():
        raise Negado(f'nombre de base no válido: {base!r}')
    return base


def _q_borrar_base(base: str):
    from psycopg import sql
    return sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(_nombre(base)))


def _q_crear_rol(rol: str):
    from psycopg import sql
    if rol not in ROLES:
        raise Negado(f'rol no previsto: {rol!r}')
    return sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(rol))


def _usuario() -> str:
    from paridad.tobe import parametros
    return parametros()['user']


def _docker(*argumentos: str) -> None:
    """La CLI de Docker; si falla, el error lleva lo que dijo (pg_dump y pg_restore explican ahí por qué)."""
    import subprocess

    from legado.conexion import docker
    try:
        docker(*argumentos)
    except subprocess.CalledProcessError as error:
        raise Negado(f"docker {' '.join(argumentos[:3])}: salió con {error.returncode}: "
                     f"{(error.stderr or '').strip()[-1500:]}") from error


def _ci() -> dict:
    from corte import medir
    return medir._ci()


def volcar(pg, contenedor: str, base: str, salida: Path, informe: dict) -> dict:
    """`pg_dump -Fc` de la base cerrada, desde el contenedor, y su `destino.json`."""
    t0 = time.monotonic()
    huella = runbook.huella_destino(pg)
    salida.mkdir(parents=True, exist_ok=True)
    _docker('exec', contenedor, 'pg_dump', '-U', _usuario(), '-d', _nombre(base), '-Fc', '-Z', '6', '-f', EN_CONTENEDOR)
    _docker('cp', f'{contenedor}:{EN_CONTENEDOR}', str(salida / DUMP))
    _docker('exec', contenedor, 'rm', '-f', EN_CONTENEDOR)
    meta = {
        'version': 1,
        'que_es': 'la base cerrada del corte (36 meses, setval, folios con margen y llaves foráneas), volcada por la '
                  'nocturna para que el delta la restaure (corte/base.py)',
        'corrida': _ci(), 'base': base,
        'dump': {'archivo': DUMP, 'sha256': sha256(salida / DUMP), 'bytes': (salida / DUMP).stat().st_size},
        'origen': informe.get('origen'), 'corte': informe.get('corte'), 'plan_sha': informe['plan']['sha'],
        'cierre': informe.get('cierre'), 'huella': huella, 'segundos': round(time.monotonic() - t0, 1),
    }
    (salida / META).write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str) + '\n', encoding='utf-8')
    return meta


def restaurar(contenedor: str, carpeta: Path, base: str) -> dict:
    """La foto en una base LIMPIA: sha256 del volcado contra `destino.json`, roles del servidor y `pg_restore`."""
    import psycopg

    from paridad.tobe import parametros
    t0 = time.monotonic()
    meta = json.loads((carpeta / META).read_text(encoding='utf-8'))
    volcado = carpeta / DUMP
    sha = sha256(volcado)
    if sha != meta['dump']['sha256']:
        raise Negado(f"{DUMP}: el sha256 {sha[:16]}… no es el de {META} ({meta['dump']['sha256'][:16]}…); no se "
                     'restaura')
    with psycopg.connect(dbname='postgres', autocommit=True, **parametros()) as admin:
        admin.execute(_q_borrar_base(base))
        admin.execute(runbook._q_crear_base(_nombre(base)))
        for rol in ROLES:
            with contextlib.suppress(psycopg.errors.DuplicateObject):      # el rol es del servidor: ya existía
                admin.execute(_q_crear_rol(rol))
    _docker('cp', str(volcado), f'{contenedor}:{EN_CONTENEDOR}')
    try:
        _docker('exec', contenedor, 'pg_restore', '-U', _usuario(), '-d', _nombre(base), '--no-owner',
                '--exit-on-error', '-j', '2', EN_CONTENEDOR)
    finally:
        _docker('exec', contenedor, 'rm', '-f', EN_CONTENEDOR)
    return {'sha256': sha, 'bytes': volcado.stat().st_size, 'corrida': meta.get('corrida'),
            'segundos': round(time.monotonic() - t0, 1)}


def verificar(pg, ms, meta: dict | None, p: dict, corte: dict[str, int]) -> dict:
    """La base cerrada, sin creerle: ver el docstring del módulo. `meta` = `destino.json` (None si se construyó aquí:
    entonces no hay huella de una foto que comparar). `ms` = el respaldo de ESTA corrida (`BFN_DIVISAS_CORTE`)."""
    t0 = time.monotonic()
    faltas: list[str] = []
    huella = runbook.huella_destino(pg)
    if meta is not None:
        faltas += [f'huella al restaurar: {x}' for x in delta.diferencias(meta['huella'], huella)]
        if meta['plan_sha'] != p['sha']:
            faltas.append(f"el plan de la foto ({meta['plan_sha'][:12]}) no es el de esta corrida ({p['sha'][:12]}): "
                          'otro respaldo u otro generador')
    aplicados = {m: s.strip() for m, s in pg.execute(
        "SELECT mes, plan_sha FROM corte.carga_mes WHERE estado = 'aplicado'").fetchall()}
    faltan = [m for m in p['meses'] if m not in aplicados]
    con_otro_plan = sorted(m for m, s in aplicados.items() if s != p['sha'])
    if faltan or con_otro_plan:
        faltas.append(f'meses: faltan {faltan[:6]} y con otro plan {con_otro_plan[:6]}')
    a_medias = pg.execute("SELECT count(*) FROM corte.carga_mes WHERE estado = 'reversa_generada'").fetchone()[0]
    if a_medias:
        faltas.append(f'{a_medias} meses quedaron a medias (reversa generada y sin aplicar)')
    actual, f = carga.corte_del_destino(runbook.maximos(pg), runbook.registro(pg))
    faltas += f
    if actual != corte:
        faltas.append(f'el destino llega a {actual} y el corte es {corte}')
    nombres = [n for n, *_ in runbook.LLAVES_FORANEAS]
    llaves = sorted(n for (n,) in pg.execute('SELECT conname FROM pg_constraint WHERE conname = ANY(%s::text[])',
                                             (nombres,)).fetchall())
    if llaves != sorted(nombres):
        faltas.append(f'faltan llaves foráneas del cierre: {sorted(set(nombres) - set(llaves))}')
    cursor = ms.cursor()
    totales = {}
    for t in CON_IDENTIDAD:
        cursor.execute(carga.TOTALES[t.nombre], {'corte': corte[t.nombre]})
        filas, maximo, monto = cursor.fetchone()
        d_filas, d_max, d_monto = pg.execute(runbook._q('totales', t.nombre)).fetchone()
        o = (int(filas), int(maximo), None if monto is None else format(monto, 'f'))
        d = (d_filas, d_max, None if d_monto is None else format(d_monto, 'f'))
        totales[t.nombre] = {'origen': o, 'destino': d}
        if o != d:
            faltas.append(f'{t.nombre}: origen (filas, MAX, monto) {o} ≠ destino {d}')
    punto = runbook.no_retorno(pg)
    if punto is not None:
        faltas.append(f'la base ya cruzó el punto de no retorno: {punto}')
    prendidos = runbook.encendidos(pg)
    if prendidos:
        faltas.append(f'la base trae automatismos encendidos: {prendidos}')
    return {'huella_igual_a_la_foto': None if meta is None else meta['huella'] == huella, 'plan_sha': p['sha'],
            'meses_aplicados': len(aplicados), 'llaves_foraneas': llaves, 'totales': totales,
            'secuencias': {t: s['last_value'] for t, s in huella['secuencias'].items()},
            'folios': {s: v['siguiente'] for s, v in huella['folios'].items()},
            'faltas': faltas, 'verde': not faltas, 'segundos': round(time.monotonic() - t0, 1)}


def construir(pg, ms, p: dict, corte: dict[str, int], margen: int) -> dict:
    """Sin volcado: los 36 meses con el runbook de la carga (ensayo → aplicar, cada uno con su huella del mes) y el
    cierre. Es el camino lento (≈ 7 min en el CI): el volcado de la nocturna lo evita."""
    t0 = time.monotonic()
    runbook.preparar(pg, ms, recrear=True)
    no_cuadran = []
    for mes in p['meses']:
        runbook.cargar_mes(pg, ms, p, mes, corte, confirmar=False)
        r = runbook.cargar_mes(pg, ms, p, mes, corte, confirmar=True)
        if any(r['huella_origen'][t] != r['huella_destino'][t] for t in r['huella_origen']):
            no_cuadran.append(mes)
    cierre = runbook.cerrar(pg, ms, p, corte, margen)
    return {'meses': len(p['meses']), 'no_cuadran': no_cuadran,
            'consumibles': cierre['consumibles'], 'segundos': round(time.monotonic() - t0, 1)}
