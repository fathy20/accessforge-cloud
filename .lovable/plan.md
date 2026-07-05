
# خطة تطوير REDSEA لنظام احترافي متكامل

## نظرة عامة

النظام الحالي عنده أساس شغّال (Auth + 8 modules + Jobs + Uploads + Python worker). الخطة دي بتحوّله لـ **موقع احترافي كامل** بواجهة عامة، قاعدة بيانات موسّعة، وإدارة مركزية للمستخدمين والصلاحيات.

## 1) واجهة عامة (Landing Page)

- صفحة `/` عامة احترافية: Hero + Features + Modules showcase + Testimonials + CTA.
- Header: شعار REDSEA + Sign In.
- Footer: روابط الشركة، Privacy، Terms.
- SEO كامل (title, description, OG tags).

## 2) قاعدة بيانات موسّعة وقوية

### جداول جديدة
- **`user_invitations`** — دعوات بالإيميل (token, expires_at, role, invited_by, accepted_at, module presets).
- **`notifications`** — إشعارات داخل النظام (job done/failed, invitation, role change).
- **`user_activity`** — آخر تسجيل دخول، عدد الـ jobs، آخر نشاط.
- **`module_usage_stats`** — إحصائيات استخدام كل موديول.
- **`email_log`** — سجل كل الإيميلات المرسلة (نوع، مستقبل، حالة).

### تحسينات على الجداول الحالية
- `profiles`: إضافة `phone`, `department`, `job_title`, `employee_id`, `status` (active/suspended/pending), `last_seen_at`, `preferences` jsonb.
- `module_access`: إضافة `expires_at` للصلاحيات المؤقتة.
- Triggers لتحديث `user_activity` تلقائيًا وتسجيل الأحداث في `audit_log`.
- Indexes إضافية للأداء.

### الأمان
- RLS على كل جدول.
- Security definer functions لكل role/permission checks.
- GRANTs صحيحة (authenticated + service_role).

## 3) نظام Authentication احترافي

- **Email + Password** مع HIBP check (منع الباسوردات المسرّبة).
- **Email verification** إجباري.
- **Password reset** كامل عبر إيميل.
- **First user auto = super_admin**، بعده كل حساب جديد status = `pending` لحد ما الأدمن يفعّله.
- **Email templates** مخصصة بشعار REDSEA:
  - Welcome / Verify email
  - Password reset
  - Invitation to REDSEA
  - Job completed / failed notification
- Sign-out كامل يمسح الـ cache و listener واحد بس في الـ root.

## 4) لوحة تحكم المدير (Admin Console)

### `/admin/users` — تطوير كامل
- Table بكل المستخدمين + بحث/فلترة/ترتيب.
- لكل مستخدم:
  - تفعيل / تعليق / حذف الحساب.
  - تغيير الدور (guest / engineer / admin / super_admin).
  - إدارة صلاحيات كل موديول (view / run).
  - إعادة تعيين كلمة المرور (يبعت إيميل).
  - عرض النشاط الأخير + الـ jobs.
- زر **"Invite User"** — دعوة بالإيميل مع دور وصلاحيات مسبقة.
- Bulk actions.

### `/admin/invitations` — جديد
- عرض كل الدعوات (pending/accepted/expired) + إعادة إرسال / إلغاء.

### `/admin/settings` — تطوير
- تفعيل/تعطيل تسجيل الحسابات الجديدة.
- تفعيل/تعطيل موديولز على مستوى النظام.
- إعدادات الإشعارات الافتراضية.

### `/admin/audit` — تطوير
- Timeline بكل الأحداث الحساسة + فلترة + Export CSV.

## 5) صفحة الملف الشخصي (`/profile`)

- تعديل البيانات (اسم، تليفون، قسم، وظيفة، صورة).
- تغيير كلمة المرور.
- عرض صلاحيات الموديولز.
- سجل الـ jobs الشخصية.
- إعدادات الإشعارات.

## 6) نظام الإشعارات

- **In-app**: Bell في الـ topbar + Badge للعدد + قائمة منسدلة.
- **Email**: عند اكتمال/فشل job، دعوة، تغيير دور.
- كل مستخدم يختار يستقبل إيه.

## 7) Dashboard مطوّر

- كروت أرقام حية (My Jobs, Active Users, Storage, Modules).
- شارتات آخر 7 أيام (Jobs by day / status / module).
- Quick actions حسب الدور.
- Recent activity feed.

## 8) القسم الفني (Technical)

- **Backend**: كل الـ server logic في TanStack `createServerFn` (مش Edge Functions).
- **Frontend**: كل الصفحات تحت `_authenticated/` ماعدا `/`, `/auth`, `/reset-password`, `/invite/:token`.
- **TanStack Query** + Supabase Realtime للـ jobs والإشعارات.
- **Email**: Lovable managed templates (auth) + transactional email للإشعارات.
- **Security**: RLS + HIBP + Rate limiting + Audit trail.
- **Toast** موحّد (sonner).

## 9) مراحل التنفيذ

- **Phase A**: Landing page + تحسين Auth + Password reset.
- **Phase B**: قاعدة البيانات (جداول + triggers + RLS + GRANTs).
- **Phase C**: لوحة تحكم المستخدمين الكاملة + Invitations.
- **Phase D**: Email system (templates + notifications).
- **Phase E**: Dashboard بالإحصائيات + Profile page.
- **Phase F**: UI/UX نهائي + اختبار شامل.

---

## قبل ما نبدأ — محتاج قرارك في 3 نقاط

**1) الصفحة الرئيسية العامة (`/`):**
- **(أ)** Landing عام لأي حد يشوفه + زر Sign In.
- **(ب)** صفحة دخول مباشرة (النظام مغلق تمامًا).

**2) طريقة إنشاء الحسابات:**
- **(أ)** المستخدم يعمل حساب بنفسه ويكون Pending لحد ما الأدمن يفعّله.
- **(ب)** الأدمن هو الوحيد اللي يبعت دعوات بالإيميل (Invite-only).

**3) Google Sign-in:**
- **(أ)** أضيفه مع Email/Password.
- **(ب)** Email/Password فقط.

قوللي اختياراتك (مثلًا: `1-أ, 2-ب, 3-ب`) وأبدأ فورًا بـ **Phase A**.
