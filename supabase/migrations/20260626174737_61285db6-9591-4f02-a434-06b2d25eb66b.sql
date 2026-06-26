
-- =========================================================
-- Extensions
-- =========================================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- =========================================================
-- Enums
-- =========================================================
CREATE TYPE public.app_role AS ENUM ('super_admin', 'admin', 'engineer', 'viewer', 'guest');
CREATE TYPE public.job_status AS ENUM ('queued', 'running', 'done', 'failed', 'cancelled');
CREATE TYPE public.upload_kind AS ENUM ('pdf', 'excel', 'docx', 'csv', 'image', 'other');

-- =========================================================
-- Shared utility
-- =========================================================
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

-- =========================================================
-- profiles
-- =========================================================
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT,
  avatar_url TEXT,
  department TEXT,
  job_title TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
GRANT ALL ON public.profiles TO service_role;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- =========================================================
-- user_roles (separate to prevent privilege escalation)
-- =========================================================
CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  granted_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);
GRANT SELECT ON public.user_roles TO authenticated;
GRANT ALL ON public.user_roles TO service_role;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

-- =========================================================
-- Security definer role helpers
-- =========================================================
CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role public.app_role)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = _role
  );
$$;

CREATE OR REPLACE FUNCTION public.has_any_role(_user_id UUID, _roles public.app_role[])
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = ANY(_roles)
  );
$$;

CREATE OR REPLACE FUNCTION public.is_admin(_user_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT public.has_any_role(_user_id, ARRAY['admin','super_admin']::public.app_role[]);
$$;

-- =========================================================
-- profiles & user_roles policies
-- =========================================================
CREATE POLICY "Users view own profile"
  ON public.profiles FOR SELECT TO authenticated
  USING (id = auth.uid() OR public.is_admin(auth.uid()));

CREATE POLICY "Users update own profile"
  ON public.profiles FOR UPDATE TO authenticated
  USING (id = auth.uid()) WITH CHECK (id = auth.uid());

CREATE POLICY "Admins update any profile"
  ON public.profiles FOR UPDATE TO authenticated
  USING (public.is_admin(auth.uid()));

CREATE POLICY "Users insert own profile"
  ON public.profiles FOR INSERT TO authenticated
  WITH CHECK (id = auth.uid());

CREATE POLICY "Users view own roles"
  ON public.user_roles FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin(auth.uid()));

CREATE POLICY "Admins manage roles"
  ON public.user_roles FOR ALL TO authenticated
  USING (public.is_admin(auth.uid()))
  WITH CHECK (public.is_admin(auth.uid()));

-- =========================================================
-- handle_new_user: auto create profile + default guest role
-- =========================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name, avatar_url)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', split_part(NEW.email,'@',1)),
    NEW.raw_user_meta_data->>'avatar_url'
  )
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'guest'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- =========================================================
-- modules (catalog) + module_access
-- =========================================================
CREATE TABLE public.modules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  icon TEXT,
  category TEXT,
  enabled BOOLEAN NOT NULL DEFAULT true,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.modules TO authenticated;
GRANT ALL ON public.modules TO service_role;
ALTER TABLE public.modules ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated view modules"
  ON public.modules FOR SELECT TO authenticated USING (true);

CREATE POLICY "Admins manage modules"
  ON public.modules FOR ALL TO authenticated
  USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));

CREATE TABLE public.module_access (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  module_id UUID NOT NULL REFERENCES public.modules(id) ON DELETE CASCADE,
  can_view BOOLEAN NOT NULL DEFAULT true,
  can_run BOOLEAN NOT NULL DEFAULT false,
  granted_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, module_id)
);
GRANT SELECT ON public.module_access TO authenticated;
GRANT ALL ON public.module_access TO service_role;
ALTER TABLE public.module_access ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users view own module access"
  ON public.module_access FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_admin(auth.uid()));

CREATE POLICY "Admins manage module access"
  ON public.module_access FOR ALL TO authenticated
  USING (public.is_admin(auth.uid())) WITH CHECK (public.is_admin(auth.uid()));

CREATE OR REPLACE FUNCTION public.has_module_access(_user_id UUID, _module_key TEXT, _need_run BOOLEAN DEFAULT false)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    public.is_admin(_user_id)
    OR EXISTS (
      SELECT 1 FROM public.module_access ma
      JOIN public.modules m ON m.id = ma.module_id
      WHERE ma.user_id = _user_id
        AND m.key = _module_key
        AND m.enabled = true
        AND (CASE WHEN _need_run THEN ma.can_run ELSE ma.can_view END)
    );
$$;

-- Seed default modules
INSERT INTO public.modules (key, name, description, icon, category, sort_order) VALUES
  ('task_extractor',  'Task Extractor',       'Extract maintenance tasks from PDF documents (RegEx + OCR).', 'FileSearch',  'Processing',   10),
  ('task_stamping',   'Task Stamping',        'Stamp tail number, station, and date onto PDF documents.',   'Stamp',       'Processing',   20),
  ('effectivity',     'Effectivity',          'Load Excel data and link maintenance chapters.',             'ListChecks',  'Data',         30),
  ('check_control',   'Check Control',        'Manage maintenance checks from CSV.',                        'CheckCircle', 'Data',         40),
  ('utilization',     'Utilization',          'Track aircraft utilization with hashing & history.',         'GaugeCircle', 'Data',         50),
  ('cmp_tcm',         'CMP / TCM Tasks',      'Index TCM folder and generate indexed task cards.',          'Layers',      'Processing',   60),
  ('cover_merge',     'Cover Merge',          'Merge cover PDFs onto task cards.',                          'BookCopy',    'Processing',   70),
  ('mail_merge',      'Mail Merge (Covering)','Generate RC cards from Word templates + Excel data.',        'Mailbox',     'Processing',   80);

-- =========================================================
-- projects (workspace grouping)
-- =========================================================
CREATE TABLE public.projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  tail_number TEXT,
  station TEXT,
  owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.projects TO authenticated;
GRANT ALL ON public.projects TO service_role;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_projects_owner ON public.projects(owner_id);
CREATE INDEX idx_projects_tail  ON public.projects(tail_number);

CREATE TRIGGER trg_projects_updated_at
  BEFORE UPDATE ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

CREATE POLICY "Authenticated view projects"
  ON public.projects FOR SELECT TO authenticated USING (true);

CREATE POLICY "Engineers create projects"
  ON public.projects FOR INSERT TO authenticated
  WITH CHECK (
    owner_id = auth.uid()
    AND public.has_any_role(auth.uid(), ARRAY['engineer','admin','super_admin']::public.app_role[])
  );

CREATE POLICY "Owners or admins update projects"
  ON public.projects FOR UPDATE TO authenticated
  USING (owner_id = auth.uid() OR public.is_admin(auth.uid()));

CREATE POLICY "Owners or admins delete projects"
  ON public.projects FOR DELETE TO authenticated
  USING (owner_id = auth.uid() OR public.is_admin(auth.uid()));

-- =========================================================
-- uploads
-- =========================================================
CREATE TABLE public.uploads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES public.projects(id) ON DELETE SET NULL,
  uploader_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  storage_path TEXT NOT NULL,
  kind public.upload_kind NOT NULL DEFAULT 'other',
  original_name TEXT NOT NULL,
  mime_type TEXT,
  size_bytes BIGINT,
  sha256 TEXT,
  page_count INT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_tsv tsvector,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.uploads TO authenticated;
GRANT ALL ON public.uploads TO service_role;
ALTER TABLE public.uploads ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_uploads_project   ON public.uploads(project_id);
CREATE INDEX idx_uploads_uploader  ON public.uploads(uploader_id);
CREATE INDEX idx_uploads_sha256    ON public.uploads(sha256);
CREATE INDEX idx_uploads_search    ON public.uploads USING GIN(search_tsv);
CREATE INDEX idx_uploads_name_trgm ON public.uploads USING GIN(original_name gin_trgm_ops);

CREATE OR REPLACE FUNCTION public.uploads_update_tsv()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  NEW.search_tsv :=
    setweight(to_tsvector('simple', coalesce(NEW.original_name,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.metadata->>'title','')), 'B') ||
    setweight(to_tsvector('simple', coalesce(NEW.metadata->>'ocr_text','')), 'C');
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_uploads_tsv
  BEFORE INSERT OR UPDATE OF original_name, metadata ON public.uploads
  FOR EACH ROW EXECUTE FUNCTION public.uploads_update_tsv();

CREATE POLICY "Authenticated view uploads"
  ON public.uploads FOR SELECT TO authenticated USING (true);

CREATE POLICY "Engineers create uploads"
  ON public.uploads FOR INSERT TO authenticated
  WITH CHECK (
    uploader_id = auth.uid()
    AND public.has_any_role(auth.uid(), ARRAY['engineer','admin','super_admin']::public.app_role[])
  );

CREATE POLICY "Uploader or admin update uploads"
  ON public.uploads FOR UPDATE TO authenticated
  USING (uploader_id = auth.uid() OR public.is_admin(auth.uid()));

CREATE POLICY "Uploader or admin delete uploads"
  ON public.uploads FOR DELETE TO authenticated
  USING (uploader_id = auth.uid() OR public.is_admin(auth.uid()));

-- =========================================================
-- jobs + job_logs
-- =========================================================
CREATE TABLE public.jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES public.projects(id) ON DELETE SET NULL,
  module_key TEXT NOT NULL,
  status public.job_status NOT NULL DEFAULT 'queued',
  progress INT NOT NULL DEFAULT 0,
  input_refs JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_refs JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT,
  created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  worker_id TEXT
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.jobs TO authenticated;
GRANT ALL ON public.jobs TO service_role;
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_jobs_status     ON public.jobs(status);
CREATE INDEX idx_jobs_module     ON public.jobs(module_key);
CREATE INDEX idx_jobs_project    ON public.jobs(project_id);
CREATE INDEX idx_jobs_created_by ON public.jobs(created_by);

CREATE POLICY "Authenticated view jobs"
  ON public.jobs FOR SELECT TO authenticated USING (true);

CREATE POLICY "Engineers create jobs with module access"
  ON public.jobs FOR INSERT TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND public.has_module_access(auth.uid(), module_key, true)
  );

CREATE POLICY "Creator or admin update jobs"
  ON public.jobs FOR UPDATE TO authenticated
  USING (created_by = auth.uid() OR public.is_admin(auth.uid()));

CREATE POLICY "Admins delete jobs"
  ON public.jobs FOR DELETE TO authenticated
  USING (public.is_admin(auth.uid()));

CREATE TABLE public.job_logs (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  level TEXT NOT NULL DEFAULT 'info',
  message TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON public.job_logs TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.job_logs_id_seq TO authenticated;
GRANT ALL ON public.job_logs TO service_role;
GRANT ALL ON SEQUENCE public.job_logs_id_seq TO service_role;
ALTER TABLE public.job_logs ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_job_logs_job_ts ON public.job_logs(job_id, ts);

CREATE POLICY "Authenticated view job logs"
  ON public.job_logs FOR SELECT TO authenticated USING (true);

-- =========================================================
-- tasks (extracted task records)
-- =========================================================
CREATE TABLE public.tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
  source_upload_id UUID REFERENCES public.uploads(id) ON DELETE SET NULL,
  code TEXT NOT NULL,
  title TEXT,
  chapter TEXT,
  effectivity TEXT,
  page_no INT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_tsv tsvector,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.tasks TO authenticated;
GRANT ALL ON public.tasks TO service_role;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_tasks_project   ON public.tasks(project_id);
CREATE INDEX idx_tasks_code_trgm ON public.tasks USING GIN(code gin_trgm_ops);
CREATE INDEX idx_tasks_search    ON public.tasks USING GIN(search_tsv);

CREATE OR REPLACE FUNCTION public.tasks_update_tsv()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
  NEW.search_tsv :=
    setweight(to_tsvector('simple', coalesce(NEW.code,'')), 'A') ||
    setweight(to_tsvector('simple', coalesce(NEW.title,'')), 'B') ||
    setweight(to_tsvector('simple', coalesce(NEW.chapter,'')), 'C') ||
    setweight(to_tsvector('simple', coalesce(NEW.effectivity,'')), 'C');
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_tasks_tsv
  BEFORE INSERT OR UPDATE OF code, title, chapter, effectivity ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.tasks_update_tsv();

CREATE POLICY "Authenticated view tasks"
  ON public.tasks FOR SELECT TO authenticated USING (true);

CREATE POLICY "Engineers manage tasks"
  ON public.tasks FOR ALL TO authenticated
  USING (public.has_any_role(auth.uid(), ARRAY['engineer','admin','super_admin']::public.app_role[]))
  WITH CHECK (public.has_any_role(auth.uid(), ARRAY['engineer','admin','super_admin']::public.app_role[]));

-- =========================================================
-- audit_log
-- =========================================================
CREATE TABLE public.audit_log (
  id BIGSERIAL PRIMARY KEY,
  actor_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  entity TEXT,
  entity_id TEXT,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON public.audit_log TO authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.audit_log_id_seq TO authenticated;
GRANT ALL ON public.audit_log TO service_role;
GRANT ALL ON SEQUENCE public.audit_log_id_seq TO service_role;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_audit_actor ON public.audit_log(actor_id);
CREATE INDEX idx_audit_ts    ON public.audit_log(ts DESC);

CREATE POLICY "Admins view audit log"
  ON public.audit_log FOR SELECT TO authenticated
  USING (public.is_admin(auth.uid()));

CREATE POLICY "Authenticated insert audit log"
  ON public.audit_log FOR INSERT TO authenticated
  WITH CHECK (actor_id = auth.uid());
