import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiClient } from "@/lib/apiClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

export const Route = createFileRoute("/_authenticated/admin/settings")({
  head: () => ({ meta: [{ title: "Settings · REDSEA Admin" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const { data: modules = [] as any[] } = useQuery({
    queryKey: ["admin-modules"],
    queryFn: async () => {
      return await ApiClient.fetch("/admin/modules");
    },
  });

  const toggle = async (id: string, enabled: boolean) => {
    await ApiClient.fetch(`/admin/modules/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
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
          {modules?.map((m: any) => (
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
