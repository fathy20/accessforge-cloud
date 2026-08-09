import { dict, type DictKey, type Translate } from "@/lib/i18n";

export const MODULE_READINESS_VALUES = [
  "available",
  "pilot",
  "under_validation",
  "requires_configuration",
  "under_development",
  "not_migrated",
  "discovery_required",
] as const;

export type ModuleReadiness = (typeof MODULE_READINESS_VALUES)[number];

export const MODULE_READINESS_STATUS_FAMILIES = [
  "success",
  "info",
  "warning",
  "neutral",
] as const;

export type ModuleReadinessStatusFamily =
  (typeof MODULE_READINESS_STATUS_FAMILIES)[number];

export const READINESS_STATUS_FAMILY_BY_VALUE = {
  available: "success",
  pilot: "info",
  under_validation: "info",
  requires_configuration: "warning",
  under_development: "warning",
  not_migrated: "neutral",
  discovery_required: "neutral",
} as const satisfies Partial<Record<ModuleReadiness, ModuleReadinessStatusFamily>>;

export function getReadinessStatusFamily(
  readiness: ModuleReadiness,
): ModuleReadinessStatusFamily {
  const statusMap = READINESS_STATUS_FAMILY_BY_VALUE as Partial<
    Record<ModuleReadiness, ModuleReadinessStatusFamily>
  >;
  return statusMap[readiness] ?? "neutral";
}

export const MODULE_BUSINESS_AREAS = ["crew", "maintenance", "stores", "admin"] as const;

export type ModuleBusinessArea = (typeof MODULE_BUSINESS_AREAS)[number];

export interface ModuleRegistryItem {
  key: string;
  name: string;
  description: string | null;
  icon: string | null;
  category: string | null;
  enabled: boolean;
  sort_order: number;
  business_area: ModuleBusinessArea;
  route: string | null;
  module_status: string;
  required_view_permission: string | null;
  display_name_key: string | null;
  action_permissions: string[];
  granted_action_permissions: string[];
  readiness: ModuleReadiness;
}

export function sortModules(modules: ModuleRegistryItem[]): ModuleRegistryItem[] {
  return [...modules].sort(
    (a, b) => a.sort_order - b.sort_order || a.key.localeCompare(b.key),
  );
}

export function getModuleLabel(module: ModuleRegistryItem, t: Translate): string {
  const key = `mod.${module.key}`;
  return Object.prototype.hasOwnProperty.call(dict, key)
    ? t(key as DictKey)
    : module.name;
}

export function getReadinessLabel(module: ModuleRegistryItem, t: Translate): string {
  return t(`mod.readiness.${module.readiness}` as DictKey);
}

export function getBusinessAreaLabel(area: ModuleBusinessArea, t: Translate): string {
  return t(`mod.area.${area}` as DictKey);
}
