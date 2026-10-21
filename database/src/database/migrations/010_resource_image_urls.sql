-- Optional official book covers and certification badge images. No generated URLs.
ALTER TABLE public.books ADD COLUMN IF NOT EXISTS image_url text;
ALTER TABLE public.certifications ADD COLUMN IF NOT EXISTS image_url text;
WITH images AS (
 SELECT entity_key,fetched_at,
 coalesce(nullif(trim(payload#>>'{detail_record,bookImageURL}'),''),nullif(trim(payload#>>'{list_record,bookImageURL}'),''),nullif(trim(payload->>'bookImageURL'),'')) AS url
 FROM growpath_meta.catalog_api_sources WHERE resource_type='books' AND source='API_DATA4LIBRARY'
), chosen AS (
 SELECT DISTINCT ON(entity_key) entity_key,url FROM images
 WHERE url ~ '^https?://[^/@[:space:]]+([/:?][^[:space:]]*)?$' ORDER BY entity_key,fetched_at DESC
)
UPDATE public.books b SET image_url=x.url FROM chosen x WHERE b.isbn=x.entity_key AND b.image_url IS NULL;
WITH images AS (
 SELECT entity_key,fetched_at,
 coalesce(nullif(trim(payload#>>'{merged_certification,social_image_url}'),''),nullif(trim(payload#>>'{merged_certification,icon_url}'),''),
 nullif(trim(payload#>>'{certification,social_image_url}'),''),nullif(trim(payload#>>'{certification,icon_url}'),''),
 nullif(trim(payload->>'social_image_url'),''),nullif(trim(payload->>'icon_url'),'')) AS url
 FROM growpath_meta.catalog_api_sources WHERE resource_type='certifications' AND source='API_MS_CERT'
), chosen AS (
 SELECT DISTINCT ON(entity_key) entity_key,url FROM images
 WHERE url ~ '^https?://[^/@[:space:]]+([/:?][^[:space:]]*)?$' ORDER BY entity_key,fetched_at DESC
)
UPDATE public.certifications t SET image_url=x.url FROM chosen x WHERE t.cert_id::text=x.entity_key AND t.image_url IS NULL;
