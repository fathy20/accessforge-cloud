import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Ban, Download, ListTodo, Loader2, RotateCcw } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";
import { usePermissions } from "@/lib/auth/use-permissions";
import { downloadAuthenticated, outputDownloadEndpoint } from "@/lib/uploads/helpers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { JOB_STATUS_TONE, jobOutputs, type JobOutputRef, type JobRecord } from "./job-status";

interface JobListProps {
  jobs: JobRecord[];
  isLoading: boolean;
  /** Show the module key on each row (the global queue mixes modules; a module page does not). */
  showModule?: boolean;
  emptyMessage: string;
}

export function JobList({ jobs, isLoading, showModule = false, emptyMessage }: JobListProps) {
  const { t } = useI18n();
  const perms = usePermissions();
  const queryClient = useQueryClient();
  const canRetry = perms.hasAnyRole(["engineer", "admin", "super_admin"]);

  const act = async (job: JobRecord, action: "cancel" | "retry") => {
    try {
      await ApiClient.fetch(`/jobs/${encodeURIComponent(job.id)}/${action}`, { method: "POST" });
      toast.success(t(action === "cancel" ? "jobs.cancel_sent" : "jobs.retry_sent"));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] }),
      ]);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("jobs.action_failed"));
    }
  };

  const downloadOutput = async (output: JobOutputRef) => {
    const endpoint = outputDownloadEndpoint(output);
    if (!endpoint) {
      toast.error(t("jobs.no_file"));
      return;
    }
    try {
      await downloadAuthenticated(endpoint, output.name || "output");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("jobs.download_failed"));
    }
  };

  if (isLoading) {
    return (
      <div className="grid place-items-center p-10" role="status">
        <Loader2 className="size-5 animate-spin text-fg-muted" aria-hidden="true" />
        <span className="sr-only">{t("jobs.loading")}</span>
      </div>
    );
  }

  if (jobs.length === 0) {
    return (
      <div className="p-10 text-center text-body text-fg-muted">
        <ListTodo className="mx-auto mb-2 size-8 opacity-50" aria-hidden="true" />
        {emptyMessage}
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {jobs.map((job) => {
        const outputs = jobOutputs(job);
        const active = job.status === "queued" || job.status === "running";
        return (
          <li key={job.id} className="px-4 py-3 hover:bg-interactive-hover">
            <div className="flex flex-wrap items-center gap-3">
              <Badge className={JOB_STATUS_TONE[job.status]}>
                {t(`jobs.status.${job.status}`)}
              </Badge>
              {showModule && <span className="font-mono text-body">{job.module_key}</span>}
              <span className="font-mono text-caption text-fg-muted">{job.id.slice(0, 8)}</span>
              {job.attempt > 1 && (
                <span className="text-caption text-fg-muted">
                  {t("jobs.attempt", { n: job.attempt })}
                </span>
              )}
              <div className="flex-1" />
              <time className="text-caption text-fg-muted" dateTime={job.created_at}>
                {new Date(job.created_at).toLocaleString()}
              </time>
              {(job.status === "failed" || job.status === "cancelled") && canRetry && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => act(job, "retry")}
                  aria-label={t("jobs.retry")}
                  title={t("jobs.retry")}
                >
                  <RotateCcw className="size-4" aria-hidden="true" />
                </Button>
              )}
              {active && job.cancel_requested && (
                <span className="text-caption text-fg-muted">{t("jobs.cancelling")}</span>
              )}
              {active && !job.cancel_requested && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => act(job, "cancel")}
                  aria-label={t("jobs.cancel")}
                  title={t("jobs.cancel")}
                >
                  <Ban className="size-4 text-destructive" aria-hidden="true" />
                </Button>
              )}
            </div>
            {job.status === "running" && (
              <Progress value={job.progress ?? 0} className="mt-2 h-1.5" />
            )}
            {outputs.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {outputs.map((output, index) => (
                  <Button
                    key={output.url ?? output.storage_name ?? `${job.id}-${index}`}
                    size="sm"
                    variant={index === 0 && job.status === "done" ? "default" : "outline"}
                    className="h-7 gap-1.5 text-caption"
                    onClick={() => downloadOutput(output)}
                  >
                    <Download className="size-3" aria-hidden="true" />
                    <span className="max-w-[220px] truncate font-mono">
                      {output.name ?? t("jobs.download")}
                    </span>
                  </Button>
                ))}
              </div>
            )}
            {job.error_message && (
              <p className="mt-1.5 whitespace-pre-wrap font-mono text-caption text-status-danger-foreground">
                {job.error_message}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
