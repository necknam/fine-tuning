-- Employee-authored context available before project creation or assessment.
ALTER TABLE public.employees
 ADD COLUMN planned_project_description text DEFAULT NULL,
 ADD CONSTRAINT employees_planned_project_description_nonblank CHECK (
  planned_project_description IS NULL OR length(btrim(planned_project_description)) > 0
 );
COMMENT ON COLUMN public.employees.planned_project_description IS
 '설문 이전 추천 질문 생성용 본인 업무·구상 중인 프로젝트 설명. 시트 본인 업무 설명과 매핑. 미입력 시 NULL. 생성된 질문이나 확정 프로젝트 계획이 아님.';
