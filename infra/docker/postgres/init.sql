-- Runs once, on first initialisation of the data volume.
-- The Alembic migration also creates the extension; doing it here as well means
-- a fresh database is usable before migrations have run.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- organisation+title near-duplicate probing
