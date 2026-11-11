-- 001_create_document_extractions.sql
--
-- DESACTIVADO: el servicio ya no usa base de datos. NO es necesario ejecutar este script.
-- Se conserva por si se reactiva la persistencia (ver app/infrastructure/persistence/__init__.py).
--
-- Esquema propio del servicio document-autofill-cafelab.
--
-- Guarda SOLO lo que se leyó de cada guía (campos y advertencias), NUNCA el archivo.
-- Sirve para la idempotencia: el mismo archivo enviado por el mismo usuario
-- (mismo file_hash) devuelve el resultado guardado sin volver a llamar a Document AI.
--
-- Ejecutarlo una sola vez, con el mismo usuario que usa el servicio en DATABASE_URL.
-- Es seguro repetirlo: no borra ni cambia datos existentes.

BEGIN;

CREATE SCHEMA IF NOT EXISTS document_autofill;

CREATE TABLE IF NOT EXISTS document_autofill.document_extractions (
    id                bigserial    PRIMARY KEY,
    user_id           bigint       NOT NULL,
    file_hash         char(64)     NOT NULL,  -- SHA-256 en hex de (bytes del archivo + userId)
    result            jsonb        NOT NULL,  -- { "fields": {...}, "warnings": [...] }
    processor_version text,                   -- versión del procesador, si se configuró
    created_at        timestamptz  DEFAULT now(),
    CONSTRAINT uq_document_extractions_user_file UNIQUE (user_id, file_hash)
);

COMMENT ON TABLE document_autofill.document_extractions IS
    'Resultados de Document AI por usuario y archivo (SHA-256). No guarda el archivo.';

-- Supabase expone las tablas por su API REST según los permisos de cada esquema.
-- Con RLS activo y sin políticas, nadie puede leer esta tabla por esa API.
-- El servicio no se ve afectado: se conecta como dueño de la tabla, y el dueño no pasa por RLS.
ALTER TABLE document_autofill.document_extractions ENABLE ROW LEVEL SECURITY;

COMMIT;
