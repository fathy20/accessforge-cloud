import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "ar" | "en";

type Dict = Record<string, { ar: string; en: string }>;

export const dict = {
  // nav
  "nav.dashboard": { ar: "الرئيسية", en: "Dashboard" },
  "nav.uploads": { ar: "الملفات", en: "Uploads" },
  "nav.search": { ar: "البحث", en: "Search" },
  "nav.projects": { ar: "المشاريع", en: "Projects" },
  "nav.jobs": { ar: "المهام", en: "Jobs" },
  "nav.modules": { ar: "الموديولات", en: "Modules" },
  "nav.admin": { ar: "الإدارة", en: "Admin" },
  "nav.users": { ar: "المستخدمون", en: "Users" },
  "nav.audit": { ar: "سجل التدقيق", en: "Audit Log" },
  "nav.settings": { ar: "الإعدادات", en: "Settings" },
  "nav.profile": { ar: "الملف الشخصي", en: "Profile" },
  // topbar
  "top.search_placeholder": { ar: "ابحث في الملفات والمهام…", en: "Search files, tasks, jobs…" },
  "top.signout": { ar: "تسجيل الخروج", en: "Sign out" },
  "top.signed_in": { ar: "مسجل الدخول", en: "Signed in" },
  "top.language": { ar: "اللغة", en: "Language" },
  // modules
  "mod.task_extractor": { ar: "استخراج المهام", en: "Task Extractor" },
  "mod.task_stamping": { ar: "ختم الملفات", en: "Task Stamping" },
  "mod.effectivity": { ar: "Effectivity", en: "Effectivity" },
  "mod.check_control": { ar: "Check Control", en: "Check Control" },
  "mod.utilization": { ar: "Utilization", en: "Utilization" },
  "mod.cmp_tcm": { ar: "CMP / TCM", en: "CMP / TCM" },
  "mod.cover_merge": { ar: "Cover Merge", en: "Cover Merge" },
  "mod.mail_merge": { ar: "Mail Merge", en: "Mail Merge" },
  "mod.crew_hours": { ar: "ساعات الطاقم (LEON)", en: "Crew Hours (LEON)" },
  "mod.tcm_indexing": { ar: "فهرسة TCM", en: "TCM Indexing" },
  "mod.admin_users": { ar: "المستخدمون والأدوار", en: "Users & Roles" },
  "mod.admin_audit": { ar: "سجل التدقيق", en: "Audit Log" },
  "mod.admin_settings": { ar: "الإعدادات", en: "Settings" },
  "mod.readiness.available": { ar: "متاح", en: "Available" },
  "mod.readiness.pilot": { ar: "تجريبي", en: "Pilot" },
  "mod.readiness.under_validation": { ar: "قيد التحقق", en: "Under validation" },
  "mod.readiness.requires_configuration": { ar: "يتطلب إعدادًا", en: "Requires configuration" },
  "mod.readiness.under_development": { ar: "قيد التطوير", en: "Under development" },
  "mod.readiness.not_migrated": { ar: "لم تتم مهاجرته", en: "Not migrated" },
  "mod.readiness.discovery_required": { ar: "يتطلب استكشافًا", en: "Discovery required" },
  "mod.area.crew": { ar: "الطاقم", en: "Crew" },
  "mod.area.maintenance": { ar: "الصيانة", en: "Maintenance" },
  "mod.area.stores": { ar: "المخازن", en: "Stores" },
  "mod.area.admin": { ar: "الإدارة", en: "Admin" },
  "mod.index.description": {
    ar: "اختَر موديولًا لفتحه. حالات الجاهزية تعكس حالة الترحيل الحالية.",
    en: "Choose a module to open. Readiness statuses reflect the current migration state.",
  },
  "mod.maintenance.title": { ar: "موديولات الصيانة", en: "Maintenance modules" },
  "mod.maintenance.status_note": {
    ar: "الحالات المعروضة تعكس حالة الترحيل الحالية.",
    en: "Statuses reflect the current migration state.",
  },
  "mod.loading": { ar: "جاري تحميل الموديولات...", en: "Loading modules..." },
  "mod.empty": { ar: "لا توجد موديولات متاحة.", en: "No modules available." },
  "mod.access.view": { ar: "عرض", en: "View" },
  "mod.access.run": { ar: "تشغيل", en: "Run" },
  // crew hours
  "crew.tabs.cockpit_summary": { ar: "ملخص قمرة القيادة (Cockpit Summary)", en: "Cockpit Summary" },
  "crew.tabs.cockpit": { ar: "قمرة القيادة (Cockpit)", en: "Cockpit" },
  "crew.tabs.cabin_summary": { ar: "ملخص الضيافة (Cabin Summary)", en: "Cabin Summary" },
  "crew.tabs.cabin": { ar: "الضيافة (Cabin)", en: "Cabin" },
  "crew.official_mcp": { ar: "LEON MCP الرسمي", en: "Official LEON MCP" },
  "crew.positioning.cue": { ar: "تموضع · غير نشطة", en: "Positioning · Not Active" },
  "crew.positioning.description": {
    ar: "تموضع · غير نشطة · مشمولة في الإجمالي الرسمي.",
    en: "Positioning · Not Active · Included in official total.",
  },
  "crew.outside_tab_crew_message": {
    ar: "{arabicParts} من أفراد الطاقم خارج هذا التبويب غير معروضين.",
    en: "{englishParts} crew members are not shown in this tab.",
  },
  "crew.flight_count_filtered": { ar: "{visible} من {total} رحلة", en: "{visible} of {total} flights" },
  "crew.flight_count": { ar: "{count} رحلة", en: "{count} flights" },
  "crew.trn.aria_training": {
    ar: "علامة TRN يدوية ومحلية: تدريب",
    en: "Manual local TRN marker: Training",
  },
  "crew.trn.aria_normal": {
    ar: "علامة TRN يدوية ومحلية: عادي",
    en: "Manual local TRN marker: Normal",
  },
  "crew.trn.button_training": {
    ar: "يدوي · تدريب (TRN)",
    en: "Manual · Training (TRN)",
  },
  "crew.trn.button_normal": { ar: "يدوي · عادي", en: "Manual · Normal" },
  "crew.trn.tooltip": {
    ar: "هذه علامة TRN يدوية ومحلية، وليست من LEON ولا تؤثر على الإجمالي الرسمي.",
    en: "This is a manual local TRN marker; it is not from LEON and does not affect the official total.",
  },
  "crew.official_total": { ar: "الإجمالي الرسمي", en: "Official total" },
  "crew.unavailable": { ar: "غير متاح", en: "Unavailable" },
  "crew.expand.collapse": { ar: "طي تفاصيل الطاقم", en: "Collapse crew details" },
  "crew.expand.expand": { ar: "توسيع تفاصيل الطاقم", en: "Expand crew details" },
  "crew.filter.no_match": {
    ar: "لا توجد صفوف رحلات مطابقة لمرشحات العرض الحالية.",
    en: "No flight rows match the current display filters.",
  },
  "crew.filter.reset_hint": {
    ar: "أعد ضبط مرشحات الطائرة ورمز الموقع لعرض جميع الصفوف.",
    en: "Reset the aircraft and position-token filters to show all rows.",
  },
  "crew.table.detail_label": {
    ar: "جدول تفاصيل الرحلات حسب الطاقم",
    en: "Grouped crew flight detail table",
  },
  "crew.table.summary_label": { ar: "جدول ملخص الطاقم", en: "Crew summary table" },
  "crew.table.position_type": { ar: "نوع الموقع (Position type)", en: "Position type" },
  "crew.table.name": { ar: "الاسم (Name)", en: "Name" },
  "crew.table.date": { ar: "التاريخ (Date)", en: "Date" },
  "crew.table.aircraft": { ar: "الطائرة (Aircraft)", en: "Aircraft" },
  "crew.table.flight_number": { ar: "رقم الرحلة (Flight #)", en: "Flight #" },
  "crew.table.block_time": { ar: "زمن البلوك (Block time)", en: "Block time" },
  "crew.table.crew_code": { ar: "كود الطاقم (Crew code)", en: "Crew code" },
  "crew.table.flights": { ar: "الرحلات (Flights)", en: "Flights" },
  "crew.table.official_total": { ar: "الإجمالي الرسمي (Official total)", en: "Official total" },
  "crew.table.source": { ar: "المصدر (Source)", en: "Source" },
  "crew.total": { ar: "الإجمالي", en: "Total" },
  "crew.empty.tab": { ar: "لا يوجد أفراد طاقم في هذا التبويب.", en: "No crew members are in this tab." },
  "crew.server_total.cockpit": {
    ar: "إجمالي مجموعة قمرة القيادة المحسوب من الخادم:",
    en: "Server-computed Cockpit group total:",
  },
  "crew.server_total.cabin": {
    ar: "إجمالي مجموعة الضيافة المحسوب من الخادم:",
    en: "Server-computed Cabin group total:",
  },
  "crew.load.failed": {
    ar: "فشل تحميل تقرير ساعات الطاقم",
    en: "Failed to load crew hours report",
  },
  "crew.export.no_filename": {
    ar: "لم يرسل الخادم اسم الملف",
    en: "The server did not provide a filename",
  },
  "crew.export.success": { ar: "تم تصدير تقرير Excel", en: "Excel report exported" },
  "crew.export.failed": {
    ar: "فشل تصدير تقرير ساعات الطاقم",
    en: "Failed to export crew hours report",
  },
  "crew.title": { ar: "ساعات الطاقم", en: "Crew Hours" },
  "crew.subtitle": { ar: "قطاع الإحصائيات · المرحلة الأولى", en: "Statistics Sector · Phase 1" },
  "crew.last_loaded": { ar: "آخر تحميل", en: "Last loaded" },
  "crew.filters.title": { ar: "تصفية التقرير", en: "Report Filters" },
  "crew.filters.from": { ar: "من", en: "From" },
  "crew.filters.to": { ar: "إلى", en: "To" },
  "crew.filters.position": { ar: "الموقع (Position)", en: "Position" },
  "crew.filters.all_positions": { ar: "الكل (All)", en: "All Positions" },
  "crew.filters.crew_search": { ar: "اسم / كود الطاقم", en: "Crew Search" },
  "crew.filters.crew_search_placeholder": {
    ar: "ابحث باسم الطيار أو الكود...",
    en: "Search name or code...",
  },
  "crew.filters.aircraft": { ar: "الطائرة", en: "Aircraft" },
  "crew.filters.all_aircraft": { ar: "كل الطائرات (All aircraft)", en: "All aircraft" },
  "crew.filters.position_token": { ar: "رمز الموقع", en: "Position token" },
  "crew.filters.all_tokens": { ar: "الكل (All)", en: "All" },
  "crew.filters.active": { ar: "نشط (Active)", en: "Active" },
  "crew.filters.load": { ar: "تحميل التقرير", en: "Load Report" },
  "crew.filters.note": {
    ar: "تغيّر المرشحات تفاصيل الرحلات الظاهرة فقط. تظل الإجماليات الرسمية شاملة لأرجل PAD / غير النشطة.",
    en: "Filters change visible flight details only. Official totals still include PAD / Not-Active legs.",
  },
  "crew.kpi.heading": { ar: "مؤشرات ساعات الطاقم", en: "Crew hours KPIs" },
  "crew.kpi.cockpit_hours": {
    ar: "الساعات الرسمية لقمرة القيادة",
    en: "Cockpit official hours",
  },
  "crew.kpi.cockpit_description": {
    ar: "الساعات الرسمية المقدمة من LEON لطاقم قمرة القيادة",
    en: "Server-provided official LEON hours for cockpit crew",
  },
  "crew.kpi.maintenance_hours": {
    ar: "الساعات الرسمية للصيانة:",
    en: "Maintenance official hours:",
  },
  "crew.kpi.cabin_hours": { ar: "الساعات الرسمية للضيافة", en: "Cabin official hours" },
  "crew.kpi.cabin_description": {
    ar: "الساعات الرسمية المقدمة من LEON لطاقم الضيافة",
    en: "Server-provided official LEON hours for cabin crew",
  },
  "crew.kpi.matched_legs": { ar: "الأرجل المطابقة", en: "Matched legs" },
  "crew.kpi.matched_legs_description": {
    ar: "عدد الرحلات المطابقة لسجلات التقرير، وليس عدد صفوف LEON",
    en: "Flights matched to report records; not the LEON row count",
  },
  "crew.kpi.leon_records": { ar: "سجلات LEON", en: "LEON records" },
  "crew.kpi.leon_records_description": {
    ar: "عدد الصفوف التي أعادها LEON، وليس عدد الأرجل المطابقة",
    en: "Rows returned by LEON; not the matched-leg count",
  },
  "crew.kpi.unclassified_roles": { ar: "الأدوار غير المصنفة", en: "Unclassified roles" },
  "crew.kpi.unclassified_roles_description": {
    ar: "عدد أفراد الطاقم الذين قيمة position_type لديهم null",
    en: "Crew rows where position_type is null",
  },
  "crew.kpi.totals_available": {
    ar: "الإجماليات الرسمية المتاحة: {count}",
    en: "Official totals available: {count}",
  },
  "crew.kpi.totals_unavailable": {
    ar: "الإجماليات الرسمية غير المتاحة: {count}",
    en: "Official totals unavailable: {count}",
  },
  "crew.loading.aria": {
    ar: "جاري تحميل تقرير ساعات الطاقم",
    en: "Loading crew hours report",
  },
  "crew.error.title": { ar: "خطأ في تحميل التقرير", en: "Error Loading Report" },
  "crew.error.retry": { ar: "إعادة المحاولة", en: "Retry" },
  "crew.error.validation.title": { ar: "فشل التحقق من التقرير", en: "Report validation failed" },
  "crew.error.validation.description": {
    ar: "راجع الفترة والمرشحات المحددة ثم أعد المحاولة.",
    en: "Check the selected period and filters, then retry.",
  },
  "crew.error.rate_limited.title": { ar: "تم تجاوز حد الطلبات", en: "Report rate limited" },
  "crew.error.rate_limited.description": {
    ar: "الخدمة حدّت الطلبات مؤقتًا. حاول مرة أخرى بعد قليل.",
    en: "The report service is rate-limited temporarily. Try again shortly.",
  },
  "crew.error.unavailable.title": { ar: "مصدر التقرير غير متاح", en: "Report source unavailable" },
  "crew.error.unavailable.description": {
    ar: "مصدر تقرير LEON غير مُعد أو غير متاح حاليًا.",
    en: "The LEON report source is not configured or is currently unavailable.",
  },
  "crew.error.timeout.title": { ar: "انتهت مهلة التقرير", en: "Report request timed out" },
  "crew.error.timeout.description": {
    ar: "استغرق الطلب وقتًا طويلًا. أعد المحاولة.",
    en: "The request took too long. Retry the report.",
  },
  "crew.partial.title": {
    ar: "الإجمالي الرسمي غير متاح لبعض أفراد الطاقم",
    en: "Official totals are unavailable for some crew members",
  },
  "crew.partial.description": {
    ar: "توجد رحلات في التقرير، لكن بعض الإجماليات الرسمية غير متاحة. اعرض القيم غير المتاحة كما هي ولا تعتبرها صفرًا.",
    en: "Flights are present, but some official totals are unavailable. Treat unavailable values as unavailable, not zero.",
  },
  "crew.empty.title": { ar: "لا توجد سجلات", en: "No Crew Records Found" },
  "crew.empty.description": {
    ar: "لم يتم العثور على رحلات أو طاقم بالفلاتر المحددة. جرب تغيير النطاق الزمني.",
    en: "No flight or crew data matched your criteria for this interval.",
  },
  "crew.details.title": {
    ar: "تفاصيل الطاقم والرحلات",
    en: "Crew Members & Flight Breakdown",
  },
  "crew.export.aria_exporting": {
    ar: "جاري تصدير تقرير Excel",
    en: "Exporting Excel report",
  },
  "crew.export.aria_export": {
    ar: "تصدير تقرير ساعات الطاقم إلى Excel",
    en: "Export crew hours report to Excel",
  },
  "crew.export.button_exporting": { ar: "جاري التصدير...", en: "Exporting..." },
  "crew.export.button_export": { ar: "تصدير Excel", en: "Export Excel" },
  "crew.tabs.aria": { ar: "تبويبات تقرير ساعات الطاقم", en: "Crew hours report tabs" },
} satisfies Dict;

export type DictKey = keyof typeof dict;
export type I18nParams = Record<string, string | number>;
export type Translate = (key: DictKey, params?: I18nParams) => string;

type Ctx = {
  lang: Lang;
  dir: "rtl" | "ltr";
  setLang: (l: Lang) => void;
  t: Translate;
};

const I18nContext = createContext<Ctx | null>(null);

const STORAGE_KEY = "redsea.lang";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ar");

  useEffect(() => {
    const stored = (typeof window !== "undefined" && localStorage.getItem(STORAGE_KEY)) as Lang | null;
    if (stored === "ar" || stored === "en") setLangState(stored);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const html = document.documentElement;
    html.lang = lang;
    html.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);

  const setLang = (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(STORAGE_KEY, l); } catch { /* noop */ }
  };

  const t: Translate = (key, params) => {
    const value = dict[key]?.[lang] ?? key;
    if (!params) return value;

    return value.replace(/\{(\w+)\}/g, (placeholder, name) => {
      if (!Object.prototype.hasOwnProperty.call(params, name)) return placeholder;
      return String(params[name]);
    });
  };

  return (
    <I18nContext.Provider value={{ lang, dir: lang === "ar" ? "rtl" : "ltr", setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
