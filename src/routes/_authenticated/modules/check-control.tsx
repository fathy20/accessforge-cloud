import { createFileRoute } from "@tanstack/react-router";
import { ListChecks } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";

export const Route = createFileRoute("/_authenticated/modules/check-control")({
  head: () => ({ meta: [{ title: "Check Control · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="check_control"
      title="Check Control"
      titleAr="التحكم في الفحوصات"
      description="Import CSV check definitions and manage check execution data."
      descriptionAr="استيراد تعريفات الفحوصات من CSV وإدارة بيانات تنفيذها."
      icon={ListChecks}
      acceptedKinds={["csv", "excel"]}
    />
  ),
});
