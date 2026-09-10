import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";
import { JobList } from "@/components/jobs/JobList";
import { useJobStatusToasts } from "@/components/jobs/use-job-status-toasts";
import { jobsRefetchInterval, type JobRecord } from "@/components/jobs/job-status";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ModuleJobs({ moduleKey }: { moduleKey: string }) {
  const { t } = useI18n();

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs", moduleKey],
    queryFn: () =>
      ApiClient.fetch<JobRecord[]>(`/jobs?module_key=${encodeURIComponent(moduleKey)}`),
    refetchInterval: jobsRefetchInterval,
  });

  useJobStatusToasts(jobs);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-heading-3">
          {t("jobs.module_count", { count: jobs.length })}
          <span className="inline-flex items-center gap-1 text-caption font-normal text-status-success-foreground">
            <Activity className="size-3.5" aria-hidden="true" /> {t("jobs.live")}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <JobList jobs={jobs} isLoading={isLoading} emptyMessage={t("jobs.module_empty")} />
      </CardContent>
    </Card>
  );
}
