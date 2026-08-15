import { createFileRoute } from "@tanstack/react-router";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/effectivity")({
  head: () => ({ meta: [{ title: "Effectivity · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="effectivity"
      title="EFFECTIVITY / TCM"
      titleAr="EFFECTIVITY / TCM"
      description="Load Excel data and link maintenance chapters per effectivity."
      descriptionAr="تحميل بيانات Excel وربط فصول الصيانة لكل effectivity."
      icon={MODULE_ICONS.effectivity}
      acceptedKinds={["excel", "csv"]}
      supportsDatabase={true}
    />
  ),
});
