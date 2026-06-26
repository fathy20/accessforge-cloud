import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";
import { PlaceholderPage } from "@/components/app/PlaceholderPage";

const searchSchema = z.object({ q: z.string().optional() });

export const Route = createFileRoute("/_authenticated/search")({
  head: () => ({ meta: [{ title: "Search · REDSEA" }] }),
  validateSearch: searchSchema,
  component: SearchPage,
});

function SearchPage() {
  const { q } = Route.useSearch();
  return (
    <PlaceholderPage
      title="Global Search"
      description={
        q
          ? `Powerful full-text + fuzzy search across uploads, tasks, jobs. Query: "${q}". Coming in Phase 2.`
          : "Powerful full-text + fuzzy search across uploads, tasks, jobs. Coming in Phase 2."
      }
    />
  );
}
