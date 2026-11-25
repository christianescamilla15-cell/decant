"""Las noches del job: el reloj que el replay debe inyectar (T8) en lugar de GETDATE().

Salen de dos fuentes del respaldo: el horario del job en la copia restaurada de msdb y los sellos que dejó el
trigger cuando escribía el usuario del Agent (`svc_agente`). Si las dos no cuadran, hay noches que no corrieron o
corridas manuales.
"""
from __future__ import annotations

from datetime import datetime

USUARIO_AGENTE = 'svc_agente'


def noches(cursor) -> list[datetime]:
    """Instantes (hora local del servidor) en que corrió el job, según la bitácora."""
    cursor.execute('SELECT DISTINCT fecha FROM dbo.bitacora WHERE usuario = %s ORDER BY fecha', (USUARIO_AGENTE,))
    return [fila[0] for fila in cursor.fetchall()]


def horario(cursor, base_msdb: str, base: str) -> list[dict]:
    """Horario declarado del job en msdb (para cuadrarlo contra las noches de la bitácora)."""
    cursor.execute("""
        DECLARE @sql nvarchar(max) = N'
            SELECT j.name, sc.freq_type, sc.freq_interval, sc.active_start_time
            FROM ' + QUOTENAME(%s) + N'.dbo.sysjobs j
            JOIN ' + QUOTENAME(%s) + N'.dbo.sysjobsteps s ON s.job_id = j.job_id
            JOIN ' + QUOTENAME(%s) + N'.dbo.sysjobschedules js ON js.job_id = j.job_id
            JOIN ' + QUOTENAME(%s) + N'.dbo.sysschedules sc ON sc.schedule_id = js.schedule_id
            WHERE s.database_name = @base';
        EXEC sp_executesql @sql, N'@base sysname', @base = %s""", (base_msdb,) * 4 + (base,))
    return [{'job': n, 'frecuencia': f, 'intervalo': i, 'hora': f'{h // 10000:02d}:{h // 100 % 100:02d}'}
            for n, f, i, h in cursor.fetchall()]


def cuadre(instantes: list[datetime], hora: str) -> dict:
    """¿Todas las noches de la bitácora caen a la hora del horario? Cuenta las que no."""
    fuera = [i for i in instantes if i.strftime('%H:%M') != hora]
    return {'noches': len(instantes), 'a_la_hora_del_horario': len(instantes) - len(fuera), 'fuera_de_horario': fuera}
