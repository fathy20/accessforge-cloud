import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { toast } from "sonner";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { format, subDays } from "date-fns";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const Route = createFileRoute("/_authenticated/reports")({
  head: () => ({ meta: [{ title: "Reports · REDSEA" }] }),
  component: ReportsPage,
});

type ReportKey = "jobs" | "uploads" | "tasks" | "audit";

const REPORTS: { key: ReportKey; table: string; columns: string; label: { en: string; ar: string } }[] = [
  { key: "jobs",    table: "jobs",     columns: "id,module_key,status,progress,created_at,started_at,finished_at,error,project_id,created_by",
    label: { en: "Jobs", ar: "المهام" } },
  { key: "uploads", table: "uploads",  columns: "id,original_name,kind,size_bytes,sha256,project_id,uploader_id,created_at",
    label: { en: "Uploads", ar: "الملفات" } },
  { key: "tasks",   table: "tasks",    columns: "id,code,title,chapter,effectivity,page_no,project_id,source_upload_id,created_at",
    label: { en: "Extracted Tasks", ar: "المهام المستخرجة" } },
  { key: "audit",   table: "audit_log", columns: "id,action,entity,entity_id,actor_id,ts,meta",
    label: { en: "Audit Log", ar: "سجل التدقيق" } },
];

function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const headers = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    if (v === null || v === undefined) return "";
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers.join(","), ...rows.map((r) => headers.map((h) => esc(r[h])).join(","))].join("\n");
}

function download(name: string, csv: string) {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

function ReportsPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";

  const [from, setFrom] = useState(format(subDays(new Date(), 30), "yyyy-MM-dd"));
  const [to, setTo] = useState(format(new Date(), "yyyy-MM-dd"));
  const [busy, setBusy] = useState<ReportKey | null>(null);

  const run = async (r: (typeof REPORTS)[number]) => {
    setBusy(r.key);
    try {
      const data = await ApiClient.fetch(`/reports/${r.key}?from=${from}&to=${to}`);
      const rows = (data ?? []) as unknown as Record<string, unknown>[];
      if (!rows.length) { toast.info(ar ? "لا توجد بيانات" : "No data"); return; }
      download(`${r.key}-${from}-to-${to}.csv`, toCsv(rows));
      toast.success(ar ? `تم تصدير ${rows.length} صف` : `Exported ${rows.length} rows`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{ar ? "التقارير" : "Reports"}</h1>
        <p className="text-sm text-muted-foreground">
          {ar ? "تصدير بيانات النظام بصيغة CSV." : "Export system data as CSV files."}
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">{ar ? "نطاق التاريخ" : "Date range"}</CardTitle></CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4 max-w-xl">
          <div className="space-y-1.5">
            <Label>{ar ? "من" : "From"}</Label>
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>{ar ? "إلى" : "To"}</Label>
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      <div className="grid sm:grid-cols-2 gap-4">
        {REPORTS.map((r) => (
          <Card key={r.key}>
            <CardContent className="p-5 flex items-center gap-4">
              <div className="size-11 rounded-lg bg-primary/10 text-primary grid place-items-center">
                <FileSpreadsheet className="size-5" />
              </div>
              <div className="flex-1">
                <p className="font-medium">{r.label[ar ? "ar" : "en"]}</p>
                <p className="text-xs text-muted-foreground font-mono">{r.table}.csv</p>
              </div>
              <Button size="sm" onClick={() => run(r)} disabled={busy === r.key}>
                {busy === r.key ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                {ar ? "تصدير" : "Export"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
