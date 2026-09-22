-- =============================================================================
-- CoachLink — rôles PostgreSQL de DEV LOCAL
--
-- Exigence Tech Lead (ARCHITECTURE.md §4, "Règle d'accès transversale") :
-- la Row Level Security est notre seconde barrière contre la fuite transversale
-- coach A -> client de coach B. Elle n'a de valeur que si le rôle utilisé par
-- l'application NE PEUT PAS la contourner. D'où deux rôles distincts :
--
--   * coachlink_owner : propriétaire du schéma, exécute les migrations Alembic.
--   * coachlink_app   : rôle applicatif, NOSUPERUSER + NOBYPASSRLS + NOCREATEDB.
--                       C'est lui (et lui seul) que l'API FastAPI utilise.
--
-- ⚠️  Rappel : en PostgreSQL, le PROPRIÉTAIRE d'une table contourne nativement
--     ses propres policies RLS. Les migrations doivent donc déclarer
--     `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;`
--     ET `ALTER TABLE <t> FORCE ROW LEVEL SECURITY;`
--     sans quoi la protection serait inopérante pour le owner. -> à la charge
--     de l'agent `back` dans Alembic ; la QA doit tester le cas d'accès croisé.
--
-- Ce script n'est exécuté qu'au PREMIER démarrage du conteneur (volume vide).
-- Pour le rejouer :  docker compose down -v && docker compose up -d
--
-- ⚠️  Mots de passe de développement uniquement. En staging/prod, les rôles sont
--     provisionnés par l'hébergeur (Scaleway) et les secrets viennent du
--     gestionnaire de secrets — jamais d'un fichier du repo.
-- =============================================================================

\set ON_ERROR_STOP on

-- Rôle applicatif : volontairement bridé.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coachlink_app') THEN
        CREATE ROLE coachlink_app
            LOGIN
            PASSWORD 'coachlink_app_dev_only'
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOBYPASSRLS
            NOINHERIT;
    END IF;
END
$$;

-- Droits de connexion et d'usage du schéma public (pas de droit DDL).
-- `current_database()` et non un nom en dur : la base s'appelle `coachlink` en
-- dev local et `coachlink_test` en CI — le même script doit marcher dans les deux.
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO coachlink_app', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO coachlink_app;

-- Droits DML sur l'existant (le schéma est vide à ce stade, mais idempotent).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO coachlink_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO coachlink_app;

-- Droits DML automatiques sur les tables FUTURES créées par le owner
-- (c'est ce qui évite d'avoir à re-GRANT après chaque migration Alembic).
ALTER DEFAULT PRIVILEGES FOR ROLE coachlink_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO coachlink_app;
ALTER DEFAULT PRIVILEGES FOR ROLE coachlink_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO coachlink_app;

-- Extensions attendues par le modèle de données (ARCHITECTURE.md §4) :
--   citext   -> colonne `user.email` insensible à la casse
--   pgcrypto -> primitives crypto côté base (le chiffrement applicatif des
--               colonnes sensibles reste fait côté Python, cf. §5.1)
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
