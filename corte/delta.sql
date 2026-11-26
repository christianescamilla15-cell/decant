-- Delta del mismo día (S3 paso 4, ADR 0013). Lo corre `python -m corte.runbook_delta preparar` UNA vez, sobre la base
-- cerrada (la restaurada del volcado de la nocturna o la recién cargada): el volcado no lo trae, así que el delta no
-- depende de la versión del destino que lo dejó.
--
-- Registro: el delta aplicado (con su reversa y su huella previa, guardadas ANTES de escribir) y sus ensayos. A lo más
-- UN delta aplicado a la vez (índice único parcial): repetirlo se niega también en la base, no sólo en el runbook.
--
-- Roles: los de la carga por mes siguen igual (`decant_corte_aplica` sólo inserta, `decant_corte_revierte` sólo
-- borra). El delta tiene los suyos, separados entre sí:
-- - `decant_corte_delta_aplica`: INSERT en las 5 tablas con identidad y en el catálogo, y UPDATE SÓLO de las columnas
--   que el legado escribe sobre una fila ya registrada (`corte.delta.MUTABLES`): estatus y horas_liquidacion de la
--   orden, activa de la moneda. Sin DELETE.
-- - `decant_corte_delta_revierte`: DELETE en esas mismas tablas y UPDATE de esas mismas columnas (para devolver el
--   valor previo). Sin INSERT.
-- Ninguno toca el punto de no retorno ni la bitácora de acciones de negocio.

CREATE TABLE corte.carga_delta (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_sha      char(64)     NOT NULL,
    estado        text         NOT NULL CHECK (estado IN ('reversa_generada', 'aplicado', 'revertido', 'fallido')),
    plan          jsonb        NOT NULL,
    reversa       jsonb        NOT NULL,
    huella_previa jsonb        NOT NULL,
    verificacion  jsonb        NULL,
    carga_txid    bigint       NULL,
    generada_en   timestamptz  NOT NULL DEFAULT clock_timestamp(),
    aplicada_en   timestamptz  NULL,
    revertida_en  timestamptz  NULL,
    detalle       text         NULL
);
CREATE UNIQUE INDEX ux_carga_delta_un_aplicado ON corte.carga_delta ((true)) WHERE estado = 'aplicado';

CREATE TABLE corte.ensayo_delta (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_sha      char(64)     NOT NULL,
    huella_previa jsonb        NOT NULL,
    verde         boolean      NOT NULL,
    resultado     jsonb        NOT NULL,
    instante      timestamptz  NOT NULL DEFAULT clock_timestamp()
);

DO $$
BEGIN
    CREATE ROLE decant_corte_delta_aplica NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END
$$;
DO $$
BEGIN
    CREATE ROLE decant_corte_delta_revierte NOLOGIN;
EXCEPTION WHEN duplicate_object THEN NULL;
END
$$;

GRANT USAGE ON SCHEMA legado, corte TO decant_corte_delta_aplica, decant_corte_delta_revierte;
GRANT SELECT ON ALL TABLES IN SCHEMA legado, corte TO decant_corte_delta_aplica, decant_corte_delta_revierte;
-- aplicar: altas (el catálogo primero: las operaciones lo referencian)
GRANT INSERT ON legado.moneda, legado.operacion, legado.orden_pago, legado.partida_solicitada,
    legado.partida_liquidada, legado.bitacora TO decant_corte_delta_aplica;
-- reversa: bajas de esas mismas filas
GRANT DELETE ON legado.moneda, legado.operacion, legado.orden_pago, legado.partida_solicitada,
    legado.partida_liquidada, legado.bitacora TO decant_corte_delta_revierte;
-- los dos: UPDATE acotado a lo que el legado cambia sobre una fila ya registrada (aplicar pone el valor del
-- congelamiento; reversa devuelve el previo)
GRANT UPDATE (estatus, horas_liquidacion) ON legado.orden_pago TO decant_corte_delta_aplica, decant_corte_delta_revierte;
GRANT UPDATE (activa) ON legado.moneda TO decant_corte_delta_aplica, decant_corte_delta_revierte;
GRANT UPDATE (siguiente) ON legado.folio TO decant_corte_delta_aplica, decant_corte_delta_revierte;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA legado TO decant_corte_delta_aplica, decant_corte_delta_revierte;
GRANT INSERT, UPDATE ON corte.carga_delta, corte.ensayo_delta TO decant_corte_delta_aplica, decant_corte_delta_revierte;
