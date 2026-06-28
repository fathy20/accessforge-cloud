import { createFileRoute } from "@tanstack/react-router";
import { Stamp } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";

export const Route = createFileRoute("/_authenticated/modules/task-stamping")({
  head: () => ({ meta: [{ title: "Task Stamping · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="task_stamping"
      title="Task Stamping"
      titleAr="ختم المهام"
      description="Stamp Tail / Station / Date onto selected PDFs."
      descriptionAr="ختم رقم الطائرة والمحطة والتاريخ على ملفات PDF المختارة."
      icon={Stamp}
      acceptedKinds={["pdf"]}
    />
  ),
});
