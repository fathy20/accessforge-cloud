import { createFileRoute } from "@tanstack/react-router";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/utilization")({
  head: () => ({ meta: [{ title: "Utilization · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="utilization"
      title="Utilization"
      titleAr="الاستخدام (Utilization)"
      description="Track aircraft utilization with cryptographic record hashing."
      descriptionAr="تتبع استخدام الطائرة مع تجزئة تشفيرية للسجلات."
      icon={MODULE_ICONS.utilization}
      acceptedKinds={["excel", "csv"]}
      supportsDatabase={true}
    />
  ),
});
