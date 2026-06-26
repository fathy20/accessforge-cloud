import { createFileRoute } from "@tanstack/react-router";
import { ModulePlaceholder } from "@/components/app/ModulePlaceholder";

export const Route = createFileRoute("/_authenticated/modules/mail-merge")({
  head: () => ({ meta: [{ title: "Mail Merge · REDSEA" }] }),
  component: () => (
    <ModulePlaceholder
      moduleKey="mail_merge"
      title="Mail Merge (Covering)"
      description="Generate RC cards from Word templates + Excel data."
    />
  ),
});
