import { createFileRoute } from "@tanstack/react-router";
import { ModuleRunner } from "@/components/app/ModuleRunner";
import { MODULE_ICONS } from "@/lib/modules/icons";

export const Route = createFileRoute("/_authenticated/modules/cover-merge")({
  head: () => ({ meta: [{ title: "Cover Merge · REDSEA" }] }),
  component: () => (
    <ModuleRunner
      moduleKey="cover_merge"
      title="Cover Merge"
      titleAr="دمج الأغلفة"
      description="Merge selected cover PDFs onto task-card PDFs."
      descriptionAr="دمج ملفات أغلفة PDF المختارة على بطاقات المهام."
      icon={MODULE_ICONS.cover_merge}
      acceptedKinds={["pdf"]}
      minFiles={2}
    />
  ),
});
