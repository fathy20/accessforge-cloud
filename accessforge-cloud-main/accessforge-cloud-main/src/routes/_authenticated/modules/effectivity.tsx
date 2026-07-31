import { createFileRoute } from "@tanstack/react-router";
import { Table2 } from "lucide-react";
import { ModuleRunner } from "@/components/app/ModuleRunner";

export const Route = createFileRoute("/_authenticated/modules/effectivity")({
  head: () => ({ meta: [{ title: "Effectivity · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="effectivity"
      title="EFFECTIVITY / TCM"
      titleAr="EFFECTIVITY / TCM"
      description="Load Excel data and link maintenance chapters per effectivity."
      descriptionAr="تحميل بيانات Excel وربط فصول الصيانة لكل effectivity."
      icon={Table2}
      acceptedKinds={["excel", "csv"]}
      supportsDatabase={true}
      comingSoon
    />
  ),
});
