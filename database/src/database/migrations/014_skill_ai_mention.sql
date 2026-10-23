-- Reserved for future short AI-written skill summaries. Do not generate now.
ALTER TABLE public.skill_tags ADD COLUMN ai_mention text DEFAULT NULL;
COMMENT ON COLUMN public.skill_tags.ai_mention IS '향후 AI 생성 스킬 요약. 미생성 상태는 NULL이며 이번 변경에서는 생성하지 않음';
