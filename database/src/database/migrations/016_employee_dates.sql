ALTER TABLE public.employees
 ADD COLUMN hire_date date DEFAULT NULL,
 ADD COLUMN department_start_date date DEFAULT NULL,
 ADD CONSTRAINT employees_department_start_after_hire CHECK (
  hire_date IS NULL OR department_start_date IS NULL OR department_start_date >= hire_date
 );
COMMENT ON COLUMN public.employees.hire_date IS '입사일. 미확인 시 NULL';
COMMENT ON COLUMN public.employees.department_start_date IS '현재 부서 배치 시작일. 미확인 시 NULL';
