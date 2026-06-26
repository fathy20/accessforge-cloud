import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/app/PlaceholderPage";

export const Route = createFileRoute("/_authenticated/uploads")({
  head: () => ({ meta: [{ title: "Uploads · REDSEA" }] }),
  component: () => (
    <PlaceholderPage
      title="Uploads"
      description="Drag-and-drop PDF / Excel / DOCX uploads with sha256 dedupe and full-text search. Coming in Phase 2."
    />
  ),
});
