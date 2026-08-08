import type { DictKey } from "@/lib/i18n";
import type { CrewHoursReport, ReportTabDefinition, ReportTabPosition } from "./types";

type Translate = (key: DictKey, params?: Record<string, string | number>) => string;

export function reportTabLabel(tab: ReportTabDefinition, t: Translate): string {
  if (tab.position === "Cockpit") {
    return tab.summary
      ? t("crew.tabs.cockpit_summary")
      : t("crew.tabs.cockpit");
  }
  return tab.summary
    ? t("crew.tabs.cabin_summary")
    : t("crew.tabs.cabin");
}

export function outsideTabCrewMessage(
  report: CrewHoursReport,
  activePosition: ReportTabPosition,
  t: Translate,
): string | null {
  const outsideCrew = report.crew_members.filter((crew) => crew.position_type !== activePosition);
  if (outsideCrew.length === 0) {
    return null;
  }

  const maintenanceCount = outsideCrew.filter(
    (crew) => crew.position_type === "Maintenance",
  ).length;
  const unclassifiedCount = outsideCrew.filter((crew) => crew.position_type == null).length;
  const otherPosition: ReportTabPosition = activePosition === "Cockpit" ? "Cabin" : "Cockpit";
  const otherPositionCount = outsideCrew.filter(
    (crew) => crew.position_type === otherPosition,
  ).length;
  const otherCount = outsideCrew.length - maintenanceCount - unclassifiedCount - otherPositionCount;
  const englishParts = [
    maintenanceCount > 0 ? `${maintenanceCount} Maintenance` : null,
    unclassifiedCount > 0 ? `${unclassifiedCount} unclassified` : null,
    otherPositionCount > 0 ? `${otherPositionCount} ${otherPosition}` : null,
    otherCount > 0 ? `${otherCount} other` : null,
  ].filter((part): part is string => part !== null);
  const arabicParts = [
    maintenanceCount > 0 ? `${maintenanceCount} من الصيانة` : null,
    unclassifiedCount > 0 ? `${unclassifiedCount} غير مصنف` : null,
    otherPositionCount > 0
      ? `${otherPositionCount} ${otherPosition === "Cockpit" ? "من قمرة القيادة" : "من الضيافة"}`
      : null,
    otherCount > 0 ? `${otherCount} أخرى` : null,
  ].filter((part): part is string => part !== null);

  return t("crew.outside_tab_crew_message", {
    arabicParts: arabicParts.join(" و"),
    englishParts: englishParts.join(" and "),
  });
}
