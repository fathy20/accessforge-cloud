import type { Query } from "@tanstack/react-query";

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export const JOB_STATUSES: readonly JobStatus[] = [
  "queued",
  "running",
  "done",
  "failed",
  "cancelled",
];

export interface JobOutputRef {
  name?: string;
  storage_name?: string;
  url?: string;
}

export interface JobRecord {
  id: string;
  module_key: string;
  status: JobStatus;
  progress: number | null;
  error_message: string | null;
  output_refs: { files?: Array<JobOutputRef | string> } | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  /** Claims so far (first run + reclaims + retries). */
  attempt: number;
  /** Set on a running job; the worker kills it at its next tick. */
  cancel_requested: boolean;
}

/** Badge / tile tone per status. Status colours are reserved for state only. */
export const JOB_STATUS_TONE: Record<JobStatus, string> = {
  queued: "bg-status-info-background text-status-info-foreground",
  running: "bg-status-warning-background text-status-warning-foreground",
  done: "bg-status-success-background text-status-success-foreground",
  failed: "bg-status-danger-background text-status-danger-foreground",
  cancelled: "bg-status-neutral-background text-status-neutral-foreground",
};

/** Solid status colours for SVG marks (charts cannot use utility classes on fills). */
export const JOB_STATUS_COLOR: Record<JobStatus, string> = {
  queued: "var(--info)",
  running: "var(--warning)",
  done: "var(--success)",
  failed: "var(--destructive)",
  cancelled: "var(--muted-foreground)",
};

export const ACTIVE_POLL_MS = 3_000;
export const IDLE_POLL_MS = 20_000;

export function isActiveJob(job: Pick<JobRecord, "status">): boolean {
  return job.status === "queued" || job.status === "running";
}

/**
 * Poll fast only while something is actually in flight. A fixed 2-second
 * interval on every job list hammered the API from every open tab even when
 * nothing had changed for hours.
 */
export function jobsRefetchInterval(query: Query<JobRecord[], Error>): number {
  const jobs = query.state.data;
  return jobs?.some(isActiveJob) ? ACTIVE_POLL_MS : IDLE_POLL_MS;
}

/** Normalises the mixed string/object shape the worker writes into output_refs. */
export function jobOutputs(job: Pick<JobRecord, "output_refs">): JobOutputRef[] {
  const files = job.output_refs?.files ?? [];
  return files.map((entry) =>
    typeof entry === "string" ? { name: entry.split("/").pop() || entry, url: entry } : entry,
  );
}
