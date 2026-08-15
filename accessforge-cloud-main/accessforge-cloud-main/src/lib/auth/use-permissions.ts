import { useQuery } from "@tanstack/react-query";
import { ApiClient } from "@/lib/apiClient";
import type { ModuleRegistryItem } from "@/lib/modules/registry";
import { useAuth } from "./use-auth";

export type AppRole = "super_admin" | "admin" | "engineer" | "viewer" | "guest";

export interface PermissionSet {
  roles: AppRole[];
  moduleKeys: { view: string[]; run: string[] };
  modules: ModuleRegistryItem[];
  isAdmin: boolean;
  isSuperAdmin: boolean;
  hasRole: (r: AppRole) => boolean;
  hasAnyRole: (rs: AppRole[]) => boolean;
  canViewModule: (key: string) => boolean;
  canRunModule: (key: string) => boolean;
  canRunModuleAction: (moduleKey: string, actionKey: string) => boolean;
  loading: boolean;
}

export function usePermissions(): PermissionSet {
  const { user, loading: authLoading } = useAuth();

  const { data: modulesData, isLoading } = useQuery({
    queryKey: ["permissions", user?.id],
    enabled: !!user?.id,
    queryFn: async () => {
      return (await ApiClient.fetch<ModuleRegistryItem[]>("/modules")) ?? [];
    },
  });

  const roles = (user?.roles ?? []) as AppRole[];
  const isAdmin = roles.includes("admin") || roles.includes("super_admin");
  const isSuperAdmin = roles.includes("super_admin");

  // `action_permissions` is declared; `granted_action_permissions` is user-filtered.
  const modules = (modulesData ?? []).map((mod) => ({
    ...mod,
    granted_action_permissions: mod.granted_action_permissions ?? [],
  }));
  const view = modules.map((mod) => mod.key);
  const run = modules
    .filter((mod) => mod.granted_action_permissions.length > 0)
    .map((mod) => mod.key);
  const viewSet = new Set(view);
  const modulesByKey = new Map(modules.map((mod) => [mod.key, mod]));

  const canRunModule = (key: string) => {
    const module = modulesByKey.get(key);
    if (!module || !viewSet.has(key)) return false;

    return module.action_permissions.length === 0 || module.granted_action_permissions.length > 0;
  };

  return {
    roles,
    moduleKeys: { view, run },
    modules,
    isAdmin,
    isSuperAdmin,
    hasRole: (r) => roles.includes(r),
    hasAnyRole: (rs) => rs.some((r) => roles.includes(r)),
    canViewModule: (key) => viewSet.has(key),
    canRunModule,
    canRunModuleAction: (moduleKey, actionKey) =>
      modulesByKey.get(moduleKey)?.granted_action_permissions.includes(actionKey) ?? false,
    loading: authLoading || isLoading,
  };
}
