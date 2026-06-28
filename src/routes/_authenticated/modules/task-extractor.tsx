import { createFileRoute } from "@tanstack/react-router";
import { FileSearch } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";

export const Route = createFileRoute("/_authenticated/modules/task-extractor")({
  head: () => ({ meta: [{ title: "Task Extractor · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="task_extractor"
      title="Task Extractor"
      titleAr="استخراج المهام"
      description="Pick PDFs to extract maintenance task codes from (RegEx + OCR) via the Python worker."
      descriptionAr="اختر ملفات PDF لاستخراج رموز المهام منها (RegEx + OCR) عبر Python worker."
      icon={FileSearch}
      acceptedKinds={["pdf"]}
      minFiles={1}
    />
  ),
});
