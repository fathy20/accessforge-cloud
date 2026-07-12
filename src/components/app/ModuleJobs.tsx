import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, RotateCcw, Ban, Download, ListTodo, Activity } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useI18n } from "@/lib/i18n";
import { usePermissions } from "@/lib/auth/use-permissions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

const statusTone: Record<JobStatus, string> = {
  queued: "bg-info/15 text-info",
  running: "bg-warning/15 text-warning",
  done: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

export function ModuleJobs({ moduleKey }: { moduleKey: string }) {
  const { lang } = useI18n();
  const ar = lang === "ar";
  const perms = usePermissions();
  const qc = useQueryClient();

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs", "module", moduleKey],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("jobs")
        .select("id, module_key, status, progress, error, output_refs, created_at, started_at, finished_at, worker_id")
        .eq("module_key", moduleKey)
        .order("created_at", { ascending: false })
        .limit(50);
      if (error) throw error;
      return data;
    },
  });

  const lastStatus = useRef<Map<string, string>>(new Map());
  useEffect(() => { for (const j of jobs) lastStatus.current.set(j.id, j.status); }, [jobs]);

  useEffect(() => {
    const ch = supabase
      .channel(`jobs-live-${moduleKey}`)
      .on("postgres_changes",
        { event: "*", schema: "public", table: "jobs", filter: `module_key=eq.${moduleKey}` },
        (payload) => {
          qc.invalidateQueries({ queryKey: ["jobs", "module", moduleKey] });
          const row = payload.new as { id?: string; status?: string; error?: string | null } | null;
          if (!row?.id || !row.status) return;
          const prev = lastStatus.current.get(row.id);
          if (prev === row.status) return;
          lastStatus.current.set(row.id, row.status);
          if (row.status === "done") {
            toast.success(`${moduleKey} ✓`, { description: ar ? "اكتملت المهمة" : "Job completed" });
          } else if (row.status === "failed") {
            toast.error(`${moduleKey} ✗`, { description: row.error?.slice(0, 140) ?? (ar ? "فشلت المهمة" : "Job failed") });
          }
        })
      .subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [qc, ar, moduleKey]);

  const retry = async (id: string) => {
    const { error } = await supabase.from("jobs").update({
      status: "queued", progress: 0, error: null, started_at: null, finished_at: null, worker_id: null,
    }).eq("id", id);
    if (error) toast.error(error.message); else toast.success(ar ? "تمت إعادة الجدولة" : "Re-queued");
  };

  const cancel = async (id: string) => {
    const { error } = await supabase.from("jobs").update({
      status: "cancelled", finished_at: new Date().toISOString(),
    }).eq("id", id);
    if (error) toast.error(error.message); else toast.success(ar ? "تم الإلغاء" : "Cancelled");
  };

  const downloadOutput = async (path: string) => {
    const { data, error } = await supabase.storage.from("outputs").createSignedUrl(path, 60);
    if (error || !data) { toast.error(error?.message ?? "Failed"); return; }
    window.open(data.signedUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <Card>
      <CardHeader className="pb-3 flex flex-row items-center justify-between gap-3 flex-wrap">
        <CardTitle className="text-base flex items-center gap-2">
          {ar ? `مهام هذا الموديول (${jobs.length})` : `Jobs for this module (${jobs.length})`}
          <span className="inline-flex items-center gap-1 text-xs font-normal text-success">
            <Activity className="size-3.5" /> Live
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-8 grid place-items-center">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            <ListTodo className="size-8 mx-auto mb-2 opacity-50" />
            {ar ? "لا توجد مهام لهذا الموديول بعد." : "No jobs for this module yet."}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {jobs.map((j) => {
              const st = j.status as JobStatus;
              const outputs = ((j.output_refs as { files?: string[] } | null)?.files) ?? [];
              const done = st === "done";
              return (
                <div key={j.id} className="px-4 py-3 hover:bg-muted/30">
                  <div className="flex items-center gap-3 flex-wrap">
                    <Badge className={statusTone[st]}>{st}</Badge>
                    <span className="text-xs text-muted-foreground font-mono">{j.id.slice(0, 8)}</span>
                    <div className="flex-1" />
                    <span className="text-xs text-muted-foreground">
                      {new Date(j.created_at).toLocaleString()}
                    </span>
                    {done && outputs.length > 0 && (
                      <Button size="sm" variant="default" className="h-7 text-xs gap-1.5"
                        onClick={() => downloadOutput(outputs[0])}>
                        <Download className="size-3" />
                        {ar ? "تحميل" : "Download"}
                      </Button>
                    )}
                    {(st === "failed" || st === "cancelled") && perms.hasAnyRole(["engineer", "admin", "super_admin"]) && (
                      <Button variant="ghost" size="icon" onClick={() => retry(j.id)} title={ar ? "إعادة" : "Retry"}>
                        <RotateCcw className="size-4" />
                      </Button>
                    )}
                    {(st === "queued" || st === "running") && (
                      <Button variant="ghost" size="icon" onClick={() => cancel(j.id)} title={ar ? "إلغاء" : "Cancel"}>
                        <Ban className="size-4 text-destructive" />
                      </Button>
                    )}
                  </div>
                  {st === "running" && (
                    <Progress value={j.progress ?? 0} className="h-1.5 mt-2" />
                  )}
                  {outputs.length > 1 && done && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {outputs.slice(1).map((p) => (
                        <Button key={p} size="sm" variant="outline" className="h-7 text-xs gap-1.5"
                          onClick={() => downloadOutput(p)}>
                          <Download className="size-3" />
                          <span className="font-mono truncate max-w-[220px]">{p.split("/").pop()}</span>
                        </Button>
                      ))}
                    </div>
                  )}
                  {j.error && (
                    <p className="text-xs text-destructive mt-1.5 font-mono whitespace-pre-wrap">{j.error}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
