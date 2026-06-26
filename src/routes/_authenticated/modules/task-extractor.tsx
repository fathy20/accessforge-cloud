import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/task-extractor")({
  head: () => ({ meta: [{ title: "Task Extractor · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="task_extractor"
      title="Task Extractor"
      description="Extract maintenance tasks from PDF documents using RegEx + OCR. Will run as a background job on the Python worker (Phase 4)."
    />
  ),
});
