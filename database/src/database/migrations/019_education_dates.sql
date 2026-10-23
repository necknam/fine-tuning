ALTER TABLE public.employee_education_records
 ADD COLUMN enrollment_date date DEFAULT NULL,
 ADD COLUMN graduation_date date DEFAULT NULL,
 ADD CONSTRAINT employee_education_dates_order CHECK (
  enrollment_date IS NULL OR graduation_date IS NULL OR graduation_date >= enrollment_date
 );
COMMENT ON COLUMN public.employee_education_records.enrollment_date IS
 '입학일. 시트 입학일과 매핑. 정확한 날짜 미확인 시 NULL; 연도로 날짜를 추정하지 않음.';
COMMENT ON COLUMN public.employee_education_records.graduation_date IS
 '졸업일. 시트 졸업일과 매핑. 재학 중 또는 정확한 날짜 미확인 시 NULL.';
