import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "./use-auth";

export type AppRole = "super_admin" | "admin" | "engineer" | "viewer" | "guest";

export interface PermissionSet {
  roles: AppRole[];
  moduleKeys: { view: string[]; run: string[] };
  isAdmin: boolean;
  isSuperAdmin: boolean;
  hasRole: (r: AppRole) => boolean;
  hasAnyRole: (rs: AppRole[]) => boolean;
  canViewModule: (key: string) => boolean;
  canRunModule: (key: string) => boolean;
  loading: boolean;
}

export function usePermissions(): PermissionSet {
  const { user, loading: authLoading } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["permissions", user?.id],
    enabled: !!user?.id,
    queryFn: async () => {
      const [rolesRes, accessRes] = await Promise.all([
        supabase.from("user_roles").select("role").eq("user_id", user!.id),
        supabase
          .from("module_access")
          .select("can_view, can_run, modules!inner(key, enabled)")
          .eq("user_id", user!.id),
      ]);
      const roles = (rolesRes.data ?? []).map((r) => r.role as AppRole);
      const view: string[] = [];
      const run: string[] = [];
      for (const row of accessRes.data ?? []) {
        const mod = (row as { modules: { key: string; enabled: boolean } }).modules;
        if (!mod?.enabled) continue;
        if (row.can_view) view.push(mod.key);
        if (row.can_run) run.push(mod.key);
      }
      return { roles, view, run };
    },
  });

  const roles = data?.roles ?? [];
  const isAdmin = roles.includes("admin") || roles.includes("super_admin");
  const isSuperAdmin = roles.includes("super_admin");

  return {
    roles,
    moduleKeys: { view: data?.view ?? [], run: data?.run ?? [] },
    isAdmin,
    isSuperAdmin,
    hasRole: (r) => roles.includes(r),
    hasAnyRole: (rs) => rs.some((r) => roles.includes(r)),
    canViewModule: (key) => isAdmin || (data?.view ?? []).includes(key),
    canRunModule: (key) => isAdmin || (data?.run ?? []).includes(key),
    loading: authLoading || isLoading,
  };
}
