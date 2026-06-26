import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

export const Route = createFileRoute("/_authenticated/admin/settings")({
  head: () => ({ meta: [{ title: "Settings · REDSEA Admin" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const { data: modules } = useQuery({
    queryKey: ["admin-modules"],
    queryFn: async () => {
      const { data, error } = await supabase.from("modules").select("*").order("sort_order");
      if (error) throw error;
      return data;
    },
  });

  const toggle = async (id: string, enabled: boolean) => {
    await supabase.from("modules").update({ enabled }).eq("id", id);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">System Settings</h1>
        <p className="text-sm text-muted-foreground">Enable / disable modules across the platform.</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Modules</CardTitle></CardHeader>
        <CardContent className="divide-y divide-border">
          {modules?.map((m) => (
            <div key={m.id} className="flex items-center justify-between py-3">
              <div>
                <p className="font-medium">{m.name}</p>
                <p className="text-xs text-muted-foreground">{m.description}</p>
              </div>
              <Switch
                defaultChecked={m.enabled}
                onCheckedChange={(v) => toggle(m.id, Boolean(v))}
              />
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
