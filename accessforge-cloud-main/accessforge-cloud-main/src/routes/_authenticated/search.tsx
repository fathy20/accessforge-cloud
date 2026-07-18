import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search as SearchIcon, FileText, ListTodo, Loader2 } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const searchSchema = z.object({ q: z.string().optional() });

export const Route = createFileRoute("/_authenticated/search")({
  head: () => ({ meta: [{ title: "Search · REDSEA" }] }),
  validateSearch: searchSchema,
  component: SearchPage,
});

interface Hit {
  source: string;
  id: string;
  title: string;
  subtitle: string | null;
  project_id: string | null;
  created_at: string;
  rank: number;
}

function SearchPage() {
  const { q: initialQ } = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { lang } = useI18n();
  const ar = lang === "ar";
  const [q, setQ] = useState(initialQ ?? "");
  const [debounced, setDebounced] = useState(q);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    navigate({ search: debounced ? { q: debounced } : {}, replace: true });
  }, [debounced, navigate]);

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: async () => {
      if (!debounced) return [] as Hit[];
      try {
        const hits = await ApiClient.fetch(`/search?q=${encodeURIComponent(debounced)}&limit=80`);
        return (hits ?? []) as Hit[];
      } catch {
        return [] as Hit[];
      }
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{ar ? "البحث الشامل" : "Global Search"}</h1>
        <p className="text-sm text-muted-foreground">
          {ar ? "بحث نصي كامل عبر الملفات والمهام." : "Full-text + fuzzy search across uploads and tasks."}
        </p>
      </div>

      <div className="relative">
        <SearchIcon className="absolute start-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
        <Input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={ar ? "ابحث عن task code, file name, chapter…" : "Search task code, file name, chapter…"}
          className="ps-9 h-11 text-base"
        />
      </div>

      <Card>
        <CardContent className="p-0">
          {!debounced ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              {ar ? "اكتب للبدء بالبحث." : "Start typing to search."}
            </div>
          ) : isFetching ? (
            <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
          ) : !data?.length ? (
            <div className="p-10 text-center text-sm text-muted-foreground">
              {ar ? "لا توجد نتائج." : "No results."}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {data.map((h) => (
                <div key={`${h.source}-${h.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/30">
                  {h.source === "upload" ? (
                    <FileText className="size-5 text-muted-foreground shrink-0" />
                  ) : (
                    <ListTodo className="size-5 text-muted-foreground shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{h.title}</p>
                    {h.subtitle && <p className="text-xs text-muted-foreground truncate">{h.subtitle}</p>}
                  </div>
                  <Badge variant="secondary" className="text-[10px] uppercase">{h.source}</Badge>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {new Date(h.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
