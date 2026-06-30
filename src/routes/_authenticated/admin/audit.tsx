import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ShieldCheck } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

export const Route = createFileRoute("/_authenticated/admin/audit")({
  head: () => ({ meta: [{ title: "Audit Log · REDSEA Admin" }] }),
  component: AuditLog,
});

function AuditLog() {
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log"],
    queryFn: async () => {
      const [{ data: events, error }, { data: profiles }] = await Promise.all([
        supabase.from("audit_log").select("*").order("ts", { ascending: false }).limit(500),
        supabase.from("profiles").select("id, full_name"),
      ]);
      if (error) throw error;
      const nameById = new Map((profiles ?? []).map((p) => [p.id, p.full_name ?? ""]));
      return (events ?? []).map((e) => ({ ...e, actor_name: e.actor_id ? nameById.get(e.actor_id) ?? "" : "" }));
    },
  });

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return data ?? [];
    return (data ?? []).filter((e) =>
      [e.action, e.entity, e.entity_id, e.actor_name].some((v) => (v ?? "").toString().toLowerCase().includes(term))
    );
  }, [data, q]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <ShieldCheck className="size-5 text-primary" /> Audit Log
          </h1>
          <p className="text-sm text-muted-foreground">Recent sensitive actions across the system.</p>
        </div>
        <div className="relative w-72">
          <Search className="size-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Filter by action, entity, user…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" />
        </div>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Events ({filtered.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground text-center">No audit events.</p>
          ) : (
            <div className="text-sm divide-y divide-border">
              {filtered.map((e) => (
                <div key={e.id} className="px-4 py-2.5 flex items-center gap-3 flex-wrap">
                  <Badge variant="outline" className="font-mono text-[11px]">{e.action}</Badge>
                  {e.entity && <span className="text-muted-foreground text-xs font-mono">{e.entity}</span>}
                  {e.entity_id && <span className="text-muted-foreground text-xs font-mono">{String(e.entity_id).slice(0, 8)}</span>}
                  {e.actor_name && <span className="text-xs">by <span className="font-medium">{e.actor_name}</span></span>}
                  <span className="text-xs text-muted-foreground ml-auto">{new Date(e.ts).toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
