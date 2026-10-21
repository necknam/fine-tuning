-- Store optional official API images with the course itself.
ALTER TABLE public.courses ADD COLUMN IF NOT EXISTS image_url text;
WITH images AS (
 SELECT s.entity_key,s.fetched_at,s.source,
 CASE WHEN s.source='API_KMOOC' THEN nullif(trim(s.payload->>'course_image'),'')
      WHEN s.source='API_MS_LEARN' THEN coalesce(nullif(trim(s.payload->>'social_image_url'),''),nullif(trim(s.payload->>'icon_url'),'')) END AS url
 FROM growpath_meta.catalog_api_sources s
 WHERE s.resource_type='courses' AND s.source IN ('API_KMOOC','API_MS_LEARN')
), chosen AS (
 SELECT DISTINCT ON (entity_key) entity_key,url FROM images
 WHERE url ~ '^https?://[^/@[:space:]]+([/:?][^[:space:]]*)?$'
 ORDER BY entity_key,fetched_at DESC,source
)
UPDATE public.courses c SET image_url=x.url FROM chosen x WHERE c.course_id=x.entity_key AND c.image_url IS NULL;
