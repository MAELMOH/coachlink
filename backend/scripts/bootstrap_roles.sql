-- CoachLink — PostgreSQL role bootstrap.
--
-- Run ONCE per database, as a superuser, BEFORE the first Alembic migration.
-- Passwords are injected by the operator (psql -v) and never stored in this repo.
--
--   psql -v app_password="$APP_PASSWORD" -v owner_password="$OWNER_PASSWORD" \
--        -f scripts/bootstrap_roles.sql
--
-- WHY TWO ROLES. Row Level Security is only a real barrier when the connecting
-- role can neither bypass it nor own the tables:
--   * a SUPERUSER bypasses every policy, silently;
--   * a table OWNER also bypasses its own policies unless FORCE ROW LEVEL
--     SECURITY is set — and can simply drop them anyway.
-- So the API connects as coachlink_app (NOSUPERUSER, NOBYPASSRLS, owns nothing)
-- and migrations run as coachlink_owner.

\set ON_ERROR_STOP on

-- NOTE: psql does NOT substitute :variables inside dollar-quoted $$ blocks, so
-- role creation goes through \gexec (a plain SELECT, where substitution works).

-- Owner / migration role -----------------------------------------------------
SELECT format('CREATE ROLE coachlink_owner LOGIN PASSWORD %L', :'owner_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coachlink_owner')
\gexec

SELECT format('ALTER ROLE coachlink_owner PASSWORD %L', :'owner_password')
\gexec

ALTER ROLE coachlink_owner NOSUPERUSER NOBYPASSRLS NOCREATEROLE;

-- Application role -----------------------------------------------------------
SELECT format('CREATE ROLE coachlink_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coachlink_app')
\gexec

SELECT format('ALTER ROLE coachlink_app PASSWORD %L', :'app_password')
\gexec

-- The three NO* flags below are the whole point of this file.
ALTER ROLE coachlink_app NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB NOINHERIT;

-- Schema privileges ----------------------------------------------------------
ALTER SCHEMA public OWNER TO coachlink_owner;
GRANT USAGE ON SCHEMA public TO coachlink_app;

-- The app may read/write rows, but never change the schema and never create a
-- table it would then own (owning one would let it escape its own policies).
REVOKE CREATE ON SCHEMA public FROM coachlink_app;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO coachlink_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO coachlink_app;

-- Same grants for tables created later by Alembic.
ALTER DEFAULT PRIVILEGES FOR ROLE coachlink_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO coachlink_app;
ALTER DEFAULT PRIVILEGES FOR ROLE coachlink_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO coachlink_app;

-- Extensions (superuser-only, hence here rather than in a migration).
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;    -- case-insensitive e-mail uniqueness

-- Self-check: fails loudly rather than leaving a cosmetic barrier in place.
DO $$
DECLARE
    is_super boolean;
    can_bypass boolean;
BEGIN
    SELECT rolsuper, rolbypassrls INTO is_super, can_bypass
    FROM pg_roles WHERE rolname = 'coachlink_app';

    IF is_super OR can_bypass THEN
        RAISE EXCEPTION
            'coachlink_app must be NOSUPERUSER and NOBYPASSRLS (super=%, bypassrls=%)',
            is_super, can_bypass;
    END IF;
END
$$;
