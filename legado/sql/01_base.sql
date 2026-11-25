-- Banco Ficticio del Norte (BFN) · back-office de divisas y pagos internacionales.
-- Base del legado. Se crea con la intercalación por omisión del servidor (SQL_Latin1_General_CP1_CI_AS).
IF DB_ID(N'BFN_DIVISAS') IS NULL
    CREATE DATABASE BFN_DIVISAS;
GO
ALTER DATABASE BFN_DIVISAS SET RECOVERY SIMPLE;
GO
