
-- Storage RLS for 'uploads' and 'outputs' buckets
-- Path convention: <user_id>/<project_id_or_unassigned>/<sha256>-<filename>

-- UPLOADS bucket
CREATE POLICY "uploads_select_own_or_admin"
ON storage.objects FOR SELECT TO authenticated
USING (
  bucket_id = 'uploads'
  AND (owner = auth.uid() OR public.is_admin(auth.uid()))
);

CREATE POLICY "uploads_insert_own"
ON storage.objects FOR INSERT TO authenticated
WITH CHECK (
  bucket_id = 'uploads'
  AND owner = auth.uid()
  AND (storage.foldername(name))[1] = auth.uid()::text
);

CREATE POLICY "uploads_delete_own_or_admin"
ON storage.objects FOR DELETE TO authenticated
USING (
  bucket_id = 'uploads'
  AND (owner = auth.uid() OR public.is_admin(auth.uid()))
);

-- OUTPUTS bucket (worker writes via service-role; users read their own/admin all)
CREATE POLICY "outputs_select_own_or_admin"
ON storage.objects FOR SELECT TO authenticated
USING (
  bucket_id = 'outputs'
  AND (owner = auth.uid() OR public.is_admin(auth.uid()))
);

CREATE POLICY "outputs_delete_admin"
ON storage.objects FOR DELETE TO authenticated
USING (
  bucket_id = 'outputs' AND public.is_admin(auth.uid())
);

-- Improve uploads search: add trigger if not present
DROP TRIGGER IF EXISTS uploads_tsv_trigger ON public.uploads;
CREATE TRIGGER uploads_tsv_trigger
BEFORE INSERT OR UPDATE ON public.uploads
FOR EACH ROW EXECUTE FUNCTION public.uploads_update_tsv();

-- Unified search function across uploads + tasks
CREATE OR REPLACE FUNCTION public.global_search(_q text, _limit int DEFAULT 50)
RETURNS TABLE (
  source text,
  id uuid,
  title text,
  subtitle text,
  project_id uuid,
  created_at timestamptz,
  rank real
)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public
AS $$
  SELECT 'upload'::text, u.id, u.original_name,
         coalesce(u.metadata->>'title', u.kind::text),
         u.project_id, u.created_at,
         ts_rank(u.search_tsv, plainto_tsquery('simple', _q)) AS rank
  FROM public.uploads u
  WHERE _q <> '' AND (
    u.search_tsv @@ plainto_tsquery('simple', _q)
    OR u.original_name ILIKE '%'||_q||'%'
  )
  UNION ALL
  SELECT 'task'::text, t.id, coalesce(t.code, t.title), t.title,
         t.project_id, t.created_at,
         ts_rank(t.search_tsv, plainto_tsquery('simple', _q)) AS rank
  FROM public.tasks t
  WHERE _q <> '' AND (
    t.search_tsv @@ plainto_tsquery('simple', _q)
    OR t.code ILIKE '%'||_q||'%'
    OR t.title ILIKE '%'||_q||'%'
  )
  ORDER BY rank DESC NULLS LAST, created_at DESC
  LIMIT _limit;
$$;

GRANT EXECUTE ON FUNCTION public.global_search(text, int) TO authenticated;
