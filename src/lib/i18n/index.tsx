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
} satisfies Dict;

export type DictKey = keyof typeof dict;

type Ctx = {
  lang: Lang;
  dir: "rtl" | "ltr";
  setLang: (l: Lang) => void;
  t: (key: DictKey) => string;
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

  const t = (key: DictKey) => dict[key]?.[lang] ?? key;

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
