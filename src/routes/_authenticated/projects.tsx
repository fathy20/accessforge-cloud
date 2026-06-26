import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/app/PlaceholderPage";

export const Route = createFileRoute("/_authenticated/projects")({
  head: () => ({ meta: [{ title: "Projects · REDSEA" }] }),
  component: () => (
    <PlaceholderPage
      title="Projects"
      description="Group uploads, jobs, and tasks under aircraft / station / check projects. Coming in Phase 2."
    />
  ),
});
