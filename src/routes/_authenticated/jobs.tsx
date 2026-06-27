import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, RotateCcw, Ban, ListTodo, Activity } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useI18n } from "@/lib/i18n";
import { usePermissions } from "@/lib/auth/use-permissions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

export const Route = createFileRoute("/_authenticated/jobs")({
  head: () => ({ meta: [{ title: "Jobs · REDSEA" }] }),
  component: JobsPage,
});

type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

const statusTone: Record<JobStatus, string> = {
  queued: "bg-info/15 text-info",
  running: "bg-warning/15 text-warning",
  done: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  cancelled: "bg-muted text-muted-foreground",
};

function JobsPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";
  const perms = usePermissions();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"all" | JobStatus>("all");

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("jobs")
        .select("id, module_key, status, progress, error, created_at, started_at, finished_at, created_by, project_id, worker_id")
        .order("created_at", { ascending: false })
        .limit(200);
      if (error) throw error;
      return data;
    },
  });

  // Realtime: refresh on any job change
  useEffect(() => {
    const ch = supabase
      .channel("jobs-live")
      .on("postgres_changes", { event: "*", schema: "public", table: "jobs" }, () => {
        qc.invalidateQueries({ queryKey: ["jobs"] });
      })
      .subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [qc]);

  const filtered = useMemo(
    () => jobs.filter((j) => filter === "all" || j.status === filter),
    [jobs, filter],
  );

  const counts = useMemo(() => ({
    queued: jobs.filter((j) => j.status === "queued").length,
    running: jobs.filter((j) => j.status === "running").length,
    done: jobs.filter((j) => j.status === "done").length,
    failed: jobs.filter((j) => j.status === "failed").length,
    cancelled: jobs.filter((j) => j.status === "cancelled").length,
  }), [jobs]);

  const retry = async (id: string) => {
    const { error } = await supabase.from("jobs").update({
      status: "queued", progress: 0, error: null, started_at: null, finished_at: null, worker_id: null,
    }).eq("id", id);
    if (error) toast.error(error.message); else toast.success(ar ? "تمت إعادة الجدولة" : "Re-queued");
  };

  const cancel = async (id: string) => {
    const { error } = await supabase.from("jobs").update({ status: "cancelled", finished_at: new Date().toISOString() }).eq("id", id);
    if (error) toast.error(error.message); else toast.success(ar ? "تم الإلغاء" : "Cancelled");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            {ar ? "قائمة المهام" : "Job Queue"}
            <span className="inline-flex items-center gap-1 text-xs font-normal text-success">
              <Activity className="size-3.5" /> Live
            </span>
          </h1>
          <p className="text-sm text-muted-foreground">
            {ar ? "متابعة لحظية لجميع المهام الخلفية." : "Live monitor for background processing jobs."}
          </p>
        </div>
        <Select value={filter} onValueChange={(v) => setFilter(v as typeof filter)}>
          <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{ar ? "الكل" : "All"}</SelectItem>
            <SelectItem value="queued">Queued</SelectItem>
            <SelectItem value="running">Running</SelectItem>
            <SelectItem value="done">Done</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {(["queued", "running", "done", "failed", "cancelled"] as JobStatus[]).map((s) => (
          <Card key={s}><CardContent className={`p-4 ${statusTone[s]} rounded-md`}>
            <p className="text-[10px] uppercase tracking-wider opacity-80">{s}</p>
            <p className="text-2xl font-bold mt-1">{counts[s]}</p>
          </CardContent></Card>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">
          {ar ? `المهام (${filtered.length})` : `Jobs (${filtered.length})`}
        </CardTitle></CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
          ) : filtered.length === 0 ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              <ListTodo className="size-8 mx-auto mb-2 opacity-50" />
              {ar ? "لا توجد مهام." : "No jobs."}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {filtered.map((j) => {
                const st = j.status as JobStatus;
                return (
                  <div key={j.id} className="px-4 py-3 hover:bg-muted/30">
                    <div className="flex items-center gap-3 flex-wrap">
                      <Badge className={statusTone[st]}>{st}</Badge>
                      <span className="font-mono text-sm">{j.module_key}</span>
                      <span className="text-xs text-muted-foreground font-mono">{j.id.slice(0, 8)}</span>
                      <div className="flex-1" />
                      <span className="text-xs text-muted-foreground">{new Date(j.created_at).toLocaleString()}</span>
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
    </div>
  );
}
