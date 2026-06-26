import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/utilization")({
  head: () => ({ meta: [{ title: "Utilization · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="utilization"
      title="Utilization"
      description="Track aircraft utilization with cryptographic record hashing."
    />
  ),
});
