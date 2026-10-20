-- OBSOLETE historical schema. Canonical schema: src/db/migrations + deployment.CATALOG.
-- Use: python scripts/db.py --db-env TARGET_DB_URL bootstrap --input data/transfer/source_001
-- This file intentionally fails before any DDL; it must not create a conflicting BIGINT schema.
DO $$ BEGIN
 RAISE EXCEPTION 'Obsolete schema.sql: use scripts/db.py bootstrap/migrate and src/db/migrations';
END $$;
