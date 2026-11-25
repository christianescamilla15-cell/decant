-- Job nocturno del legado. Vive en msdb, no en la base: un respaldo sólo de BFN_DIVISAS no lo trae.
USE msdb;
GO
IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'BFN - conciliacion nocturna')
    EXEC msdb.dbo.sp_delete_job @job_name = N'BFN - conciliacion nocturna';
GO
EXEC msdb.dbo.sp_add_job
    @job_name = N'BFN - conciliacion nocturna',
    @enabled = 1,
    @description = N'Concilia las órdenes liquidadas y vence las que siguen enviadas.';
EXEC msdb.dbo.sp_add_jobstep
    @job_name = N'BFN - conciliacion nocturna',
    @step_name = N'conciliar',
    @subsystem = N'TSQL',
    @database_name = N'BFN_DIVISAS',
    @command = N'EXEC dbo.sp_conciliar;';
EXEC msdb.dbo.sp_add_jobschedule
    @job_name = N'BFN - conciliacion nocturna',
    @name = N'todas las noches 23:30',
    @freq_type = 4,
    @freq_interval = 1,
    @active_start_time = 233000;
EXEC msdb.dbo.sp_add_jobserver @job_name = N'BFN - conciliacion nocturna';
GO
