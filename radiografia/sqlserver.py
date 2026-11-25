"""Contenedor LIMPIO de SQL Server para restaurar un respaldo: nada del legado vivo se reutiliza.

Se arranca un contenedor nuevo con contraseña aleatoria (por archivo de entorno, no en la línea de órdenes),
se copia el .bak, se verifica y se restaura moviendo cada archivo lógico a la carpeta de datos.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import tempfile
import time
from dataclasses import dataclass

import pymssql

# La misma versión que el legado (legado/docker-compose.yml); una prueba exige que coincidan.
IMAGEN = ('mcr.microsoft.com/mssql/server:2022-CU28-ubuntu-22.04'
          '@sha256:4525e3efac9f3e241cb003bb2ff2a82818b502f37e12049d788b1a9fa7e13b7f')
CARPETA = '/var/opt/mssql/backup'

_RESTAURAR = """
DECLARE @disco nvarchar(400) = %s, @base sysname = %s, @destino nvarchar(400) = N'/var/opt/mssql/data/';
DECLARE @archivos TABLE (LogicalName nvarchar(128), PhysicalName nvarchar(260), [Type] char(1),
    FileGroupName nvarchar(128), Size numeric(20, 0), MaxSize numeric(20, 0), FileId bigint, CreateLSN numeric(25, 0),
    DropLSN numeric(25, 0), UniqueId uniqueidentifier, ReadOnlyLSN numeric(25, 0), ReadWriteLSN numeric(25, 0),
    BackupSizeInBytes bigint, SourceBlockSize int, FileGroupId int, LogGroupGUID uniqueidentifier,
    DifferentialBaseLSN numeric(25, 0), DifferentialBaseGUID uniqueidentifier, IsReadOnly bit, IsPresent bit,
    TDEThumbprint varbinary(32), SnapshotUrl nvarchar(360));
DECLARE @literal nvarchar(800) = N'''' + REPLACE(@disco, N'''', N'''''') + N'''';
INSERT INTO @archivos EXEC (N'RESTORE FILELISTONLY FROM DISK = ' + @literal);
DECLARE @mover nvarchar(max) = N'';
SELECT @mover += N', MOVE N''' + REPLACE(LogicalName, N'''', N'''''') + N''' TO N'''
       + REPLACE(@destino + @base + N'_' + LogicalName
                 + CASE [Type] WHEN 'L' THEN N'.ldf' WHEN 'S' THEN N'' ELSE N'.mdf' END, N'''', N'''''') + N''''
FROM @archivos;
DECLARE @sql nvarchar(max) = N'RESTORE DATABASE ' + QUOTENAME(@base) + N' FROM DISK = ' + @literal
    + N' WITH RECOVERY, STATS = 50' + @mover;
EXEC (@sql);
"""


@dataclass
class Servidor:
    contenedor: str
    puerto: int
    contrasena: str
    propio: bool          # lo creamos nosotros: se borra al terminar

    def conectar(self, base: str = 'master') -> pymssql.Connection:
        return pymssql.connect(server='127.0.0.1', port=self.puerto, user='sa', password=self.contrasena,
                               database=base, autocommit=True, tds_version='7.4', charset='UTF-8',
                               login_timeout=15, timeout=3600)

    def copiar(self, ruta: str) -> str:
        _docker('exec', self.contenedor, 'mkdir', '-p', CARPETA)
        destino = f'{CARPETA}/{os.path.basename(ruta)}'
        _docker('cp', ruta, f'{self.contenedor}:{destino}')
        # docker cp conserva el dueño y los permisos del anfitrión: el usuario mssql debe poder leerlo
        _docker('exec', '-u', '0', self.contenedor, 'chmod', '0644', destino)
        return destino

    def verificar(self, disco: str) -> str:
        """RESTORE VERIFYONLY con CHECKSUM si el respaldo los trae; devuelve qué se pudo verificar."""
        with self.conectar() as conexion:
            cursor = conexion.cursor()
            try:
                cursor.execute('RESTORE VERIFYONLY FROM DISK = %s WITH CHECKSUM', (disco,))
                return 'íntegro (VERIFYONLY con CHECKSUM)'
            except pymssql.DatabaseError as error:
                if '3187' not in str(error):
                    raise
            cursor.execute('RESTORE VERIFYONLY FROM DISK = %s', (disco,))
            return 'legible (VERIFYONLY; el respaldo no trae CHECKSUM)'

    def restaurar(self, disco: str, base: str) -> float:
        t0 = time.perf_counter()
        with self.conectar() as conexion:
            cursor = conexion.cursor()
            cursor.execute(_RESTAURAR, (disco, base))
            while cursor.nextset():
                pass
        return time.perf_counter() - t0

    def cerrar(self) -> None:
        if self.propio:
            subprocess.run(['docker', 'rm', '-f', self.contenedor], capture_output=True, check=False)


def _docker(*argumentos: str) -> str:
    return subprocess.run(['docker', *argumentos], check=True, capture_output=True, text=True).stdout.strip()


def arrancar_limpio(memoria_mb: int = 4096) -> Servidor:
    nombre = f'decant-radiografia-{secrets.token_hex(4)}'
    contrasena = 'Rx!' + secrets.token_urlsafe(24) + 'a1'
    with tempfile.NamedTemporaryFile('w', suffix='.env', delete=False) as entorno:
        entorno.write(f'ACCEPT_EULA=Y\nMSSQL_PID=Developer\nMSSQL_SA_PASSWORD={contrasena}\n'
                      f'MSSQL_MEMORY_LIMIT_MB={memoria_mb - 512}\n')
    try:
        os.chmod(entorno.name, 0o600)
        _docker('run', '-d', '--name', nombre, '--env-file', entorno.name, '--memory', f'{memoria_mb}m',
                '-p', '127.0.0.1::1433', IMAGEN)
    finally:
        os.unlink(entorno.name)
    puerto = int(_docker('port', nombre, '1433/tcp').splitlines()[0].rsplit(':', 1)[1])
    servidor = Servidor(nombre, puerto, contrasena, propio=True)
    _esperar(servidor)
    return servidor


def existente(contenedor: str, puerto: int, contrasena: str) -> Servidor:
    servidor = Servidor(contenedor, puerto, contrasena, propio=False)
    _esperar(servidor)
    return servidor


def _esperar(servidor: Servidor, segundos: int = 180) -> None:
    limite = time.monotonic() + segundos
    while True:
        try:
            with servidor.conectar() as conexion:
                conexion.cursor().execute('SELECT 1')
            return
        except pymssql.Error:
            if time.monotonic() > limite:
                raise
            time.sleep(2)
