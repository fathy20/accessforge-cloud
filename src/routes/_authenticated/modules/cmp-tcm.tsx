import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/cmp-tcm")({
  head: () => ({ meta: [{ title: "CMP / TCM · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="cmp_tcm"
      title="CMP / TCM Tasks"
      description="Index TCM folder and generate indexed task cards."
    />
  ),
});
