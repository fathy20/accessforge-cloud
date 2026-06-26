import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/task-stamping")({
  head: () => ({ meta: [{ title: "Task Stamping · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="task_stamping"
      title="Task Stamping"
      description="Stamp tail number, station, and date onto PDF documents."
    />
  ),
});
