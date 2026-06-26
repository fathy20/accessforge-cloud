import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Users2 } from "lucide-react";

export const Route = createFileRoute("/_authenticated/admin/users")({
  head: () => ({ meta: [{ title: "Users & Roles · REDSEA Admin" }] }),
  component: UsersAdmin,
});

const ROLES = ["super_admin", "admin", "engineer", "viewer", "guest"] as const;
type AppRole = (typeof ROLES)[number];

function UsersAdmin() {
  const qc = useQueryClient();

  const { data: rows, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: async () => {
      const [profiles, roles, modules, access] = await Promise.all([
        supabase.from("profiles").select("id, full_name, department, job_title, created_at"),
        supabase.from("user_roles").select("user_id, role"),
        supabase.from("modules").select("id, key, name").order("sort_order"),
        supabase.from("module_access").select("user_id, module_id, can_view, can_run"),
      ]);
      if (profiles.error) throw profiles.error;
      const rolesByUser: Record<string, AppRole[]> = {};
      for (const r of roles.data ?? []) {
        (rolesByUser[r.user_id] ||= []).push(r.role as AppRole);
      }
      const accessByUser: Record<string, Record<string, { v: boolean; r: boolean }>> = {};
      for (const a of access.data ?? []) {
        (accessByUser[a.user_id] ||= {})[a.module_id] = { v: a.can_view, r: a.can_run };
      }
      return {
        users: (profiles.data ?? []).map((p) => ({
          ...p,
          roles: rolesByUser[p.id] ?? [],
          access: accessByUser[p.id] ?? {},
        })),
        modules: modules.data ?? [],
      };
    },
  });

  const setRole = useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: AppRole }) => {
      // remove all existing then insert chosen role (single-role model per user)
      const del = await supabase.from("user_roles").delete().eq("user_id", userId);
      if (del.error) throw del.error;
      const ins = await supabase.from("user_roles").insert({ user_id: userId, role });
      if (ins.error) throw ins.error;
    },
    onSuccess: () => {
      toast.success("Role updated");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const toggleAccess = useMutation({
    mutationFn: async ({
      userId,
      moduleId,
      field,
      value,
      current,
    }: {
      userId: string;
      moduleId: string;
      field: "can_view" | "can_run";
      value: boolean;
      current: { v: boolean; r: boolean } | undefined;
    }) => {
      const can_view = field === "can_view" ? value : current?.v ?? true;
      const can_run = field === "can_run" ? value : current?.r ?? false;
      const { error } = await supabase
        .from("module_access")
        .upsert(
          { user_id: userId, module_id: moduleId, can_view, can_run },
          { onConflict: "user_id,module_id" },
        );
      if (error) throw error;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Users2 className="size-6 text-primary" />
        <div>
          <h1 className="text-2xl font-bold">Users &amp; Roles</h1>
          <p className="text-sm text-muted-foreground">
            Assign a role and per-module access for each user.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="space-y-4">
          {rows?.users.map((u) => (
            <Card key={u.id}>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                  <div>
                    <CardTitle className="text-base">{u.full_name ?? "Unnamed user"}</CardTitle>
                    <p className="text-xs text-muted-foreground font-mono">{u.id}</p>
                    <div className="flex gap-1.5 mt-1.5">
                      {u.roles.length === 0 ? (
                        <Badge variant="outline">no role</Badge>
                      ) : (
                        u.roles.map((r) => (
                          <Badge key={r} variant="secondary" className="capitalize">
                            {r.replace("_", " ")}
                          </Badge>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Role:</span>
                    <Select
                      value={u.roles[0] ?? ""}
                      onValueChange={(v) =>
                        setRole.mutate({ userId: u.id, role: v as AppRole })
                      }
                    >
                      <SelectTrigger className="w-40">
                        <SelectValue placeholder="Select role" />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLES.map((r) => (
                          <SelectItem key={r} value={r} className="capitalize">
                            {r.replace("_", " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
                  {rows.modules.map((m) => {
                    const cur = u.access[m.id];
                    return (
                      <div
                        key={m.id}
                        className="rounded-lg border border-border p-3 flex flex-col gap-2"
                      >
                        <p className="text-sm font-medium truncate">{m.name}</p>
                        <div className="flex gap-4 text-xs">
                          <label className="flex items-center gap-1.5">
                            <Checkbox
                              checked={cur?.v ?? false}
                              onCheckedChange={(v) =>
                                toggleAccess.mutate({
                                  userId: u.id,
                                  moduleId: m.id,
                                  field: "can_view",
                                  value: Boolean(v),
                                  current: cur,
                                })
                              }
                            />
                            View
                          </label>
                          <label className="flex items-center gap-1.5">
                            <Checkbox
                              checked={cur?.r ?? false}
                              onCheckedChange={(v) =>
                                toggleAccess.mutate({
                                  userId: u.id,
                                  moduleId: m.id,
                                  field: "can_run",
                                  value: Boolean(v),
                                  current: cur,
                                })
                              }
                            />
                            Run
                          </label>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          ))}
          {rows?.users.length === 0 && (
            <Card>
              <CardContent className="p-6 text-sm text-muted-foreground">
                No users yet. The first signup will appear here.
              </CardContent>
            </Card>
          )}
        </div>
      )}
      <Button variant="outline" onClick={() => qc.invalidateQueries({ queryKey: ["admin-users"] })}>
        Refresh
      </Button>
    </div>
  );
}
