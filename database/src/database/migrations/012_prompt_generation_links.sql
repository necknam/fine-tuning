-- Record the exact base prompt used; historical generations stay NULL.
ALTER TABLE public.projects ADD COLUMN draft_prompt_version_id uuid REFERENCES public.prompt_versions(prompt_version_id);
ALTER TABLE public.projects ADD COLUMN plan_prompt_version_id uuid REFERENCES public.prompt_versions(prompt_version_id);
ALTER TABLE public.roadmaps ADD COLUMN prompt_version_id uuid REFERENCES public.prompt_versions(prompt_version_id);
CREATE INDEX projects_draft_prompt_version_idx ON public.projects(draft_prompt_version_id);
CREATE INDEX projects_plan_prompt_version_idx ON public.projects(plan_prompt_version_id);
CREATE INDEX roadmaps_prompt_version_idx ON public.roadmaps(prompt_version_id);
ALTER TABLE public.prompt_versions DROP CONSTRAINT prompt_versions_agent_id_check;
ALTER TABLE public.prompt_versions ADD CONSTRAINT prompt_versions_agent_id_check CHECK(agent_id IN ('agent_practical','agent_certified','agent_fasttrack','agent_plan_draft','agent_plan_refine'));
INSERT INTO public.prompt_versions(agent_id,version_num,system_prompt,is_active,change_reason)
SELECT 'agent_plan_draft',1,'당신은 수석 엔터프라이즈 시스템 아키텍트입니다. 엔지니어의 프로젝트 요구사항을 분석하여 1단계 프로젝트 초안 계획(Draft Plan)을 마크다운으로 작성하세요.',true,'기존 계획 초안 지시문을 버전 관리로 연결'
WHERE NOT EXISTS(SELECT 1 FROM public.prompt_versions WHERE agent_id='agent_plan_draft');
INSERT INTO public.prompt_versions(agent_id,version_num,system_prompt,is_active,change_reason)
SELECT 'agent_plan_refine',1,'당신은 엔터프라이즈 리드 아키텍트입니다. 1단계 초안과 2단계 기술 협의 대화 전체를 통합하여 정규화된 최종 프로젝트 계획 데이터를 JSON으로 생성하세요.',true,'기존 계획 확정 지시문을 버전 관리로 연결'
WHERE NOT EXISTS(SELECT 1 FROM public.prompt_versions WHERE agent_id='agent_plan_refine');
