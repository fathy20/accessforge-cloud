import { createFileRoute } from "@tanstack/react-router";
import { FolderTree } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";

export const Route = createFileRoute("/_authenticated/modules/cmp-tcm")({
  head: () => ({ meta: [{ title: "CMP / TCM · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="cmp_tcm"
      title="CMP / TCM Tasks"
      titleAr="مهام CMP / TCM"
      description="Index a TCM folder of PDFs and generate indexed task cards."
      descriptionAr="فهرسة مجلد TCM من ملفات PDF وتوليد بطاقات مهام مفهرسة."
      icon={FolderTree}
      acceptedKinds={["pdf"]}
      minFiles={1}
    />
  ),
});
