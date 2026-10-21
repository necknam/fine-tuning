"""Shared schema components used by bootstrap and incremental ingestion."""
AUDIT_DDL = '''
CREATE SCHEMA IF NOT EXISTS growpath_meta;
CREATE TABLE IF NOT EXISTS growpath_meta.catalog_api_sources (
    resource_type TEXT NOT NULL,
    source TEXT NOT NULL,
    external_key TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    mapping_evidence JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (resource_type,source,external_key)
);
ALTER TABLE growpath_meta.catalog_api_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON growpath_meta.catalog_api_sources FROM PUBLIC;
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
  REVOKE ALL ON growpath_meta.catalog_api_sources FROM anon;
 END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
  REVOKE ALL ON growpath_meta.catalog_api_sources FROM authenticated;
 END IF;
 IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN
  GRANT USAGE ON SCHEMA growpath_meta TO service_role;
  GRANT SELECT,INSERT,UPDATE,DELETE ON growpath_meta.catalog_api_sources TO service_role;
 END IF;
END $$;
'''
