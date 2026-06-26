
# REDSEA Aviation Toolkit — Web Platform Architecture Plan

تحويل أداة REDSEA (Python/Tkinter) لمنصة ويب احترافية متعددة المستخدمين بصلاحيات، رفع ملفات، بحث قوي، ومعالجة PDF/Excel في الخلفية. المعمارية مبنية لتقدر تستحمل نمو وموديولات جديدة من غير ما نعيد البناء.

---

## 1) High-Level Architecture

```text
┌────────────────────────────────────────────────────────────┐
│                  Frontend (TanStack Start)                 │
│  Dashboard · Auth · RBAC UI · Uploads · Search · Modules   │
└───────────────┬────────────────────────────┬───────────────┘
                │ Server Functions (RPC)     │ Realtime (jobs)
                ▼                            ▼
┌────────────────────────────┐   ┌────────────────────────────┐
│   Lovable Cloud (Supabase) │   │  Python Worker Service     │
│  · Auth (email + Google)   │   │  (FastAPI + RQ/Celery)     │
│  · Postgres + RLS          │◄──┤  · PDF extract / OCR       │
│  · Storage (PDF/Excel/DOCX)│   │  · Stamping / TCM index    │
│  · pg_cron · pg_trgm/FTS   │   │  · Mail merge / Covering   │
│  · Edge: signed URLs       │   │  Hosted: Railway/Fly/Render│
└────────────────────────────┘   └────────────────────────────┘
```

المعالجة الثقيلة (PyMuPDF, Tesseract, python-docx, openpyxl) **مستحيل** تشتغل على Cloudflare Worker. لازم **Python worker منفصل** يستقبل jobs ويرجع نتائج. الـ Web app تتحكم وتعرض فقط.

---

## 2) Core Modules (من الكود الأصلي)

| الموديول | الوظيفة | Worker job |
|---|---|---|
| Task Extractor | استخراج Tasks من PDFs (RegEx + OCR) | `extract_tasks` |
| Task Stamping | ختم Tail/Station/Date على PDFs | `stamp_pdfs` |
| Effectivity | تحميل Excel + ربط chapters | `effectivity_export` |
| Check Control | CSV checks management | DB only |
| Utilization | tracking + hashing (MD5/SHA/Blake2) | DB only |
| CMP/TCM Tasks | indexing TCM folder + بناء task cards | `build_tcm_index`, `generate_cards` |
| Cover Merge | merge cover PDFs | `cover_merge` |
| Mail Merge (Covering) | Word + Excel → RC Cards | `mail_merge` |
| **Module N** (future) | plug-in جديد | حسب الحاجة |

---

## 3) Roles & Permissions (RBAC)

Enum `app_role`: `super_admin`, `admin`, `engineer`, `viewer`, `guest`.

| Capability | super_admin | admin | engineer | viewer | guest |
|---|:-:|:-:|:-:|:-:|:-:|
| إدارة users + roles | ✅ | ✅ | – | – | – |
| رفع ملفات | ✅ | ✅ | ✅ | – | – |
| تشغيل modules (jobs) | ✅ | ✅ | ✅ | – | – |
| تنزيل النتائج | ✅ | ✅ | ✅ | ✅ | – |
| عرض dashboard | ✅ | ✅ | ✅ | ✅ | ✅ (محدود) |
| Audit log | ✅ | ✅ | – | – | – |
| Module-level access (per module assignment) | كل الموديولات | كل الموديولات | حسب التعيين | حسب التعيين | – |

الصلاحيات تتحقق على 3 مستويات: **UI hide**, **server function check**, **Postgres RLS policy** (defense in depth).

---

## 4) Database Schema (Postgres)

```text
profiles(id PK→auth.users, full_name, avatar, department, created_at)
app_role enum
user_roles(user_id, role, UNIQUE)
modules(id, key, name, description, enabled)
module_access(user_id, module_id, can_run, can_view)
projects(id, name, owner_id, tail_number, station, created_at)
uploads(id, project_id, uploader_id, storage_path, kind[pdf|excel|docx|csv],
        original_name, size, sha256, search_tsv tsvector, created_at)
jobs(id, project_id, module_key, status[queued|running|done|failed],
     input_refs jsonb, output_refs jsonb, progress int,
     error text, created_by, started_at, finished_at)
job_logs(id, job_id, level, message, ts)
tasks(id, project_id, code, title, chapter, effectivity, source_upload_id,
      page_no, search_tsv tsvector)        -- نتائج Task Extractor
tcm_index(id, project_id, task_code, pdf_path, page_no, related jsonb)
checks(id, project_id, code, description, …)
utilization(id, project_id, …)
audit_log(id, actor, action, entity, entity_id, meta jsonb, ts)
```

Security definer: `has_role(uuid, app_role)`, `has_module_access(uuid, text)`.
Indexes: `GIN(search_tsv)`, `GIN(tasks.code gin_trgm_ops)`, btree على FKs.

---

## 5) Powerful Search

- عمود `search_tsv` على `uploads`, `tasks`, `tcm_index` بيتولد عبر trigger (title+code+chapter+ocr_text).
- استعلام موحد عبر server function: full-text + fuzzy (`pg_trgm`) + filters (module, project, tail, date, uploader).
- UI: command palette (⌘K) + صفحة Search متقدمة بـ facets.

---

## 6) Processing Pipeline (Jobs)

```text
User uploads file → Storage → row in uploads
        │
        ▼
User triggers module → server fn validates RBAC → INSERT jobs(queued)
        │
        ▼
Python Worker pulls job (HTTPS webhook OR poll) →
   downloads inputs via signed URL → runs PyMuPDF/OCR/etc. →
   uploads outputs to Storage → PATCH job(done, output_refs)
        │
        ▼
Realtime channel pushes status → UI updates progress bar live
```

Worker = FastAPI + RQ (Redis) أو Celery. Deployable على Railway/Fly.io/Render. يخزن نتائج رجوع في Supabase Storage ويحدث `jobs` table بـ service-role key.

---

## 7) Frontend Structure (TanStack Start)

```text
src/routes/
  index.tsx                        ← landing/login redirect
  auth.tsx                         ← email + Google sign-in
  _authenticated/
    route.tsx                      ← managed gate
    dashboard.tsx                  ← KPIs, recent jobs, quick actions
    projects/index.tsx
    projects/$projectId.tsx
    uploads/index.tsx              ← drag-drop, list, search
    search.tsx                     ← global search
    modules/task-extractor.tsx
    modules/task-stamping.tsx
    modules/effectivity.tsx
    modules/check-control.tsx
    modules/utilization.tsx
    modules/cmp-tcm.tsx
    modules/cover-merge.tsx
    modules/mail-merge.tsx
    jobs/index.tsx                 ← queue monitor (live)
    jobs/$jobId.tsx                ← logs, output download
    _admin/
      route.tsx                    ← gate: admin/super_admin
      users.tsx                    ← invite, assign roles & modules
      audit.tsx
      settings.tsx
  api/public/worker-callback.ts    ← HMAC-verified worker → app
src/lib/
  *.functions.ts                   ← server fns (auth-guarded)
  modules/                         ← per-module UI components
  search/                          ← search hooks & components
src/components/ui/                 ← shadcn
```

UI: dashboard sidebar + topbar + content. Dark/light. Arabic RTL support اختياري.

---

## 8) Auth

- Email/password + **Google OAuth** (عبر Lovable broker — مطلوب من standards).
- صفحة `/auth` عامة. كل الموديولات تحت `_authenticated/`.
- Invites: admin يبعت invite → user يعمل sign-up → auto-assign role + modules.
- Password reset عبر `/reset-password`.
- HIBP leaked-password check مفعّل.

---

## 9) Security

- RLS على كل الجداول؛ policies تستخدم `has_role` و `has_module_access`.
- Service-role key للـ worker فقط (server-side، مش متاح للـ browser).
- Signed URLs لتنزيل ملفات Storage (expiry قصير).
- Audit log لكل action حساس (role change, file delete, job run).
- Worker callbacks محمية بـ HMAC signature.
- Input validation بـ Zod على كل server fn.
- Rate limiting على endpoints الحساسة.

---

## 10) Phased Roadmap

**Phase 1 — Foundation (Web only, no worker):**
1. Enable Lovable Cloud, design system, sidebar shell, theme.
2. Auth + `/auth` + `_authenticated` layout + Google sign-in.
3. Schema: profiles, user_roles, modules, module_access, audit_log.
4. Admin panel: users list, role assign, module access matrix.

**Phase 2 — Uploads & Search:**
5. Storage buckets (`uploads`, `outputs`) + RLS.
6. Upload UI (drag-drop, progress, dedupe بـ sha256).
7. `uploads` table + tsvector trigger + global search page + ⌘K palette.

**Phase 3 — Jobs framework:**
8. `jobs` + `job_logs` tables + realtime subscription.
9. Job orchestration server fns (enqueue, cancel, retry).
10. Jobs monitor UI (live progress, logs viewer).

**Phase 4 — Python Worker:**
11. FastAPI service repo (separate). Endpoints: `/jobs/poll`, `/jobs/:id/complete`.
12. Port `extract_tasks`, `stamp_pdfs` first (أكثر استخداماً).
13. Deploy على Railway/Fly + Redis. Document deployment.

**Phase 5 — Modules (one by one):**
14. Task Extractor → 15. Task Stamping → 16. Effectivity → 17. Check Control →
18. Utilization → 19. CMP/TCM + TCM indexer → 20. Cover Merge → 21. Mail Merge.

**Phase 6 — Polish:**
22. Dashboard KPIs (jobs/day, success rate, storage usage).
23. Notifications (in-app + email on job completion).
24. Export reports (PDF/Excel).
25. Plugin slot for "Module N" future.

---

## 11) Technical Notes

- **لا يمكن** تشغيل PyMuPDF/Tesseract/python-docx داخل Cloudflare Worker — Python worker خارجي ضروري.
- Lovable app = control plane + UI + auth + data. Worker = compute plane.
- التواصل: worker يستهلك jobs من Postgres عبر service-role key (poll كل 2-5 ثواني) أو webhook من Edge function عند job جديد.
- Storage هرفع عليه ملفات المستخدم؛ النتائج بتترفع لنفس bucket تحت `outputs/`.
- المعمارية stateless للـ worker → نقدر نشغل أكتر من instance للسكيل.

---

## 12) أسئلة قبل البدء

1. **Worker hosting**: عندك تفضيل (Railway / Fly.io / Render / VPS)؟ أو أبدأ بـ Railway (الأسهل)؟
2. **Languages**: واجهة عربي/إنجليزي/الاتنين؟
3. **Multi-tenant؟** الناس كلهم في organization واحدة (REDSEA) ولا فيه شركات منفصلة؟
4. **أبدأ Phase 1 دلوقتي** (foundation + auth + RBAC + admin panel) ولا تحب تعدّل شيء في الـ scope الأول؟
