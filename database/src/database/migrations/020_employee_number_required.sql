-- Existing missing numbers are preserved until actual numbers are registered.
DO $migration$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.employees'::regclass AND conname='employees_number_required') THEN
  ALTER TABLE public.employees ADD CONSTRAINT employees_number_required
   CHECK (employee_number IS NOT NULL AND employee_number !~ '^[[:space:]]*$') NOT VALID;
 END IF;
 IF NOT EXISTS (SELECT 1 FROM public.employees WHERE employee_number IS NULL OR employee_number ~ '^[[:space:]]*$') THEN
  ALTER TABLE public.employees VALIDATE CONSTRAINT employees_number_required;
  ALTER TABLE public.employees ALTER COLUMN employee_number SET NOT NULL;
 END IF;
END
$migration$;
