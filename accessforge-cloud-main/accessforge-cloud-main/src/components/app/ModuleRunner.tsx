import { useState, useCallback, useRef } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Play, FileText, ShieldAlert, UploadCloud, Database } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { ApiClient } from "@/lib/apiClient";
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
import { ModuleJobs } from "@/components/app/ModuleJobs";
import { DataSourceToggle, DataSource } from "@/components/app/DataSourceToggle";
import { sha256Hex, detectKind, sanitizeName } from "@/lib/uploads/helpers";

type Kind = "pdf" | "excel" | "docx" | "csv" | "image" | "other";
const MAX_BYTES = 100 * 1024 * 1024; // 100MB

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
  /** Extra UI controls to render below the header. */
  extraControls?: React.ReactNode;
  /** True if this module supports fetching from DB */
  supportsDatabase?: boolean;
}

export function ModuleRunner(props: ModuleRunnerProps) {
  const {
    moduleKey, title, titleAr, description, descriptionAr,
    icon: Icon, acceptedKinds, minFiles = 1, maxFiles, extraInput, extraControls, supportsDatabase
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
  const [uploading, setUploading] = useState(false);
  const [dataSource, setDataSource] = useState<DataSource>("files");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: files = [], isLoading } = useQuery({
    queryKey: ["uploads", "kinds", acceptedKinds.join(",")],
    enabled: canView && dataSource === "files",
    queryFn: async () => {
      const data = await ApiClient.fetch("/uploads");
      // filter locally for now
      return data.filter((u: any) => acceptedKinds.includes(u.kind));
    },
  });

  const { data: projects = [] } = useQuery({
    queryKey: ["projects-min"],
    enabled: canView,
    queryFn: async () => {
      // Stub out projects since we removed them from the backend
      return [];
    },
  });

  const handleFiles = useCallback(async (fileList: FileList | File[]) => {
    if (!user) return;
    const list = Array.from(fileList);
    if (!list.length) return;
    setUploading(true);
    let ok = 0, fail = 0;
    const newSelected = new Set(selected);
    
    try {
      const formData = new FormData();
      for (const file of list) {
        if (file.size > MAX_BYTES) {
          toast.error(`${file.name}: > 100MB`);
          fail++; continue;
        }
        const kind = detectKind(file);
        if (!acceptedKinds.includes(kind)) {
          toast.error(`${file.name}: Invalid file type`);
          fail++; continue;
        }
        formData.append("files", file);
      }

      const results = await ApiClient.fetch("/uploads", {
        method: "POST",
        body: formData
      });
      
      for (const res of results) {
        newSelected.add(res.id);
        ok++;
      }
    } catch (e) {
      console.error(e);
      toast.error((e as Error).message);
      fail += list.length;
    }
    setUploading(false);
    setSelected(newSelected);
    if (ok) toast.success(ar ? `تم رفع ${ok} ملف` : `Uploaded ${ok} file(s)`);
    if (fail) toast.error(ar ? `فشل ${fail}` : `${fail} failed`);
    qc.invalidateQueries({ queryKey: ["uploads"] });
  }, [user, qc, ar, acceptedKinds, selected]);

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

  const tooMany = dataSource === "files" && maxFiles !== undefined && selected.size > maxFiles;
  const tooFew = dataSource === "files" && selected.size < minFiles;

  const enqueue = async () => {
    if (!user) return;
    if (dataSource === "files" && (tooFew || tooMany)) return;
    
    setRunning(true);
    const jobRefs: Record<string, any> = { ...(extraInput ?? {}) };
    
    // Add upload IDs if using file source
    if (dataSource === "files") {
      jobRefs.files = Array.from(selected);
    }
    
    // Pass the data source to the backend
    jobRefs.data_source = dataSource;

    try {
      const data = await ApiClient.fetch("/jobs", {
        method: "POST",
        body: JSON.stringify({
          module_key: moduleKey,
          input_refs: jobRefs,
        })
      });
      toast.success(ar ? `تم إنشاء المهمة ${data.id.slice(0, 8)}` : `Job ${data.id.slice(0, 8)} queued`);
      if (dataSource === "files") setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["jobs"] });
    } catch (error: any) {
      toast.error(error.message || "Failed to create job");
    } finally {
      setRunning(false);
    }
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

      {supportsDatabase && (
        <DataSourceToggle 
          value={dataSource} 
          onChange={setDataSource} 
        />
      )}

      {extraControls && (
        <div>{extraControls}</div>
      )}

      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-base flex items-center gap-3">
            {dataSource === "db" ? (
              ar ? "المعالجة من قاعدة البيانات" : "Processing from Database"
            ) : (
              <>
                <span>{ar ? `الملفات المحددة (${selected.size})` : `Selected files (${selected.size})`}</span>
                <input
                  type="file"
                  multiple
                  className="hidden"
                  ref={fileInputRef}
                  onChange={(e) => {
                    if (e.target.files) handleFiles(e.target.files);
                    // Reset value so the same file can be selected again
                    e.target.value = "";
                  }}
                />
                <Button 
                  size="sm" 
                  variant="secondary" 
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? <Loader2 className="size-4 animate-spin me-2" /> : <UploadCloud className="size-4 me-2" />}
                  {ar ? "اختر و ارفع ملفات" : "Select & Upload Files"}
                </Button>
              </>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
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
              {ar ? `تشغيل` : `Run`}
            </Button>
          </div>
        </CardHeader>
        
        {dataSource === "files" && (
          <CardContent className="p-0">
            {isLoading ? (
              <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
            ) : files.length === 0 ? (
              <div className="p-10 text-center text-sm text-muted-foreground">
                {ar ? "لا توجد ملفات بالنوع المطلوب. قم باختيار ورفع ملفات بالأعلى." : "No files of the required kind. Select and upload files above."}
              </div>
            ) : (
              <div className="divide-y divide-border">
                {files.map((u: any) => (
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
        )}
        
        {dataSource === "db" && (
          <CardContent className="p-10">
            <div className="text-center text-muted-foreground flex flex-col items-center gap-3">
              <Database className="size-10 opacity-50" />
              <p>
                {ar 
                  ? "سيتم قراءة البيانات ومعالجتها مباشرة من قاعدة البيانات. لا حاجة لرفع أي ملفات." 
                  : "Data will be read and processed directly from the database. No files needed."}
              </p>
            </div>
          </CardContent>
        )}
      </Card>

      <ModuleJobs moduleKey={moduleKey} />

      <Card><CardContent className="p-4 text-xs text-muted-foreground">
        {ar
          ? "المعالجة الفعلية تتم في Python worker مستقل. تتبع تقدّم المهمة من صفحة Jobs."
          : "Actual processing runs in the Python worker. Track progress on the Jobs page."}
      </CardContent></Card>

    </div>
  );
}
