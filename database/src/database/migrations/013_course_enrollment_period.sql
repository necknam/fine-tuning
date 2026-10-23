-- Enrollment period only. No study/learning period or new table.
SET LOCAL TIME ZONE 'Asia/Seoul';
ALTER TABLE public.courses ADD COLUMN enrollment_start timestamptz;
ALTER TABLE public.courses ADD COLUMN enrollment_end timestamptz;
ALTER TABLE public.courses ADD COLUMN enrollment_period_type text NOT NULL DEFAULT 'unknown';
WITH latest AS (
 SELECT DISTINCT ON(entity_key) entity_key,source,payload FROM growpath_meta.catalog_api_sources
 WHERE resource_type='courses' AND source IN ('API_KMOOC','API_MS_LEARN') ORDER BY entity_key,fetched_at DESC
), parsed AS (SELECT entity_key,source,payload,CASE WHEN payload->>'enrollment_start' ~ '^[0-9]{10}([0-9]{3})?$'
 THEN to_timestamp((payload->>'enrollment_start')::numeric / CASE WHEN length(payload->>'enrollment_start')=13 THEN 1000 ELSE 1 END)
 WHEN pg_input_is_valid(payload->>'enrollment_start','timestamp with time zone') THEN (payload->>'enrollment_start')::timestamptz ELSE NULL END AS starts,CASE WHEN payload->>'enrollment_end' ~ '^[0-9]{10}([0-9]{3})?$'
 THEN to_timestamp((payload->>'enrollment_end')::numeric / CASE WHEN length(payload->>'enrollment_end')=13 THEN 1000 ELSE 1 END)
 WHEN pg_input_is_valid(payload->>'enrollment_end','timestamp with time zone') THEN (payload->>'enrollment_end')::timestamptz ELSE NULL END AS ends FROM latest)
UPDATE public.courses c SET
 enrollment_start=CASE WHEN starts<=ends OR starts IS NULL OR ends IS NULL THEN starts END,
 enrollment_end=CASE WHEN starts<=ends OR starts IS NULL OR ends IS NULL THEN ends END,
 enrollment_period_type=CASE WHEN source='API_MS_LEARN' AND coalesce(payload->>'enrollment_start','')='' AND coalesce(payload->>'enrollment_end','')='' THEN 'unrestricted'
 WHEN starts IS NOT NULL AND ends IS NOT NULL AND starts<=ends THEN 'scheduled' ELSE 'unknown' END
FROM parsed p WHERE c.course_id=p.entity_key;
ALTER TABLE public.courses ADD CONSTRAINT courses_enrollment_type_check CHECK(enrollment_period_type IN ('scheduled','unrestricted','unknown'));
ALTER TABLE public.courses ADD CONSTRAINT courses_enrollment_order_check CHECK(enrollment_start IS NULL OR enrollment_end IS NULL OR enrollment_start<=enrollment_end);
ALTER TABLE public.courses ADD CONSTRAINT courses_enrollment_values_check CHECK(
 (enrollment_period_type='scheduled' AND enrollment_start IS NOT NULL AND enrollment_end IS NOT NULL) OR
 (enrollment_period_type='unrestricted' AND enrollment_start IS NULL AND enrollment_end IS NULL) OR enrollment_period_type='unknown');
COMMENT ON COLUMN public.courses.enrollment_start IS '수강신청 시작 시각. UTC 저장, Asia/Seoul 표시';
COMMENT ON COLUMN public.courses.enrollment_end IS '수강신청 종료 시각. 종료 시각까지 신청 가능';
COMMENT ON COLUMN public.courses.enrollment_period_type IS 'scheduled=기간 지정, unrestricted=기간 제한 없음, unknown=기간 확인 필요';
CREATE VIEW public.course_availability WITH (security_invoker=true) AS
 SELECT c.*, CASE WHEN enrollment_period_type='unrestricted' THEN 'ongoing'
 WHEN enrollment_period_type<>'scheduled' THEN NULL
 WHEN CURRENT_TIMESTAMP<enrollment_start THEN 'upcoming'
 WHEN CURRENT_TIMESTAMP<=enrollment_end THEN 'ongoing' ELSE 'ended' END AS enrollment_status,
 CASE WHEN enrollment_period_type='unrestricted' THEN '기간 제한 없음'
 WHEN enrollment_period_type<>'scheduled' THEN '기간 확인 필요'
 WHEN CURRENT_TIMESTAMP<enrollment_start THEN '예정'
 WHEN CURRENT_TIMESTAMP<=enrollment_end THEN '진행중' ELSE '종료' END AS enrollment_status_label
 FROM public.courses c;
