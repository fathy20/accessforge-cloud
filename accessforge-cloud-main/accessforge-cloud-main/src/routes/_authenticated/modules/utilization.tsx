import { createFileRoute } from "@tanstack/react-router";
import { Gauge } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";

export const Route = createFileRoute("/_authenticated/modules/utilization")({
  head: () => ({ meta: [{ title: "Utilization · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="utilization"
      title="Utilization"
      titleAr="الاستخدام (Utilization)"
      description="Track aircraft utilization with cryptographic record hashing."
      descriptionAr="تتبع استخدام الطائرة مع تجزئة تشفيرية للسجلات."
      icon={Gauge}
      acceptedKinds={["excel", "csv"]}
      supportsDatabase={true}
      comingSoon
    />
  ),
});
