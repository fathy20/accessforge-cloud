import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, RotateCcw, Ban, Download, ListTodo, Activity } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
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
    queryKey: ["jobs", moduleKey],
    queryFn: async () => {
      return await ApiClient.fetch(`/jobs?module_key=${moduleKey}`);
    },
    refetchInterval: 2000,
  });

  const lastStatus = useRef<Map<string, string>>(new Map());
  useEffect(() => { 
    for (const row of jobs) {
      const prev = lastStatus.current.get(row.id);
      if (prev && prev !== row.status) {
          if (row.status === "done") {
            toast.success(`${moduleKey} ✓`, { description: ar ? "اكتملت المهمة" : "Job completed" });
          } else if (row.status === "failed") {
            toast.error(`${moduleKey} ✗`, { description: row.error_message?.slice(0, 140) ?? (ar ? "فشلت المهمة" : "Job failed") });
          }
      }
      lastStatus.current.set(row.id, row.status);
    }
  }, [jobs, ar, moduleKey]);

  const retry = async (id: string) => {
    toast.error("Retry not implemented yet in new backend");
  };

  const cancel = async (id: string) => {
    toast.error("Cancel not implemented yet in new backend");
  };

  const downloadOutput = (url: string) => {
    const fullUrl = url.startsWith("http") ? url : `http://localhost:8000${url}`;
    window.open(fullUrl, "_blank", "noopener,noreferrer");
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
            {jobs.map((j: any) => {
              const st = j.status as JobStatus;
              const outputs = ((j.output_refs as { files?: {name: string, url: string}[] } | null)?.files) ?? [];
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
                        onClick={() => downloadOutput(outputs[0].url)}>
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
                        <Button key={p.url} size="sm" variant="outline" className="h-7 text-xs gap-1.5"
                          onClick={() => downloadOutput(p.url)}>
                          <Download className="size-3" />
                          <span className="font-mono truncate max-w-[220px]">{p.name}</span>
                        </Button>
                      ))}
                    </div>
                  )}
                  {j.error_message && (
                    <p className="text-xs text-destructive mt-1.5 font-mono whitespace-pre-wrap">{j.error_message}</p>
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
