import type { ModuleReadiness } from "@/lib/modules/registry";

/**
 * Presentation ramp for module readiness.
 *
 * `token` names a CSS custom property rather than a literal so the value
 * follows the theme; `progress` is how complete that state is, drawn as the
 * card's progress bar.
 *
 * The registry declares seven readiness values but the design brief names five.
 * `pilot` and `requires_configuration` are mapped onto the nearest brief state
 * rather than left to fall through to grey, which would have read as
 * "not migrated" and understated them.
 */
export const READINESS_PRESENTATION: Record<
  ModuleReadiness,
  { token: string; progress: number }
> = {
  available: { token: "--ready-available", progress: 100 },
  under_validation: { token: "--ready-validation", progress: 75 },
  pilot: { token: "--ready-validation", progress: 60 },
  under_development: { token: "--ready-development", progress: 45 },
  requires_configuration: { token: "--ready-discovery", progress: 30 },
  discovery_required: { token: "--ready-discovery", progress: 15 },
  not_migrated: { token: "--ready-none", progress: 0 },
};

export function readinessColor(readiness: ModuleReadiness) {
  return `var(${READINESS_PRESENTATION[readiness]?.token ?? "--ready-none"})`;
}

export function readinessProgress(readiness: ModuleReadiness) {
  return READINESS_PRESENTATION[readiness]?.progress ?? 0;
}

/**
 * Two-letter monogram for the icon tile. Uses the module key rather than the
 * display name so it stays stable in both Arabic and English — a name-derived
 * monogram would render Arabic letters in a Latin display face.
 */
export function moduleMonogram(key: string) {
  const parts = key.split(/[_\-\s]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.slice(0, 2) ?? "??").toUpperCase();
}
