import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, ShieldCheck, Download } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/_authenticated/admin/audit")({
  head: () => ({ meta: [{ title: "Audit Log · REDSEA Admin" }] }),
  component: AuditLog,
});

function AuditLog() {
  const [q, setQ] = useState("");

  const { data = [] as any[], isLoading } = useQuery({
    queryKey: ["audit-log"],
    queryFn: async () => {
      return await ApiClient.fetch("/admin/audit-log");
    },
  });

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return data;
    return data.filter((e: any) =>
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
        <div className="flex items-center gap-2">
          <div className="relative w-72">
            <Search className="size-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Filter by action, entity, user…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" />
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const rows = [["ts", "action", "entity", "entity_id", "actor"], ...filtered.map((e: any) => [
                e.ts, e.action, e.entity ?? "", e.entity_id ?? "", e.actor_name ?? "",
              ])];
              const csv = rows.map((r) => r.map((c: any) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
              const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
              const a = document.createElement("a");
              a.href = url; a.download = `audit-${Date.now()}.csv`; a.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download className="size-4" /> Export CSV
          </Button>
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
              {filtered.map((e: any) => (
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
