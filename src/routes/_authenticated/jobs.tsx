import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/app/PlaceholderPage";

export const Route = createFileRoute("/_authenticated/jobs")({
  head: () => ({ meta: [{ title: "Jobs · REDSEA" }] }),
  component: () => (
    <PlaceholderPage
      title="Job Queue"
      description="Live monitor for background processing jobs (PDF extract, OCR, stamping…). Coming in Phase 3."
    />
  ),
});
