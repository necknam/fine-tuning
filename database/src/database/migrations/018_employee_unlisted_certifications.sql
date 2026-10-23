ALTER TABLE public.employees
 ADD COLUMN unlisted_certifications text DEFAULT NULL,
 ADD CONSTRAINT employees_unlisted_certifications_nonblank CHECK (
  unlisted_certifications IS NULL OR length(btrim(unlisted_certifications)) > 0
 );
COMMENT ON COLUMN public.employees.unlisted_certifications IS
 '직원이 입력한 미등재 보유 자격 원문(자격명/발급기관/취득일). 시트 목록에 없는 자격과 매핑. 미입력 NULL. 검증된 자격 마스터 또는 보유 FK를 자동 생성하지 않음.';
