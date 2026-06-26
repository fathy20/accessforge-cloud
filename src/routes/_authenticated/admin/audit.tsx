import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export const Route = createFileRoute("/_authenticated/admin/audit")({
  head: () => ({ meta: [{ title: "Audit Log · REDSEA Admin" }] }),
  component: AuditLog,
});

function AuditLog() {
  const { data, isLoading } = useQuery({
    queryKey: ["audit-log"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("audit_log")
        .select("*")
        .order("ts", { ascending: false })
        .limit(200);
      if (error) throw error;
      return data;
    },
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Audit Log</h1>
        <p className="text-sm text-muted-foreground">Recent sensitive actions across the system.</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Latest 200 events</CardTitle></CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : data && data.length > 0 ? (
            <div className="text-sm divide-y divide-border">
              {data.map((e) => (
                <div key={e.id} className="py-2 flex items-center gap-3">
                  <Badge variant="outline">{e.action}</Badge>
                  <span className="text-muted-foreground">{e.entity}</span>
                  <span className="text-xs text-muted-foreground ml-auto">
                    {new Date(e.ts).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No audit events yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
