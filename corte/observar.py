"""Observación del ciclo en el CI (segunda fuente del ADR 0014): qué ejecutó el servidor de verdad y qué logins y
aplicaciones se conectaron, muestreado MIENTRAS corre `./ciclo.sh`. Clasifica; no recorta: lo que no aparece aquí queda
«sin ejecución observada» en el cruce, con su renglón igual.

    python -m corte.observar --salida corte/observado-ci/observado.json &     # antes del ciclo
    ./ciclo.sh
    python -m corte.observar --detener corte/observado-ci/observado.json      # al terminar el ciclo

Fuentes, todas de sólo lectura (el observador no cambia opciones del servidor ni de la base):
- sesiones de usuario (`sys.dm_exec_sessions`, cada 0.25 s): login, aplicación, interfaz del cliente y base. Es una
  MUESTRA: una conexión que dura menos que el intervalo puede no verse (la bitácora cubre a los que escriben);
- peticiones en curso (`sys.dm_exec_requests` + `dm_exec_sql_text`): qué módulo corre y con qué login;
- estadísticas acumuladas, cada 5 s porque el caché de planes las puede expulsar: `dm_exec_procedure_stats`,
  `dm_exec_trigger_stats`, `dm_exec_function_stats` y los lotes ad hoc de `dm_exec_query_stats`. Del texto ad hoc
  sólo se guarda qué objetos toca (con el mismo parser del inventario), no el texto;
- al cerrar: Query Store de la base (estado y ejecuciones por objeto), el historial de los jobs en msdb, el catálogo de
  módulos del servidor y los usuarios que dejó la bitácora (el `SUSER_SNAME()` que guarda el trigger).

Se conecta a `master` (nunca a la base del legado: `esquema --recrear` la pone en SINGLE_USER) con la aplicación
`decant-observador`, y se excluye a sí mismo por `@@SPID`.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from corte.codigo import PRINCIPAL
from corte.sql import analizar
from radiografia.tsql import fichas

APLICACION = 'decant-observador'
MARCA = '/* decant-observador */'
MAXIMO_TEXTO = 200_000          # del texto ad hoc sólo se analiza el principio: lo que sigue suele ser un literal
POR_MODULO = ('dm_exec_procedure_stats', 'dm_exec_trigger_stats', 'dm_exec_function_stats', 'msdb.dbo.sysjobhistory')
TIPOS = {'P': 'procedimiento', 'TR': 'trigger', 'FN': 'funcion', 'IF': 'funcion', 'TF': 'funcion', 'V': 'vista',
         'PC': 'procedimiento', 'X': 'procedimiento'}

# Cada consulta es UN literal (sin armar texto: Semgrep y CodeQL lo exigen) y lleva la marca del observador, que
# la excluye de lo ad hoc. La base del legado va escrita donde no puede ser parámetro (nombres de tres partes); una
# prueba exige que sea PRINCIPAL.
Q_SESIONES = """/* decant-observador */
SELECT s.session_id, CONVERT(varchar(30), s.login_time, 126), s.login_name, s.program_name, s.client_interface_name,
       DB_NAME(s.database_id)
FROM sys.dm_exec_sessions s
WHERE s.is_user_process = 1 AND s.session_id <> @@SPID"""
Q_EN_CURSO = """/* decant-observador */
SELECT s.login_name, s.program_name, OBJECT_SCHEMA_NAME(t.objectid, t.dbid), OBJECT_NAME(t.objectid, t.dbid)
FROM sys.dm_exec_requests r
JOIN sys.dm_exec_sessions s ON s.session_id = r.session_id
CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t
WHERE s.is_user_process = 1 AND r.session_id <> @@SPID AND t.objectid IS NOT NULL AND t.dbid = DB_ID(%s)"""
Q_ESTADISTICAS = """/* decant-observador */
SELECT 'dm_exec_procedure_stats', OBJECT_SCHEMA_NAME(object_id, database_id), OBJECT_NAME(object_id, database_id),
       type, execution_count, CONVERT(varchar(30), cached_time, 126)
FROM sys.dm_exec_procedure_stats WHERE database_id = DB_ID(%s)
UNION ALL
SELECT 'dm_exec_trigger_stats', OBJECT_SCHEMA_NAME(object_id, database_id), OBJECT_NAME(object_id, database_id),
       type, execution_count, CONVERT(varchar(30), cached_time, 126)
FROM sys.dm_exec_trigger_stats WHERE database_id = DB_ID(%s)
UNION ALL
SELECT 'dm_exec_function_stats', OBJECT_SCHEMA_NAME(object_id, database_id), OBJECT_NAME(object_id, database_id),
       type, execution_count, CONVERT(varchar(30), cached_time, 126)
FROM sys.dm_exec_function_stats WHERE database_id = DB_ID(%s)"""
# El texto ad hoc no trae su base en dm_exec_sql_text (dbid nulo): sale de los atributos del plan.
Q_AD_HOC = """/* decant-observador */
WITH q AS (
    SELECT sql_handle, MAX(plan_handle) AS plan_handle, MAX(execution_count) AS n FROM sys.dm_exec_query_stats
    WHERE last_execution_time >= %s GROUP BY sql_handle)
SELECT CONVERT(varchar(130), q.sql_handle, 1), q.n, pa.dbid, LEFT(t.text, %s), LEN(t.text)
FROM q CROSS APPLY sys.dm_exec_sql_text(q.sql_handle) t
OUTER APPLY (SELECT CONVERT(int, a.value) AS dbid FROM sys.dm_exec_plan_attributes(q.plan_handle) a
             WHERE a.attribute = N'dbid') pa
WHERE t.objectid IS NULL AND (pa.dbid = DB_ID(%s) OR t.text LIKE %s) AND t.text NOT LIKE %s"""
Q_AHORA = '/* decant-observador */ SELECT GETDATE(), DB_ID(%s), @@VERSION'
Q_QUERY_STORE_ESTADO = """/* decant-observador */
SELECT actual_state_desc, query_capture_mode_desc FROM BFN_DIVISAS.sys.database_query_store_options"""
Q_QUERY_STORE = """/* decant-observador */
SELECT OBJECT_SCHEMA_NAME(q.object_id, DB_ID(N'BFN_DIVISAS')), OBJECT_NAME(q.object_id, DB_ID(N'BFN_DIVISAS')),
       SUM(rs.count_executions)
FROM BFN_DIVISAS.sys.query_store_query q
JOIN BFN_DIVISAS.sys.query_store_plan p ON p.query_id = q.query_id
JOIN BFN_DIVISAS.sys.query_store_runtime_stats rs ON rs.plan_id = p.plan_id
WHERE q.object_id <> 0
GROUP BY q.object_id"""
# Jobs del legado: los que tienen un paso en su base o que la nombran (los del sistema, como el de políticas, no).
Q_JOBS = """/* decant-observador */
SELECT j.name, j.enabled,
       (SELECT COUNT(*) FROM msdb.dbo.sysjobhistory h WHERE h.job_id = j.job_id AND h.step_id = 0),
       (SELECT COUNT(*) FROM msdb.dbo.sysjobactivity a WHERE a.job_id = j.job_id AND a.start_execution_date IS NOT NULL)
FROM msdb.dbo.sysjobs j
WHERE EXISTS (SELECT 1 FROM msdb.dbo.sysjobsteps s WHERE s.job_id = j.job_id
              AND (s.database_name = N'BFN_DIVISAS' OR s.command LIKE N'%BFN_DIVISAS%'))
ORDER BY j.name"""
Q_CATALOGO_JOBS = """/* decant-observador */
SELECT j.name
FROM msdb.dbo.sysjobs j
WHERE EXISTS (SELECT 1 FROM msdb.dbo.sysjobsteps s WHERE s.job_id = j.job_id
              AND (s.database_name = N'BFN_DIVISAS' OR s.command LIKE N'%BFN_DIVISAS%'))
ORDER BY j.name"""
Q_CATALOGO = """/* decant-observador */
SELECT s.name, o.name, RTRIM(o.type)
FROM BFN_DIVISAS.sys.objects o JOIN BFN_DIVISAS.sys.schemas s ON s.schema_id = o.schema_id
WHERE o.is_ms_shipped = 0 AND o.type IN ('P', 'V', 'TR', 'FN', 'IF', 'TF', 'PC', 'X')
ORDER BY s.name, o.name"""
Q_BITACORA = """/* decant-observador */
SELECT usuario, COUNT_BIG(*), CONVERT(varchar(30), MIN(fecha), 126), CONVERT(varchar(30), MAX(fecha), 126)
FROM BFN_DIVISAS.dbo.bitacora GROUP BY usuario ORDER BY usuario"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@dataclass
class Registro:
    """Lo observado, acumulado entre muestras. Sin base: se prueba con filas sintéticas."""
    conocidos: dict[str, str]
    consumidores: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    sesiones: set[tuple[int, str]] = field(default_factory=set)
    ejecuciones: dict[str, dict] = field(default_factory=dict)          # id → {tipo, fuentes, por_cache}
    quien: dict[str, set[tuple[str, str]]] = field(default_factory=dict)
    ad_hoc: dict[str, dict] = field(default_factory=dict)               # sql_handle → {n, firma}
    firmas: dict[str, dict] = field(default_factory=dict)               # firma → analisis
    muestras: dict[str, int] = field(default_factory=lambda: {'sesiones': 0, 'estadisticas': 0})

    def sesion(self, session_id: int, login_time: str, login: str, aplicacion: str | None, interfaz: str | None,
               base: str | None, instante: str) -> None:
        llave = (login or '', aplicacion or '', interfaz or '')
        c = self.consumidores.setdefault(llave, {'bases': set(), 'sesiones': set(), 'muestras': 0,
                                                 'primera_utc': instante, 'ultima_utc': instante})
        c['muestras'] += 1
        c['ultima_utc'] = instante
        c['sesiones'].add((session_id, login_time))
        if base:
            c['bases'].add(base)
        self.sesiones.add((session_id, login_time))

    def ejecutado(self, esquema: str | None, nombre: str | None, tipo: str, fuente: str, n: int = 0,
                  generacion: str = '') -> None:
        if nombre:
            self.ejecutado_id(f'{esquema or "dbo"}.{nombre}'.lower(), tipo, fuente, n, generacion)

    def ejecutado_id(self, id_: str, tipo: str, fuente: str, n: int = 0, generacion: str = '') -> None:
        e = self.ejecuciones.setdefault(id_, {'tipo': TIPOS.get(tipo.strip(), tipo.strip()), 'fuentes': set(),
                                              'por_cache': {}})
        e['fuentes'].add(fuente)
        clave = f'{fuente}|{generacion}'
        e['por_cache'][clave] = max(e['por_cache'].get(clave, 0), int(n or 0))

    def en_curso(self, login: str, aplicacion: str | None, esquema: str | None, nombre: str | None) -> None:
        if nombre:
            self.ejecutado(esquema, nombre, 'P', 'dm_exec_requests')
            self.quien.setdefault(f'{esquema or "dbo"}.{nombre}'.lower(), set()).add((login, aplicacion or ''))

    def lote_ad_hoc(self, handle: str, n: int, dbid_principal: bool, texto: str, largo: int) -> None:
        if handle in self.ad_hoc:
            self.ad_hoc[handle]['n'] = max(self.ad_hoc[handle]['n'], int(n))
            return
        base = PRINCIPAL if dbid_principal else 'master'
        a = analizar(fichas(texto), self.conocidos, base, PRINCIPAL)
        analisis = {'lee': sorted(a.lee), 'escribe': {t: sorted(e) for t, e in sorted(a.escribe.items())},
                    'llama': sorted(a.llama), 'efectos': sorted(a.efectos), 'sql_dinamico': sorted(a.sql_dinamico),
                    'reloj': sorted(a.reloj)}
        # Sin objetos del legado (lotes internos del servidor, p. ej. los de Query Store): se cuentan, no se listan.
        firma = json.dumps(analisis, sort_keys=True) if any(analisis[k] for k in (
            'lee', 'escribe', 'llama', 'efectos', 'sql_dinamico')) else None
        if firma:
            self.firmas[firma] = analisis
        self.ad_hoc[handle] = {'n': int(n), 'firma': firma, 'truncado': largo > len(texto)}
        for id_ in sorted(set(a.lee) | set(a.escribe) | set(a.llama)):
            if self.conocidos.get(id_, 'tabla') != 'tabla':       # las tablas quedan en el grupo ad hoc
                self.ejecutado_id(id_, self.conocidos[id_], 'dm_exec_query_stats (ad hoc)', n, handle)

    def resumen(self) -> dict:
        consumidores = []
        for (login, aplicacion, interfaz), c in sorted(self.consumidores.items()):
            consumidores.append({'login': login, 'aplicacion': aplicacion, 'interfaz_cliente': interfaz,
                                 'bases': sorted(c['bases']), 'sesiones': len(c['sesiones']), 'muestras': c['muestras'],
                                 'primera_utc': c['primera_utc'], 'ultima_utc': c['ultima_utc'],
                                 'origen': 'dm_exec_sessions'})
        ejecutados = {}
        for id_, e in sorted(self.ejecuciones.items()):
            por_fuente = {f: sum(n for k, n in e['por_cache'].items() if k.startswith(f + '|'))
                          for f in sorted(e['fuentes'])}
            # Ejecuciones del MÓDULO: las de sus estadísticas (o del historial del job). Query Store cuenta por
            # sentencia y lo ad hoc por lote: sólo si no hay otra cosa.
            modulo = [n for f, n in por_fuente.items() if f in POR_MODULO]
            ejecutados[id_] = {'tipo': e['tipo'], 'fuentes': sorted(e['fuentes']),
                               'ejecuciones': max(modulo) if modulo else max(por_fuente.values(), default=0),
                               'por_fuente': por_fuente}
        grupos: dict[str, dict] = {}
        for lote in self.ad_hoc.values():
            if lote['firma'] is None:
                continue
            g = grupos.setdefault(lote['firma'], {**self.firmas[lote['firma']], 'lotes': 0, 'ejecuciones': 0,
                                                 'truncados': 0})
            g['lotes'] += 1
            g['ejecuciones'] += lote['n']
            g['truncados'] += int(lote['truncado'])
        return {'consumidores': consumidores, 'objetos_ejecutados': ejecutados,
                'quien_ejecuta': {k: sorted([list(x) for x in v]) for k, v in sorted(self.quien.items())},
                'ad_hoc': sorted(grupos.values(), key=lambda g: (-g['ejecuciones'], json.dumps(g, sort_keys=True))),
                'ad_hoc_sin_objetos': sum(1 for x in self.ad_hoc.values() if x['firma'] is None),
                'muestras': dict(self.muestras)}


class Observador:
    def __init__(self, salida: Path, intervalo: float = 0.25, cada_estadisticas: float = 5.0,
                 maximo_minutos: float = 90.0):
        from corte.codigo import inventario
        inv = inventario()
        conocidos = {o['id']: o['tipo'] for o in inv['objetos']}
        conocidos.update({t: 'tabla' for t in inv['tablas']})
        self.registro = Registro(conocidos)
        self.salida = salida
        self.detener_en = salida.with_name(salida.name + '.detener')
        self.intervalo, self.cada_estadisticas = intervalo, cada_estadisticas
        self.limite = time.monotonic() + maximo_minutos * 60
        self.conexion = None
        self.parar = False
        self.errores: list[str] = []
        self.errores_antes_de_conectar = 0
        self.conecto = False
        self.umbral_ad_hoc: datetime | None = None
        self.servidor: dict = {}

    def _conectar(self):
        import pymssql

        from legado.conexion import contrasena
        return pymssql.connect(
            server=os.environ.get('DECANT_SQL_HOST', '127.0.0.1'), port=int(os.environ.get('DECANT_PUERTO', '14330')),
            user='sa', password=contrasena(), database='master', autocommit=True, appname=APLICACION,
            tds_version='7.4', charset='UTF-8', login_timeout=5, timeout=120)

    def _error(self, error: Exception) -> None:
        if not self.conecto:
            self.errores_antes_de_conectar += 1
            return
        self.errores.append(f'{_ahora()} {type(error).__name__}: {str(error)[:300]}')
        self.errores = self.errores[-20:]

    def _cerrar_conexion(self) -> None:
        if self.conexion is not None:
            with contextlib.suppress(Exception):     # ya está caída: sólo se suelta
                self.conexion.close()
        self.conexion = None

    def muestrear(self, estadisticas: bool) -> None:
        if self.conexion is None:
            self.conexion = self._conectar()
            self.conecto = True
        cursor = self.conexion.cursor()
        instante = _ahora()
        cursor.execute(Q_SESIONES)
        for fila in cursor.fetchall():
            self.registro.sesion(*fila, instante=instante)
        cursor.execute(Q_EN_CURSO, (PRINCIPAL,))
        for fila in cursor.fetchall():
            self.registro.en_curso(*fila)
        self.registro.muestras['sesiones'] += 1
        if estadisticas:
            self.estadisticas(cursor)

    def estadisticas(self, cursor) -> None:
        cursor.execute(Q_AHORA, (PRINCIPAL,))
        ahora, dbid, version = cursor.fetchone()
        self.servidor = {'version': (version or '').splitlines()[0].strip(), 'base_existe': dbid is not None}
        if dbid is None:
            return                      # la base aún no existe (o se está recreando)
        cursor.execute(Q_ESTADISTICAS, (PRINCIPAL,) * 3)
        for fuente, esquema, nombre, tipo, n, cache in cursor.fetchall():
            self.registro.ejecutado(esquema, nombre, tipo or '', fuente, n, cache or '')
        desde = (self.umbral_ad_hoc or datetime(2000, 1, 1)) - timedelta(seconds=10)
        cursor.execute(Q_AD_HOC, (desde, MAXIMO_TEXTO, PRINCIPAL, f'%{PRINCIPAL}%', f'%{APLICACION}%'))
        for handle, n, dbid_lote, texto, largo in cursor.fetchall():
            self.registro.lote_ad_hoc(handle, n, dbid_lote == dbid, texto or '', int(largo or 0))
        self.umbral_ad_hoc = ahora
        self.registro.muestras['estadisticas'] += 1

    def correr(self) -> dict:
        inicio, t0 = _ahora(), time.monotonic()
        ultimo = 0.0
        while not (self.parar or self.detener_en.exists() or time.monotonic() > self.limite):
            ahora = time.monotonic()
            try:
                self.muestrear(estadisticas=ahora - ultimo >= self.cada_estadisticas)
                if ahora - ultimo >= self.cada_estadisticas:
                    ultimo = ahora
            except Exception as error:  # noqa: BLE001 (servidor que aún no levanta o que se reinicia: se reintenta)
                self._error(error)
                self._cerrar_conexion()
            time.sleep(self.intervalo)
        cierre = self.cerrar()
        return self.informe(inicio, time.monotonic() - t0, cierre)

    def cerrar(self) -> dict:
        """Última muestra de estadísticas y lo que sólo se lee al final (Query Store, jobs, catálogo, bitácora)."""
        cierre: dict = {}
        for intento in range(3):
            try:
                if self.conexion is None:
                    self.conexion = self._conectar()
                    self.conecto = True
                cursor = self.conexion.cursor()
                self.estadisticas(cursor)
                cierre = {'query_store': self._query_store(cursor), 'jobs': self._jobs(cursor),
                          'catalogo': self._catalogo(cursor), 'bitacora': self._bitacora(cursor)}
                break
            except Exception as error:  # noqa: BLE001
                self._error(error)
                self._cerrar_conexion()
                cierre = {'error_al_cerrar': f'intento {intento + 1}: {type(error).__name__}: {str(error)[:300]}'}
                time.sleep(2)
        self._cerrar_conexion()
        return cierre

    def _query_store(self, cursor) -> dict:
        cursor.execute(Q_QUERY_STORE_ESTADO)
        fila = cursor.fetchone()
        estado = {'estado': fila[0], 'captura': fila[1]} if fila else {'estado': None, 'captura': None}
        cursor.execute(Q_QUERY_STORE)
        objetos = {}
        for esquema, nombre, n in cursor.fetchall():
            if nombre:
                objetos[f'{esquema}.{nombre}'.lower()] = int(n or 0)
                self.registro.ejecutado(esquema, nombre, self.registro.conocidos.get(
                    f'{esquema}.{nombre}'.lower(), 'P'), 'query_store', n)
        return {**estado, 'objetos': objetos}

    def _jobs(self, cursor) -> list[dict]:
        cursor.execute(Q_JOBS)
        resultado = []
        for nombre, habilitado, historial, actividad in cursor.fetchall():
            resultado.append({'job': nombre, 'habilitado': bool(habilitado), 'ejecuciones_en_historial': historial,
                              'arranques_en_actividad': actividad})
            if historial or actividad:
                self.registro.ejecutado_id(f'job:{nombre}', 'job', 'msdb.dbo.sysjobhistory', historial or actividad)
        return resultado

    def _catalogo(self, cursor) -> dict:
        cursor.execute(Q_CATALOGO)
        modulos = [{'id': f'{e}.{n}'.lower(), 'tipo': TIPOS.get(t, t)} for e, n, t in cursor.fetchall()]
        cursor.execute(Q_CATALOGO_JOBS)
        return {'modulos': modulos, 'jobs': [f'job:{n}' for (n,) in cursor.fetchall()]}

    def _bitacora(self, cursor) -> dict:
        cursor.execute(Q_BITACORA)
        return {'origen': 'dbo.bitacora.usuario (SUSER_SNAME() que guarda el trigger)',
                'usuarios': [{'login': u, 'filas': n, 'primera': a, 'ultima': b} for u, n, a, b in cursor.fetchall()]}

    def informe(self, inicio: str, segundos: float, cierre: dict) -> dict:
        resumen = self.registro.resumen()
        return {
            'version': 1,
            'que_es': 'lo que el servidor del legado ejecutó y quién se conectó durante ./ciclo.sh (corte/observar.py)',
            'ci': {k: os.environ.get(v) for k, v in (('repositorio', 'GITHUB_REPOSITORY'), ('corrida', 'GITHUB_RUN_ID'),
                                                     ('intento', 'GITHUB_RUN_ATTEMPT'), ('sha', 'GITHUB_SHA'),
                                                     ('rama', 'GITHUB_HEAD_REF'))},
            'inicio_utc': inicio, 'fin_utc': _ahora(), 'segundos': round(segundos, 1),
            'intervalos': {'sesiones_s': self.intervalo, 'estadisticas_s': self.cada_estadisticas},
            'muestras': resumen['muestras'], 'servidor': self.servidor,
            'errores': {'antes_de_conectar': self.errores_antes_de_conectar, 'despues': len(self.errores),
                        'ultimos': self.errores},
            'consumidores': resumen['consumidores'], 'objetos_ejecutados': resumen['objetos_ejecutados'],
            'quien_ejecuta': resumen['quien_ejecuta'], 'ad_hoc': resumen['ad_hoc'],
            'ad_hoc_sin_objetos': resumen['ad_hoc_sin_objetos'],
            **cierre,
            'terminado': 'error_al_cerrar' not in cierre and self.conecto,
        }


def detener(salida: Path, espera: float = 240.0) -> int:
    """Pide al observador que cierre y espera su informe."""
    marca = salida.with_name(salida.name + '.detener')
    marca.write_text(_ahora() + '\n', encoding='utf-8')
    pid_ruta = salida.with_name(salida.name + '.pid')
    limite = time.monotonic() + espera
    pid = int(pid_ruta.read_text(encoding='utf-8')) if pid_ruta.exists() else None
    while pid is not None and time.monotonic() < limite:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(1)
    if not salida.exists():
        print(f'el observador no dejó {salida}', file=sys.stderr)
        return 1
    informe = json.loads(salida.read_text(encoding='utf-8'))
    print(f"observación: {informe['segundos']} s · {informe['muestras']} · "
          f"{len(informe['consumidores'])} consumidores · {len(informe['objetos_ejecutados'])} objetos ejecutados · "
          f"terminado={informe['terminado']}")
    return 0 if informe['terminado'] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m corte.observar', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--salida', type=Path, help='observar hasta que se pida detener y escribir aquí el informe')
    grupo.add_argument('--detener', type=Path, help='pedir al observador que cierre y esperar su informe')
    parser.add_argument('--intervalo', type=float, default=0.25, help='segundos entre muestras de sesiones')
    parser.add_argument('--cada-estadisticas', type=float, default=5.0)
    args = parser.parse_args(argv)
    if args.detener:
        return detener(args.detener)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.with_name(args.salida.name + '.pid').write_text(f'{os.getpid()}\n', encoding='utf-8')
    observador = Observador(args.salida, args.intervalo, args.cada_estadisticas)

    def al_terminar(_senal, _marco):
        observador.parar = True
    signal.signal(signal.SIGTERM, al_terminar)
    informe = observador.correr()
    temporal = args.salida.with_name(args.salida.name + '.tmp')
    temporal.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    temporal.replace(args.salida)
    print(f"observación cerrada: {informe['muestras']} · terminado={informe['terminado']}")
    return 0 if informe['terminado'] else 1


if __name__ == '__main__':
    sys.exit(main())
