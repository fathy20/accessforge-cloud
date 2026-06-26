import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/effectivity")({
  head: () => ({ meta: [{ title: "Effectivity · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="effectivity"
      title="Effectivity"
      description="Load Excel data and link maintenance chapters per effectivity."
    />
  ),
});
