
DROP POLICY IF EXISTS "Engineers manage tasks" ON public.tasks;

CREATE POLICY "Engineers manage tasks in owned projects"
ON public.tasks
FOR ALL
TO authenticated
USING (
  private.has_any_role(auth.uid(), ARRAY['engineer'::app_role,'admin'::app_role,'super_admin'::app_role])
  AND (
    private.is_admin(auth.uid())
    OR EXISTS (SELECT 1 FROM public.projects p WHERE p.id = tasks.project_id AND p.owner_id = auth.uid())
  )
)
WITH CHECK (
  private.has_any_role(auth.uid(), ARRAY['engineer'::app_role,'admin'::app_role,'super_admin'::app_role])
  AND (
    private.is_admin(auth.uid())
    OR EXISTS (SELECT 1 FROM public.projects p WHERE p.id = tasks.project_id AND p.owner_id = auth.uid())
  )
);
