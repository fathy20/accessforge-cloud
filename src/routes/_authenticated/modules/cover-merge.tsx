import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/cover-merge")({
  head: () => ({ meta: [{ title: "Cover Merge · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="cover_merge"
      title="Cover Merge"
      description="Merge cover PDFs onto task cards."
    />
  ),
});
