-- Optional employee-specific suggested questions; no seed data.
CREATE TABLE public.employee_recommended_prompts (
 prompt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 employee_id integer REFERENCES public.employees(employee_id) ON DELETE CASCADE,
 prompt_text text CHECK (prompt_text IS NULL OR length(btrim(prompt_text)) > 0),
 display_order smallint CHECK (display_order BETWEEN 1 AND 3),
 updated_at timestamptz DEFAULT now(),
 CONSTRAINT employee_recommended_prompts_employee_order_key UNIQUE(employee_id,display_order)
);
COMMENT ON TABLE public.employee_recommended_prompts IS 'Optional latest employee growth questions; up to three ordered slots per employee.';
