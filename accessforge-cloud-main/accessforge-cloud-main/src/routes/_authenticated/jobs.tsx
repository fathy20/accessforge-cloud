import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";
import { PageHeader } from "@/components/app/PageHeader";
import { JobList } from "@/components/jobs/JobList";
import { useJobStatusToasts } from "@/components/jobs/use-job-status-toasts";
import {
  JOB_STATUSES,
  JOB_STATUS_TONE,
  jobsRefetchInterval,
  type JobRecord,
  type JobStatus,
} from "@/components/jobs/job-status";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export const Route = createFileRoute("/_authenticated/jobs")({
  head: () => ({ meta: [{ title: "Jobs · REDSEA" }] }),
  component: JobsPage,
});

function JobsPage() {
  const { t } = useI18n();
  const [filter, setFilter] = useState<"all" | JobStatus>("all");

  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => ApiClient.fetch<JobRecord[]>("/jobs"),
    refetchInterval: jobsRefetchInterval,
  });

  useJobStatusToasts(jobs);

  const filtered = useMemo(
    () => jobs.filter((job) => filter === "all" || job.status === filter),
    [jobs, filter],
  );

  const counts = useMemo(() => {
    const result = Object.fromEntries(JOB_STATUSES.map((status) => [status, 0])) as Record<
      JobStatus,
      number
    >;
    for (const job of jobs) result[job.status] = (result[job.status] ?? 0) + 1;
    return result;
  }, [jobs]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <>
            {t("jobs.title")}
            <span className="inline-flex items-center gap-1 text-caption font-normal text-status-success-foreground">
              <Activity className="size-3.5" aria-hidden="true" /> {t("jobs.live")}
            </span>
          </>
        }
        description={t("jobs.subtitle")}
        actions={
          <Select value={filter} onValueChange={(value) => setFilter(value as typeof filter)}>
            <SelectTrigger className="w-44" aria-label={t("jobs.filter_label")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("jobs.filter_all")}</SelectItem>
              {JOB_STATUSES.map((status) => (
                <SelectItem key={status} value={status}>
                  {t(`jobs.status.${status}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {JOB_STATUSES.map((status) => (
          <Card key={status}>
            <CardContent className={`rounded-md p-4 ${JOB_STATUS_TONE[status]}`}>
              <p className="text-caption uppercase tracking-wider opacity-80">
                {t(`jobs.status.${status}`)}
              </p>
              <p className="numeric-tabular mt-1 text-2xl font-bold">{counts[status]}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-heading-3">
            {t("jobs.count", { count: filtered.length })}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <JobList
            jobs={filtered}
            isLoading={isLoading}
            showModule
            emptyMessage={t("jobs.empty")}
          />
        </CardContent>
      </Card>
    </div>
  );
}
