import { useQuery } from "@tanstack/react-query";
import { ApiClient } from "@/lib/apiClient";
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

  const { data: modulesData, isLoading } = useQuery({
    queryKey: ["permissions", user?.id],
    enabled: !!user?.id,
    queryFn: async () => {
      const mods = await ApiClient.fetch("/modules");
      return mods;
    },
  });

  const roles = (user?.roles ?? []) as AppRole[];
  const isAdmin = roles.includes("admin") || roles.includes("super_admin");
  const isSuperAdmin = roles.includes("super_admin");
  
  const view: string[] = [];
  const run: string[] = [];
  
  for (const mod of modulesData ?? []) {
    if (!mod.enabled) continue;
    view.push(mod.key);
    run.push(mod.key); // For now, if enabled, give run access since we simplify locally
  }

  return {
    roles,
    moduleKeys: { view, run },
    isAdmin,
    isSuperAdmin,
    hasRole: (r) => roles.includes(r),
    hasAnyRole: (rs) => rs.some((r) => roles.includes(r)),
    canViewModule: (key) => isAdmin || view.includes(key),
    canRunModule: (key) => isAdmin || run.includes(key),
    loading: authLoading || isLoading,
  };
}
