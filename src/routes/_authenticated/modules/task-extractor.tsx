import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileSearch, Loader2, Play, FileText } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

const MODULE_KEY = "task_extractor";

export const Route = createFileRoute("/_authenticated/modules/task-extractor")({
  head: () => ({ meta: [{ title: "Task Extractor · REDSEA" }] }),
  component: TaskExtractor,
});

function TaskExtractor() {
  const { user } = useAuth();
  const perms = usePermissions();
  const { lang } = useI18n();
  const ar = lang === "ar";
  const qc = useQueryClient();
  const canRun = perms.canRunModule(MODULE_KEY);
  const canView = perms.canViewModule(MODULE_KEY);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [projectId, setProjectId] = useState<string>("none");
  const [running, setRunning] = useState(false);

  const { data: pdfs = [], isLoading } = useQuery({
    queryKey: ["uploads", "pdf"],
    enabled: canView,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("uploads")
        .select("id, original_name, size_bytes, created_at, storage_path")
        .eq("kind", "pdf")
        .order("created_at", { ascending: false })
        .limit(100);
      if (error) throw error;
      return data;
    },
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects-min"],
    enabled: canView,
    queryFn: async () => {
      const { data, error } = await supabase.from("projects").select("id, name").order("name");
      if (error) throw error;
      return data;
    },
  });

  if (!perms.loading && !canView) {
    return (
      <Card><CardContent className="p-10 text-center text-sm text-muted-foreground">
        {ar ? "ليس لديك صلاحية لهذا الموديول." : "You do not have access to this module."}
      </CardContent></Card>
    );
  }

  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const enqueue = async () => {
    if (!user || selected.size === 0) return;
    setRunning(true);
    const { data, error } = await supabase.from("jobs").insert({
      module_key: MODULE_KEY,
      created_by: user.id,
      project_id: projectId === "none" ? null : projectId,
      status: "queued",
      input_refs: { upload_ids: Array.from(selected) },
    }).select("id").single();
    setRunning(false);
    if (error) { toast.error(error.message); return; }
    toast.success(ar ? `تم إنشاء المهمة ${data.id.slice(0, 8)}` : `Job ${data.id.slice(0, 8)} queued`);
    setSelected(new Set());
    qc.invalidateQueries({ queryKey: ["jobs"] });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <FileSearch className="size-6 text-primary" />
            {ar ? "استخراج المهام" : "Task Extractor"}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            {ar ? "اختر ملفات PDF لاستخراج رموز Tasks منها (RegEx + OCR) عبر Python worker." :
                  "Pick PDFs to extract maintenance task codes from (RegEx + OCR) via the Python worker."}
          </p>
        </div>
        <Badge variant={canRun ? "default" : "outline"}>{canRun ? "Run ✓" : "Run ✗"}</Badge>
      </div>

      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-base">
            {ar ? `ملفات PDF (${pdfs.length})` : `PDF Files (${pdfs.length})`}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Select value={projectId} onValueChange={setProjectId}>
              <SelectTrigger className="w-44"><SelectValue placeholder={ar ? "بدون مشروع" : "No project"} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{ar ? "بدون مشروع" : "No project"}</SelectItem>
                {projects.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button
              onClick={enqueue}
              disabled={!canRun || running || selected.size === 0}
              title={!canRun ? (ar ? "ليس لديك صلاحية تشغيل" : "No run permission") : ""}
            >
              {running ? <Loader2 className="size-4 animate-spin me-1.5" /> : <Play className="size-4 me-1.5" />}
              {ar ? `تشغيل (${selected.size})` : `Run (${selected.size})`}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
          ) : pdfs.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              {ar ? "لا توجد ملفات PDF. " : "No PDFs available. "}
              <Link to="/uploads" className="text-primary underline">{ar ? "ارفع ملفات" : "Upload some"}</Link>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {pdfs.map((u) => (
                <label key={u.id} className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30">
                  <Checkbox checked={selected.has(u.id)} onCheckedChange={() => toggle(u.id)} />
                  <FileText className="size-4 text-muted-foreground shrink-0" />
                  <span className="flex-1 truncate text-sm">{u.original_name}</span>
                  <span className="text-xs text-muted-foreground">
                    {new Date(u.created_at).toLocaleDateString()}
                  </span>
                </label>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card><CardContent className="p-4 text-xs text-muted-foreground">
        {ar
          ? "ملاحظة: المعالجة الفعلية تتم في Python worker مستقل (Phase 4). الويب فقط ينشئ المهمة وينتظر النتائج."
          : "Note: actual processing runs in a separate Python worker (Phase 4). The web app only enqueues the job and waits for results."}
      </CardContent></Card>
    </div>
  );
}
