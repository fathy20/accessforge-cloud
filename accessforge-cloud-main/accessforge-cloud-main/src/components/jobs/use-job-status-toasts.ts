import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { useI18n } from "@/lib/i18n";
import type { JobRecord } from "./job-status";

/**
 * Fires a toast when a job the user has already seen flips to done/failed.
 * Shared by the global queue and the per-module list so both behave the same.
 */
export function useJobStatusToasts(jobs: JobRecord[]) {
  const { t } = useI18n();
  const lastStatus = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    for (const job of jobs) {
      const previous = lastStatus.current.get(job.id);
      if (previous && previous !== job.status) {
        if (job.status === "done") {
          toast.success(`${job.module_key} ✓`, { description: t("jobs.toast.completed") });
        } else if (job.status === "failed") {
          toast.error(`${job.module_key} ✗`, {
            description: job.error_message?.slice(0, 140) ?? t("jobs.toast.failed"),
          });
        }
      }
      lastStatus.current.set(job.id, job.status);
    }
  }, [jobs, t]);
}
