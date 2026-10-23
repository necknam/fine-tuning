-- Correction: short AI summaries belong to learning resources, not skill tags.
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM public.skill_tags WHERE ai_mention IS NOT NULL) THEN
  RAISE EXCEPTION 'skill_tags.ai_mention contains data; preserved for review';
 END IF;
END $$;
ALTER TABLE public.skill_tags DROP COLUMN ai_mention;
ALTER TABLE public.courses ADD COLUMN ai_mention text DEFAULT NULL;
ALTER TABLE public.books ADD COLUMN ai_mention text DEFAULT NULL;
ALTER TABLE public.certifications ADD COLUMN ai_mention text DEFAULT NULL;
COMMENT ON COLUMN public.courses.ai_mention IS '향후 AI 생성 강좌 요약. 현재 미생성 NULL';
COMMENT ON COLUMN public.books.ai_mention IS '향후 AI 생성 도서 요약. 현재 미생성 NULL';
COMMENT ON COLUMN public.certifications.ai_mention IS '향후 AI 생성 자격증 요약. 현재 미생성 NULL';
