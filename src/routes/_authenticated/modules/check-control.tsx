import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/check-control")({
  head: () => ({ meta: [{ title: "Check Control · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="check_control"
      title="Check Control"
      description="Manage maintenance checks from CSV with full traceability."
    />
  ),
});
