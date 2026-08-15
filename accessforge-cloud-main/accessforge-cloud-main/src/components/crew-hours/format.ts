import type { CrewHoursReport, OfficialPosition } from "./types";

export function displayValue(value?: string | null): string {
  return typeof value === "string" && value.trim().length > 0 ? value : "—";
}

export function displayUtcTime(value?: string | null): string {
  return displayValue(value?.replace("T", " ").replace("Z", ""));
}

export function displayAircraft(registration?: string | null, aircraftType?: string | null): string {
  const displayedRegistration = displayValue(registration);
  const displayedType = displayValue(aircraftType);
  if (displayedRegistration === "—" && displayedType === "—") {
    return "—";
  }
  return `${displayedRegistration} (${displayedType})`;
}

export function crewInitials(displayName?: string | null): string {
  const initials =
    displayName
      ?.trim()
      .split(/\s+/)
      .map((part) => part.charAt(0))
      .join("")
      .slice(0, 2) ?? "";
  return initials || "—";
}

export function displayOfficialHours(report: CrewHoursReport, position: OfficialPosition): string {
  return report.official_totals_by_position?.[position] ?? "—";
}

export function formatLastLoadedAt(value: Date, ar: boolean): string {
  return value.toLocaleString(ar === true ? "ar-EG" : undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
