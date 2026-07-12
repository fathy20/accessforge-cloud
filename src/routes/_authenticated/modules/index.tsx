import { createFileRoute, Link } from "@tanstack/react-router";
import {
  FileSearch, Stamp, Table2, ListChecks, Gauge, FolderTree, Layers, Mail,
  ArrowRight, Lock, type LucideIcon,
} from "lucide-react";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/modules/")({
  head: () => ({ meta: [{ title: "Modules · REDSEA" }] }),
  component: ModulesIndex,
});

interface ModuleCard {
  to: string;
  moduleKey: string;
  icon: LucideIcon;
  title: string;
  titleAr: string;
  description: string;
  descriptionAr: string;
  accepts: string;
}

const MODULES: ModuleCard[] = [
  {
    to: "/modules/task-extractor", moduleKey: "task_extractor", icon: FileSearch,
    title: "Task Extractor", titleAr: "Task Extractor — استخراج المهام",
    description: "Extract maintenance task codes from PDF documents (RegEx + OCR).",
    descriptionAr: "استخراج رموز المهام من ملفات PDF (RegEx + OCR).",
    accepts: "PDF",
  },
  {
    to: "/modules/task-stamping", moduleKey: "task_stamping", icon: Stamp,
    title: "Task Stamping", titleAr: "Task Stamping — ختم المهام",
    description: "Stamp tail number, station and date onto PDF documents.",
    descriptionAr: "ختم رقم الطائرة والمحطة والتاريخ على ملفات PDF.",
    accepts: "PDF",
  },
  {
    to: "/modules/effectivity", moduleKey: "effectivity", icon: Table2,
    title: "EFFECTIVITY / TCM", titleAr: "EFFECTIVITY / TCM",
    description: "Load Excel data and link maintenance chapters per effectivity.",
    descriptionAr: "تحميل بيانات Excel وربط فصول الصيانة لكل effectivity.",
    accepts: "EXCEL · CSV",
  },
  {
    to: "/modules/check-control", moduleKey: "check_control", icon: ListChecks,
    title: "Check Control", titleAr: "Check Control — التحكم في الفحوصات",
    description: "Manage maintenance checks from CSV / Excel definitions.",
    descriptionAr: "إدارة الفحوصات من تعريفات CSV / Excel.",
    accepts: "CSV · EXCEL",
  },
  {
    to: "/modules/utilization", moduleKey: "utilization", icon: Gauge,
    title: "Utilization", titleAr: "Utilization — الاستخدام",
    description: "Track aircraft utilization with hashing & history.",
    descriptionAr: "تتبع استخدام الطائرة مع تجزئة السجلات.",
    accepts: "EXCEL · CSV",
  },
  {
    to: "/modules/cmp-tcm", moduleKey: "cmp_tcm", icon: FolderTree,
    title: "CMP / TCM Tasks", titleAr: "CMP / TCM Tasks",
    description: "Index TCM folder and generate indexed task cards.",
    descriptionAr: "فهرسة مجلد TCM من ملفات PDF وتوليد بطاقات مهام مفهرسة.",
    accepts: "PDF",
  },
  {
    to: "/modules/cover-merge", moduleKey: "cover_merge", icon: Layers,
    title: "Cover Merge", titleAr: "Cover Merge — دمج الأغلفة",
    description: "Merge cover PDFs onto task-card PDFs.",
    descriptionAr: "دمج ملفات الأغلفة على بطاقات المهام.",
    accepts: "PDF",
  },
  {
    to: "/modules/mail-merge", moduleKey: "mail_merge", icon: Mail,
    title: "Mail Merge (Covering)", titleAr: "Mail Merge (Covering) — دمج المراسلات",
    description: "Generate RC cards by merging a Word template with Excel data.",
    descriptionAr: "توليد بطاقات RC بدمج قالب Word مع بيانات Excel.",
    accepts: "DOCX · EXCEL",
  },
];

function ModulesIndex() {
  const perms = usePermissions();
  const { lang } = useI18n();
  const ar = lang === "ar";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          {ar ? "الموديولز" : "Modules"}
        </h1>
        <p className="text-sm text-muted-foreground">
          {ar
            ? "اختر موديول لتشغيله. كل موديول يعمل بنفس منطق REDSEA Toolkit الأصلي."
            : "Pick a module to work on. Each runs the original REDSEA Toolkit logic."}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {MODULES.map((m) => {
          const canView = perms.canViewModule(m.moduleKey);
          const canRun = perms.canRunModule(m.moduleKey);
          const Icon = m.icon;

          const CardInner = (
            <Card
              className={cn(
                "h-full transition-all group",
                canView
                  ? "hover:border-primary/50 hover:shadow-md cursor-pointer"
                  : "opacity-60 cursor-not-allowed",
              )}
            >
              <CardContent className="p-5 flex flex-col gap-3 h-full">
                <div className="flex items-start justify-between gap-2">
                  <div className="size-10 rounded-lg bg-primary/10 grid place-items-center text-primary group-hover:bg-primary group-hover:text-primary-foreground transition-colors">
                    <Icon className="size-5" />
                  </div>
                  <Badge variant="outline" className="text-[10px]">{m.accepts}</Badge>
                </div>
                <div className="flex-1">
                  <h3 className="font-semibold text-base leading-tight">
                    {ar ? m.titleAr : m.title}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                    {ar ? m.descriptionAr : m.description}
                  </p>
                </div>
                <div className="flex items-center justify-between pt-2 border-t border-border/50">
                  <div className="flex gap-1">
                    <Badge variant={canView ? "secondary" : "outline"} className="text-[10px]">
                      {canView ? "View ✓" : "View ✗"}
                    </Badge>
                    <Badge variant={canRun ? "default" : "outline"} className="text-[10px]">
                      {canRun ? "Run ✓" : "Run ✗"}
                    </Badge>
                  </div>
                  {canView ? (
                    <ArrowRight className="size-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all rtl:rotate-180" />
                  ) : (
                    <Lock className="size-4 text-muted-foreground" />
                  )}
                </div>
              </CardContent>
            </Card>
          );

          return canView ? (
            <Link key={m.to} to={m.to} className="block">{CardInner}</Link>
          ) : (
            <div key={m.to}>{CardInner}</div>
          );
        })}
      </div>
    </div>
  );
}
