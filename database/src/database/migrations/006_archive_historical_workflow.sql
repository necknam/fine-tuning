-- Local deployment review: archive unused historical workflow tables; retain every row/FK.
-- No CASCADE, DROP, DELETE, or synthetic catalog data. This migration is atomic.
CREATE SCHEMA IF NOT EXISTS growpath_legacy;
REVOKE ALL ON SCHEMA growpath_legacy FROM PUBLIC;
SET LOCAL lock_timeout = '5s';
DO $archive$
DECLARE name text;
BEGIN
 FOREACH name IN ARRAY ARRAY['roadmap_requests','agent_generations','agent_selections','preference_pairs','test_mock_profiles','user_skill_gap','finetuning_datasets'] LOOP
  IF to_regclass(format('public.%I',name)) IS NOT NULL THEN
   IF to_regclass(format('growpath_legacy.%I',name)) IS NOT NULL THEN
    RAISE EXCEPTION 'Archive conflict: %',name;
   END IF;
   EXECUTE format('ALTER TABLE public.%I SET SCHEMA growpath_legacy',name);
   EXECUTE format('COMMENT ON TABLE growpath_legacy.%I IS %L',name,'Historical workflow archive; retained with data and FK identity. Not a live application master.');
  END IF;
 END LOOP;
END $archive$;
-- Remove the obsolete diagnostic routine from the local serving surface.
DROP FUNCTION IF EXISTS public.show_me_everything();
