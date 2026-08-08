import { createFileRoute } from "@tanstack/react-router";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/mail-merge")({
  head: () => ({ meta: [{ title: "Mail Merge · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="mail_merge"
      title="Mail Merge (Covering)"
      titleAr="Mail Merge (Covering)"
      description="Generate RC cards by merging a Word template with Excel data."
      descriptionAr="توليد بطاقات RC بدمج قالب Word مع بيانات Excel."
      icon={MODULE_ICONS.mail_merge}
      acceptedKinds={["docx", "excel"]}
      minFiles={2}
    />
  ),
});
