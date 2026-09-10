import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { format, parseISO } from "date-fns";
import { Activity, ArrowRight, FileText, FolderKanban, Layers, ListTodo } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { PageHeader } from "@/components/app/PageHeader";
import { DonutChart } from "@/components/charts/DonutChart";
import { StackedAreaChart } from "@/components/charts/StackedAreaChart";
import {
  ACTIVE_POLL_MS,
  IDLE_POLL_MS,
  JOB_STATUSES,
  JOB_STATUS_COLOR,
  JOB_STATUS_TONE,
  type JobRecord,
  type JobStatus,
} from "@/components/jobs/job-status";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard · REDSEA" }] }),
  component: DashboardPage,
});

interface UploadRecord {
  id: string;
  original_name: string;
  kind: string;
}

/** Shape of GET /api/dashboard/summary — aggregated in SQL on the server. */
interface DashboardSummary {
  jobs: {
    total: number;
    active: boolean;
    by_status: Record<JobStatus, number>;
    by_module: Array<{ module_key: string; count: number }>;
    daily: Array<{ day: string; done: number; failed: number }>;
    recent: JobRecord[];
  };
  uploads: { total: number; recent: UploadRecord[] };
  projects: { total: number };
}

const HISTORY_DAYS = 14;

async function loadDashboard() {
  // One request carrying a few dozen numbers, instead of the caller's whole
  // job and upload history reduced in the browser on every poll.
  const summary = await ApiClient.fetch<DashboardSummary>("/dashboard/summary");

  const statusCounts = Object.fromEntries(
    JOB_STATUSES.map((status) => [status, summary.jobs.by_status[status] ?? 0]),
  ) as Record<JobStatus, number>;

  return {
    jobsTotal: summary.jobs.total,
    uploadsTotal: summary.uploads.total,
    projectsTotal: summary.projects.total,
    hasActiveJobs: summary.jobs.active,
    statusCounts,
    days: summary.jobs.daily.map((row) => ({
      label: format(parseISO(row.day), "MMM d"),
      values: { done: row.done, failed: row.failed },
    })),
    moduleBars: summary.jobs.by_module.map((row) => ({
      name: row.module_key.replace(/_/g, " "),
      value: row.count,
    })),
    recentJobs: summary.jobs.recent,
    recentUploads: summary.uploads.recent,
  };
}

function DashboardPage() {
  const { user } = useAuth();
  const perms = usePermissions();
  const { t } = useI18n();

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: loadDashboard,
    // Poll quickly only while a job is in flight; otherwise the dashboard was
    // re-downloading every job and upload row every 3 seconds for nothing.
    refetchInterval: (query) => (query.state.data?.hasActiveJobs ? ACTIVE_POLL_MS : IDLE_POLL_MS),
  });

  const displayName = user?.full_name || user?.email;
  const statusSlices = JOB_STATUSES.filter((status) => (stats?.statusCounts[status] ?? 0) > 0).map(
    (status) => ({
      key: status,
      label: t(`jobs.status.${status}`),
      value: stats?.statusCounts[status] ?? 0,
      color: JOB_STATUS_COLOR[status],
    }),
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={displayName}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <span>{t("dash.welcome")}</span>
            {perms.roles.map((role) => (
              <Badge key={role} variant="outline" className="capitalize">
                {role.replace("_", " ")}
              </Badge>
            ))}
          </span>
        }
        actions={
          <Link
            to="/jobs"
            className="inline-flex items-center gap-1.5 text-body text-primary hover:underline"
          >
            {t("dash.live_monitor")}
            <Activity className="size-3.5" aria-hidden="true" />
          </Link>
        }
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat
          icon={FolderKanban}
          label={t("nav.projects")}
          value={stats?.projectsTotal}
          to="/projects"
        />
        <Stat icon={FileText} label={t("nav.uploads")} value={stats?.uploadsTotal} to="/uploads" />
        <Stat icon={ListTodo} label={t("nav.jobs")} value={stats?.jobsTotal} to="/jobs" />
        <Stat
          icon={Layers}
          label={t("nav.modules")}
          value={perms.loading ? undefined : perms.modules.length}
          to="/modules"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-heading-3">
              {t("dash.jobs_history", { days: HISTORY_DAYS })}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <StackedAreaChart
              series={[
                { key: "done", label: t("jobs.status.done"), color: JOB_STATUS_COLOR.done },
                { key: "failed", label: t("jobs.status.failed"), color: JOB_STATUS_COLOR.failed },
              ]}
              points={stats?.days ?? []}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-heading-3">{t("dash.status_mix")}</CardTitle>
          </CardHeader>
          <CardContent className="grid min-h-56 place-items-center">
            {statusSlices.length > 0 ? (
              <DonutChart slices={statusSlices} centerLabel={t("dash.total")} />
            ) : (
              <p className="text-body text-fg-muted">{t("dash.no_jobs")}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-heading-3">{t("dash.recent_jobs")}</CardTitle>
            <SeeAll to="/jobs" label={t("dash.all")} />
          </CardHeader>
          <CardContent className="p-0">
            {!stats?.recentJobs.length ? (
              <p className="p-6 text-center text-body text-fg-muted">{t("dash.no_jobs")}</p>
            ) : (
              <ul className="divide-y divide-border">
                {stats.recentJobs.map((job) => (
                  <li key={job.id} className="flex items-center gap-3 px-4 py-2.5 text-body">
                    <Badge className={JOB_STATUS_TONE[job.status]}>
                      {t(`jobs.status.${job.status}`)}
                    </Badge>
                    <span className="font-mono">{job.module_key}</span>
                    <span className="font-mono text-caption text-fg-muted">
                      {job.id.slice(0, 8)}
                    </span>
                    <div className="flex-1" />
                    <time className="text-caption text-fg-muted" dateTime={job.created_at}>
                      {new Date(job.created_at).toLocaleString()}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-heading-3">{t("dash.recent_uploads")}</CardTitle>
            <SeeAll to="/uploads" label={t("dash.all")} />
          </CardHeader>
          <CardContent className="p-0">
            {!stats?.recentUploads.length ? (
              <p className="p-6 text-center text-body text-fg-muted">{t("dash.no_uploads")}</p>
            ) : (
              <ul className="divide-y divide-border">
                {stats.recentUploads.map((upload) => (
                  <li key={upload.id} className="flex items-center gap-2 px-4 py-2.5 text-body">
                    <FileText className="size-3.5 shrink-0 text-fg-muted" aria-hidden="true" />
                    <span className="flex-1 truncate">{upload.original_name}</span>
                    <Badge variant="outline" className="text-caption uppercase">
                      {upload.kind}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {stats && stats.moduleBars.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-heading-3">{t("dash.module_usage")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {stats.moduleBars.map((bar) => {
              const max = stats.moduleBars[0].value || 1;
              return (
                <div key={bar.name} className="flex items-center gap-3 text-body">
                  <span className="w-32 truncate capitalize">{bar.name}</span>
                  <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary"
                      style={{ width: `${(bar.value / max) * 100}%` }}
                    />
                  </div>
                  <span className="numeric-tabular w-8 text-end">{bar.value}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SeeAll({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-caption text-primary hover:underline"
    >
      {label} <ArrowRight className="size-3 rtl:rotate-180" aria-hidden="true" />
    </Link>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  to,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value?: number;
  to?: string;
}) {
  const inner = (
    <Card className={to ? "transition-colors hover:bg-interactive-hover" : ""}>
      <CardContent className="flex items-center gap-4 p-5">
        <div className="grid size-11 place-items-center rounded-lg bg-brand-subtle text-primary">
          <Icon className="size-5" />
        </div>
        <div>
          <p className="text-caption uppercase tracking-wider text-fg-muted">{label}</p>
          <p className="numeric-tabular mt-1 text-2xl font-bold leading-none">{value ?? "—"}</p>
        </div>
      </CardContent>
    </Card>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}
