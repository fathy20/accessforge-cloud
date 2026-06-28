import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Play, FileText, ShieldAlert } from "lucide-react";
import type { LucideIcon } from "lucide-react";
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

type Kind = "pdf" | "excel" | "docx" | "csv" | "image" | "other";

export interface ModuleRunnerProps {
  moduleKey: string;
  title: string;
  titleAr: string;
  description: string;
  descriptionAr: string;
  icon: LucideIcon;
  /** Accepted upload kinds for this module. */
  acceptedKinds: Kind[];
  /** Minimum number of files required to run. Default 1. */
  minFiles?: number;
  /** Maximum number of files allowed to run. Default unlimited. */
  maxFiles?: number;
  /** Extra payload merged into job.input_refs. */
  extraInput?: Record<string, unknown>;
}

export function ModuleRunner(props: ModuleRunnerProps) {
  const {
    moduleKey, title, titleAr, description, descriptionAr,
    icon: Icon, acceptedKinds, minFiles = 1, maxFiles, extraInput,
  } = props;

  const { user } = useAuth();
  const perms = usePermissions();
  const { lang } = useI18n();
  const ar = lang === "ar";
  const qc = useQueryClient();
  const canView = perms.canViewModule(moduleKey);
  const canRun = perms.canRunModule(moduleKey);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [projectId, setProjectId] = useState<string>("none");
  const [running, setRunning] = useState(false);

  const { data: files = [], isLoading } = useQuery({
    queryKey: ["uploads", "kinds", acceptedKinds.join(",")],
    enabled: canView,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("uploads")
        .select("id, original_name, size_bytes, created_at, storage_path, kind")
        .in("kind", acceptedKinds)
        .order("created_at", { ascending: false })
        .limit(200);
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
      <Card><CardContent className="p-10 grid place-items-center text-center gap-2">
        <ShieldAlert className="size-10 text-destructive" />
        <h2 className="text-lg font-semibold">{ar ? "ليس لديك صلاحية" : "No access"}</h2>
        <p className="text-sm text-muted-foreground max-w-md">
          {ar ? "اطلب من المسؤول منحك صلاحية على " : "Ask an admin to grant access to "}
          <span className="font-mono">{moduleKey}</span>.
        </p>
      </CardContent></Card>
    );
  }

  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const tooMany = maxFiles !== undefined && selected.size > maxFiles;
  const tooFew = selected.size < minFiles;

  const enqueue = async () => {
    if (!user || tooFew || tooMany) return;
    setRunning(true);
    const { data, error } = await supabase.from("jobs").insert({
      module_key: moduleKey,
      created_by: user.id,
      project_id: projectId === "none" ? null : projectId,
      status: "queued",
      input_refs: { upload_ids: Array.from(selected), ...(extraInput ?? {}) },
    }).select("id").single();
    setRunning(false);
    if (error) { toast.error(error.message); return; }
    toast.success(ar ? `تم إنشاء المهمة ${data.id.slice(0, 8)}` : `Job ${data.id.slice(0, 8)} queued`);
    setSelected(new Set());
    qc.invalidateQueries({ queryKey: ["jobs"] });
  };

  const kindLabel = acceptedKinds.join(" · ").toUpperCase();

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Icon className="size-6 text-primary" />
            {ar ? titleAr : title}
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            {ar ? descriptionAr : description}
          </p>
        </div>
        <div className="flex gap-1.5">
          <Badge variant="secondary">{kindLabel}</Badge>
          <Badge variant={canRun ? "default" : "outline"}>{canRun ? "Run ✓" : "Run ✗"}</Badge>
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-base">
            {ar ? `الملفات المتاحة (${files.length})` : `Available files (${files.length})`}
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
              disabled={!canRun || running || tooFew || tooMany}
              title={
                !canRun ? (ar ? "ليس لديك صلاحية تشغيل" : "No run permission") :
                tooMany ? (ar ? `الحد الأقصى ${maxFiles}` : `Max ${maxFiles}`) :
                tooFew ? (ar ? `اختر على الأقل ${minFiles}` : `Pick at least ${minFiles}`) : ""
              }
            >
              {running ? <Loader2 className="size-4 animate-spin me-1.5" /> : <Play className="size-4 me-1.5" />}
              {ar ? `تشغيل (${selected.size})` : `Run (${selected.size})`}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
          ) : files.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              {ar ? "لا توجد ملفات بالنوع المطلوب. " : "No files of the required kind. "}
              <Link to="/uploads" className="text-primary underline">{ar ? "ارفع ملفات" : "Upload some"}</Link>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {files.map((u) => (
                <label key={u.id} className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30">
                  <Checkbox checked={selected.has(u.id)} onCheckedChange={() => toggle(u.id)} />
                  <FileText className="size-4 text-muted-foreground shrink-0" />
                  <span className="flex-1 truncate text-sm">{u.original_name}</span>
                  <Badge variant="outline" className="uppercase text-[10px]">{u.kind}</Badge>
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
          ? "المعالجة الفعلية تتم في Python worker مستقل. تتبع تقدّم المهمة من صفحة Jobs."
          : "Actual processing runs in the Python worker. Track progress on the Jobs page."}
      </CardContent></Card>
    </div>
  );
}
