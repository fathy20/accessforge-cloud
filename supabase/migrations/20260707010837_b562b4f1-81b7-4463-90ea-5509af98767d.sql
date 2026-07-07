
-- 1. Private schema for internal helpers (not exposed via the Data API)
CREATE SCHEMA IF NOT EXISTS private;
GRANT USAGE ON SCHEMA private TO authenticated, anon, service_role;

-- 2. Move SECURITY DEFINER helpers into the private schema.
--    Policies reference these functions by OID, so ALTER ... SET SCHEMA
--    keeps every existing policy working transparently.
ALTER FUNCTION public.has_role(uuid, public.app_role)      SET SCHEMA private;
ALTER FUNCTION public.has_any_role(uuid, public.app_role[]) SET SCHEMA private;
ALTER FUNCTION public.is_admin(uuid)                        SET SCHEMA private;
ALTER FUNCTION public.is_user_active(uuid)                  SET SCHEMA private;
ALTER FUNCTION public.has_module_access(uuid, text, boolean) SET SCHEMA private;
ALTER FUNCTION public.handle_new_user()                     SET SCHEMA private;

-- 3. Lock down execute privileges on the moved definer functions.
REVOKE ALL ON FUNCTION private.has_role(uuid, public.app_role)       FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.has_any_role(uuid, public.app_role[]) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.is_admin(uuid)                        FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.is_user_active(uuid)                  FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.has_module_access(uuid, text, boolean) FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.handle_new_user()                     FROM PUBLIC, anon, authenticated;

-- authenticated still needs EXECUTE so RLS policies that call these helpers work
GRANT EXECUTE ON FUNCTION private.has_role(uuid, public.app_role)       TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.has_any_role(uuid, public.app_role[]) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.is_admin(uuid)                        TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.is_user_active(uuid)                  TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.has_module_access(uuid, text, boolean) TO authenticated, service_role;

-- 4. Recreate the auth trigger against the moved function.
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION private.handle_new_user();

-- 5. Tighten broad SELECT policies to per-owner / per-project scope.

-- projects
DROP POLICY IF EXISTS "Authenticated view projects" ON public.projects;
CREATE POLICY "Owners or admins view projects" ON public.projects
  FOR SELECT TO authenticated
  USING (owner_id = auth.uid() OR private.is_admin(auth.uid()));

-- uploads
DROP POLICY IF EXISTS "Authenticated view uploads" ON public.uploads;
CREATE POLICY "Uploader project-owner or admin view uploads" ON public.uploads
  FOR SELECT TO authenticated
  USING (
    uploader_id = auth.uid()
    OR private.is_admin(auth.uid())
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = uploads.project_id AND p.owner_id = auth.uid()
    )
  );

-- jobs
DROP POLICY IF EXISTS "Authenticated view jobs" ON public.jobs;
CREATE POLICY "Creator project-owner or admin view jobs" ON public.jobs
  FOR SELECT TO authenticated
  USING (
    created_by = auth.uid()
    OR private.is_admin(auth.uid())
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = jobs.project_id AND p.owner_id = auth.uid()
    )
  );

-- tasks
DROP POLICY IF EXISTS "Authenticated view tasks" ON public.tasks;
CREATE POLICY "Project members or admin view tasks" ON public.tasks
  FOR SELECT TO authenticated
  USING (
    private.is_admin(auth.uid())
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = tasks.project_id AND p.owner_id = auth.uid()
    )
  );

-- job_logs
DROP POLICY IF EXISTS "Authenticated view job logs" ON public.job_logs;
CREATE POLICY "Job owner or admin view job logs" ON public.job_logs
  FOR SELECT TO authenticated
  USING (
    private.is_admin(auth.uid())
    OR EXISTS (
      SELECT 1 FROM public.jobs j
      WHERE j.id = job_logs.job_id
        AND (
          j.created_by = auth.uid()
          OR EXISTS (
            SELECT 1 FROM public.projects p
            WHERE p.id = j.project_id AND p.owner_id = auth.uid()
          )
        )
    )
  );

-- modules: hide disabled modules from non-admins
DROP POLICY IF EXISTS "Authenticated view modules" ON public.modules;
CREATE POLICY "Enabled modules visible or admin" ON public.modules
  FOR SELECT TO authenticated
  USING (enabled = true OR private.is_admin(auth.uid()));
