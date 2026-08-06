import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  Users,
  Calendar,
  Filter,
  Search,
  RefreshCw,
  FileSpreadsheet,
  AlertCircle,
  Plane,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/_authenticated/modules/crew-hours")({
  head: () => ({ meta: [{ title: "Crew Hours (LEON) · REDSEA" }] }),
  component: CrewHoursPage,
});

interface FlightItem {
  flight_nid: string;
  flight_number: string | null;
  departure_airport: string | null;
  arrival_airport: string | null;
  start_time_utc: string | null;
  end_time_utc: string | null;
  aircraft_reg: string | null;
  aircraft_type: string | null;
  flight_date: string | null;
  block_time: string | null;
  position: string | null;
  flight_training_type: string | null;
  is_trn: boolean;
  journey_log?: unknown;
}

interface CrewMemberSummary {
  crew_id: string;
  person_code?: string;
  display_name: string;
  full_name: string | null;
  position_type?: string | null;
  position_name?: string;
  status: string;
  official_total: string | null;
  raw_official_total: string | null;
  reference_total: string | null;
  variance_minutes: number | null;
  flight_count: number;
  flights: FlightItem[];
}

interface CrewHoursReport {
  period: { from: string; to: string };
  source: string;
  hours_source_status: string;
  total_crew: number;
  total_flights: number;
  records_count: number;
  official_totals_available: number;
  official_totals_unavailable: number;
  official_totals_by_position: Partial<Record<OfficialPosition, string>>;
  crew_members: CrewMemberSummary[];
}

const OFFICIAL_MCP_SOURCE = "official_mcp_report";
const POSITIONING_TOKENS = ["PAD", "PSN", "FDP", "FDPI", "RMP", "INSP"] as const;
const ALL_AIRCRAFT = "__all_aircraft__";
const ALL_POSITION_TOKENS = "All";
const ACTIVE_POSITION_TOKEN = "Active";

type OfficialPosition = "Cockpit" | "Cabin" | "Maintenance" | "Unclassified";
type PositioningToken = (typeof POSITIONING_TOKENS)[number];
type PositionTokenFilter =
  | typeof ALL_POSITION_TOKENS
  | typeof ACTIVE_POSITION_TOKEN
  | PositioningToken;
type ReportTab = "cockpit" | "cockpit-summary" | "cabin" | "cabin-summary";
type ReportTabPosition = Extract<OfficialPosition, "Cockpit" | "Cabin">;

interface ReportTabDefinition {
  value: ReportTab;
  position: ReportTabPosition;
  summary: boolean;
}

const REPORT_TABS: ReportTabDefinition[] = [
  { value: "cockpit", position: "Cockpit", summary: false },
  { value: "cockpit-summary", position: "Cockpit", summary: true },
  { value: "cabin", position: "Cabin", summary: false },
  { value: "cabin-summary", position: "Cabin", summary: true },
];

function hasOfficialTotal(crew: CrewMemberSummary): boolean {
  return typeof crew.official_total === "string" && crew.official_total.trim().length > 0;
}

function displayValue(value?: string | null): string {
  return typeof value === "string" && value.trim().length > 0 ? value : "—";
}

function displayUtcTime(value?: string | null): string {
  return displayValue(value?.replace("T", " ").replace("Z", ""));
}

function displayAircraft(registration?: string | null, aircraftType?: string | null): string {
  const displayedRegistration = displayValue(registration);
  const displayedType = displayValue(aircraftType);
  if (displayedRegistration === "—" && displayedType === "—") {
    return "—";
  }
  return `${displayedRegistration} (${displayedType})`;
}

function crewInitials(displayName?: string | null): string {
  const initials =
    displayName
      ?.trim()
      .split(/\s+/)
      .map((part) => part.charAt(0))
      .join("")
      .slice(0, 2) ?? "";
  return initials || "—";
}

function displayOfficialHours(report: CrewHoursReport, position: OfficialPosition): string {
  return report.official_totals_by_position?.[position] ?? "—";
}

function isPositioningToken(position: string | null): position is PositioningToken {
  return typeof position === "string" && POSITIONING_TOKENS.includes(position as PositioningToken);
}

function reportTabLabel(tab: ReportTabDefinition, ar: boolean): string {
  if (tab.position === "Cockpit") {
    return tab.summary
      ? ar
        ? "ملخص قمرة القيادة (Cockpit Summary)"
        : "Cockpit Summary"
      : ar
        ? "قمرة القيادة (Cockpit)"
        : "Cockpit";
  }
  return tab.summary
    ? ar
      ? "ملخص الضيافة (Cabin Summary)"
      : "Cabin Summary"
    : ar
      ? "الضيافة (Cabin)"
      : "Cabin";
}

function reportTabPosition(tab: ReportTab): ReportTabPosition {
  return tab.startsWith("cockpit") ? "Cockpit" : "Cabin";
}

function hasOfficialMcpTotal(report: CrewHoursReport, crew: CrewMemberSummary): boolean {
  return report.hours_source_status === OFFICIAL_MCP_SOURCE && hasOfficialTotal(crew);
}

function OfficialMcpBadge({ ar }: { ar: boolean }) {
  return (
    <Badge
      variant="outline"
      className="gap-1.5 border-success/30 bg-success/10 text-success"
      aria-label={ar ? "LEON MCP الرسمي" : "Official LEON MCP"}
    >
      <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
      {ar ? "LEON MCP الرسمي" : "Official LEON MCP"}
    </Badge>
  );
}

function PositionTokenBadge({ position, ar }: { position: string | null; ar: boolean }) {
  const token = displayValue(position);
  if (token === "—") {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const isPositioning = isPositioningToken(position);
  const badge = (
    <Badge
      variant={isPositioning ? "outline" : "secondary"}
      className={`px-1.5 py-0 text-[10px] font-mono ${
        isPositioning
          ? "border-warning/40 bg-warning/15 text-warning-foreground"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {token}
    </Badge>
  );

  if (!isPositioning) {
    return badge;
  }

  const positioningCue = ar ? "تموضع · غير نشطة" : "Positioning · Not Active";
  const positioningDescription = ar
    ? "تموضع · غير نشطة · مشمولة في الإجمالي الرسمي."
    : "Positioning · Not Active · Included in official total.";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          tabIndex={0}
          className="inline-flex items-center gap-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={positioningDescription}
        >
          {badge}
          <span className="text-[10px] font-medium text-warning-foreground">{positioningCue}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p className="text-xs">{positioningDescription}</p>
      </TooltipContent>
    </Tooltip>
  );
}

function outsideTabCrewMessage(
  report: CrewHoursReport,
  activePosition: ReportTabPosition,
  ar: boolean,
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

  return ar
    ? `${arabicParts.join(" و")} من أفراد الطاقم خارج هذا التبويب غير معروضين.`
    : `${englishParts.join(" and ")} crew members are not shown in this tab.`;
}

interface CrewGroupHeaderProps {
  report: CrewHoursReport;
  crew: CrewMemberSummary;
  visibleFlightCount: number;
  hasClientSideDisplayFilter: boolean;
  isTrnActive: boolean;
  isExpanded: boolean;
  ar: boolean;
  onToggle: () => void;
  onToggleTrn: () => void;
}

function CrewGroupHeader({
  report,
  crew,
  visibleFlightCount,
  hasClientSideDisplayFilter,
  isTrnActive,
  isExpanded,
  ar,
  onToggle,
  onToggleTrn,
}: CrewGroupHeaderProps) {
  const flightCountLabel = hasClientSideDisplayFilter
    ? ar
      ? `${visibleFlightCount} من ${crew.flight_count} رحلة`
      : `${visibleFlightCount} of ${crew.flight_count} flights`
    : ar
      ? `${crew.flight_count} رحلة`
      : `${crew.flight_count} flights`;

  return (
    <tr className="border-t-8 border-background bg-muted/30">
      <th colSpan={10} scope="rowgroup" className="p-2 text-left">
        <div className="flex min-w-[980px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            onClick={onToggle}
            aria-expanded={isExpanded}
            className="min-w-0 flex-1 justify-start rounded-lg px-2 py-2 text-left hover:bg-accent/60"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-bold text-primary">
              {crewInitials(crew.display_name)}
            </div>
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate font-semibold" title={crew.display_name}>
                  {crew.display_name}
                </span>
                {crew.person_code && crew.display_name !== crew.person_code && (
                  <Badge variant="secondary" className="text-xs">
                    {crew.person_code}
                  </Badge>
                )}
              </div>
              <span className="block text-xs font-normal text-muted-foreground">
                {displayValue(crew.position_type)} · {flightCountLabel}
              </span>
            </div>
          </Button>

          <div
            className="flex shrink-0 items-center gap-3"
            onClick={(event) => event.stopPropagation()}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant={isTrnActive ? "default" : "outline"}
                  size="sm"
                  onClick={onToggleTrn}
                  className={`h-8 gap-1.5 text-xs ${
                    isTrnActive ? "bg-warning text-warning-foreground hover:bg-warning/90" : ""
                  }`}
                  aria-label={
                    ar
                      ? `علامة TRN يدوية ومحلية: ${isTrnActive ? "تدريب" : "عادي"}`
                      : `Manual local TRN marker: ${isTrnActive ? "Training" : "Normal"}`
                  }
                >
                  <Badge
                    variant={isTrnActive ? "secondary" : "outline"}
                    className="px-1 py-0 text-[10px]"
                  >
                    TRN
                  </Badge>
                  {isTrnActive
                    ? ar
                      ? "يدوي · تدريب (TRN)"
                      : "Manual · Training (TRN)"
                    : ar
                      ? "يدوي · عادي"
                      : "Manual · Normal"}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p className="text-xs">
                  {ar
                    ? "هذه علامة TRN يدوية ومحلية، وليست من LEON ولا تؤثر على الإجمالي الرسمي."
                    : "This is a manual local TRN marker; it is not from LEON and does not affect the official total."}
                </p>
              </TooltipContent>
            </Tooltip>

            <div className="flex items-center gap-2 text-right text-xs">
              <div>
                <span className="block text-muted-foreground">
                  {ar ? "الإجمالي الرسمي" : "Official total"}
                </span>
                <span
                  className={`font-mono font-semibold ${
                    hasOfficialTotal(crew) ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {displayValue(crew.official_total)}
                </span>
              </div>
              {hasOfficialMcpTotal(report, crew) && <OfficialMcpBadge ar={ar} />}
            </div>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={onToggle}
              aria-expanded={isExpanded}
              aria-label={
                ar
                  ? isExpanded
                    ? "طي تفاصيل الطاقم"
                    : "توسيع تفاصيل الطاقم"
                  : isExpanded
                    ? "Collapse crew details"
                    : "Expand crew details"
              }
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" aria-hidden="true" />
              ) : (
                <ChevronDown className="h-4 w-4" aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
      </th>
    </tr>
  );
}

function CrewDetailFlightRow({
  crew,
  flight,
  ar,
}: {
  crew: CrewMemberSummary;
  flight: FlightItem;
  ar: boolean;
}) {
  return (
    <tr className="hover:bg-muted/10">
      <td className="whitespace-nowrap px-4 py-2.5 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span>{displayValue(crew.position_type)}</span>
          <PositionTokenBadge position={flight.position} ar={ar} />
        </div>
      </td>
      <td className="px-4 py-2.5" />
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayValue(flight.flight_date)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-xs">
        {displayAircraft(flight.aircraft_reg, flight.aircraft_type)}
      </td>
      <td
        className="whitespace-nowrap px-4 py-2.5 font-mono text-xs font-medium"
        title={flight.flight_nid}
      >
        {displayValue(flight.flight_number)}
      </td>
      <td className="px-4 py-2.5">
        <Badge variant="outline" className="font-mono">
          {displayValue(flight.departure_airport)}
        </Badge>
      </td>
      <td className="px-4 py-2.5">
        <Badge variant="outline" className="font-mono">
          {displayValue(flight.arrival_airport)}
        </Badge>
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayUtcTime(flight.start_time_utc)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayUtcTime(flight.end_time_utc)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayValue(flight.block_time)}
      </td>
    </tr>
  );
}

interface CrewDetailTableProps {
  report: CrewHoursReport;
  crews: CrewMemberSummary[];
  aircraftFilter: string;
  positionTokenFilter: PositionTokenFilter;
  hasClientSideDisplayFilter: boolean;
  expandedCrew: Record<string, boolean>;
  trnOverrides: Record<string, boolean>;
  ar: boolean;
  onToggleCrew: (crewId: string) => void;
  onToggleTrn: (crewId: string) => void;
}

function CrewDetailTable({
  report,
  crews,
  aircraftFilter,
  positionTokenFilter,
  hasClientSideDisplayFilter,
  expandedCrew,
  trnOverrides,
  ar,
  onToggleCrew,
  onToggleTrn,
}: CrewDetailTableProps) {
  const visibleCrews = crews.filter((crew) => {
    if (!hasClientSideDisplayFilter || crew.flights.length === 0) {
      return true;
    }

    return crew.flights.some((flight) =>
      matchesDisplayFilters(flight, aircraftFilter, positionTokenFilter),
    );
  });

  if (hasClientSideDisplayFilter && crews.length > 0 && visibleCrews.length === 0) {
    return (
      <div
        className="rounded-xl border border-border/80 bg-card p-8 text-center shadow-sm"
        role="status"
        aria-live="polite"
      >
        <p className="text-sm font-medium">
          {ar
            ? "لا توجد صفوف رحلات مطابقة لمرشحات العرض الحالية."
            : "No flight rows match the current display filters."}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          {ar
            ? "أعد ضبط مرشحات الطائرة ورمز الموقع لعرض جميع الصفوف."
            : "Reset the aircraft and position-token filters to show all rows."}
        </p>
      </div>
    );
  }

  return (
    <div className="w-full min-w-0 overflow-x-auto rounded-xl border border-border/80 bg-card shadow-sm">
      <table
        className="w-full min-w-[980px] border-collapse text-left text-sm"
        aria-label={ar ? "جدول تفاصيل الرحلات حسب الطاقم" : "Grouped crew flight detail table"}
      >
        <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="whitespace-nowrap px-4 py-3 font-medium">
              {ar ? "نوع الموقع (Position type)" : "Position type"}
            </th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">
              {ar ? "الاسم (Name)" : "Name"}
            </th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">
              {ar ? "التاريخ (Date)" : "Date"}
            </th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">
              {ar ? "الطائرة (Aircraft)" : "Aircraft"}
            </th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">
              {ar ? "رقم الرحلة (Flight #)" : "Flight #"}
            </th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">ADEP</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">ADES</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">OFF</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">ON</th>
            <th className="whitespace-nowrap px-4 py-3 font-medium">
              {ar ? "زمن البلوك (Block time)" : "Block time"}
            </th>
          </tr>
        </thead>
        {visibleCrews.map((crew) => {
          const visibleFlights = crew.flights.filter((flight) =>
            matchesDisplayFilters(flight, aircraftFilter, positionTokenFilter),
          );
          const isExpanded = expandedCrew[crew.crew_id] ?? true;
          const isTrnActive = trnOverrides[crew.crew_id] ?? false;

          return (
            <tbody key={crew.crew_id} className="divide-y divide-border">
              <CrewGroupHeader
                report={report}
                crew={crew}
                visibleFlightCount={visibleFlights.length}
                hasClientSideDisplayFilter={hasClientSideDisplayFilter}
                isTrnActive={isTrnActive}
                isExpanded={isExpanded}
                ar={ar}
                onToggle={() => onToggleCrew(crew.crew_id)}
                onToggleTrn={() => onToggleTrn(crew.crew_id)}
              />
              {isExpanded && (
                <>
                  {visibleFlights.map((flight, index) => (
                    <CrewDetailFlightRow
                      key={`${crew.crew_id}-${flight.flight_nid}-${index}`}
                      crew={crew}
                      flight={flight}
                      ar={ar}
                    />
                  ))}
                  <tr className="bg-muted/10 font-semibold">
                    <td colSpan={9} className="px-4 py-3 text-right">
                      {ar ? "الإجمالي" : "Total"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right font-mono">
                      {displayValue(crew.official_total)}
                    </td>
                  </tr>
                </>
              )}
            </tbody>
          );
        })}
        {crews.length === 0 && (
          <tbody>
            <tr>
              <td colSpan={10} className="px-4 py-10 text-center text-sm text-muted-foreground">
                {ar ? "لا يوجد أفراد طاقم في هذا التبويب." : "No crew members are in this tab."}
              </td>
            </tr>
          </tbody>
        )}
      </table>
    </div>
  );
}

function CrewSummaryTable({
  report,
  crews,
  position,
  ar,
}: {
  report: CrewHoursReport;
  crews: CrewMemberSummary[];
  position: ReportTabPosition;
  ar: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="w-full min-w-0 overflow-x-auto rounded-xl border border-border/80 bg-card shadow-sm">
        <table
          className="w-full min-w-[760px] border-collapse text-left text-sm"
          aria-label={ar ? "جدول ملخص الطاقم" : "Crew summary table"}
        >
          <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {ar ? "نوع الموقع (Position type)" : "Position type"}
              </th>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {ar ? "الاسم (Name)" : "Name"}
              </th>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {ar ? "كود الطاقم (Crew code)" : "Crew code"}
              </th>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {ar ? "الرحلات (Flights)" : "Flights"}
              </th>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {ar ? "الإجمالي الرسمي (Official total)" : "Official total"}
              </th>
              <th className="whitespace-nowrap px-4 py-3 font-medium">
                {ar ? "المصدر (Source)" : "Source"}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {crews.map((crew) => (
              <tr key={crew.crew_id} className="hover:bg-muted/10">
                <td className="whitespace-nowrap px-4 py-3 text-xs">
                  {displayValue(crew.position_type)}
                </td>
                <td className="px-4 py-3 font-medium">{displayValue(crew.display_name)}</td>
                <td className="px-4 py-3 font-mono text-xs">{displayValue(crew.person_code)}</td>
                <td className="px-4 py-3">{crew.flight_count}</td>
                <td className="whitespace-nowrap px-4 py-3 font-mono">
                  {displayValue(crew.official_total)}
                </td>
                <td className="px-4 py-3">
                  {hasOfficialMcpTotal(report, crew) ? (
                    <OfficialMcpBadge ar={ar} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
              </tr>
            ))}
            {crews.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">
                  {ar ? "لا يوجد أفراد طاقم في هذا التبويب." : "No crew members are in this tab."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-info/20 bg-info/5 px-3 py-2 text-xs text-muted-foreground">
        <span>
          {ar
            ? `إجمالي مجموعة ${position === "Cockpit" ? "قمرة القيادة" : "الضيافة"} المحسوب من الخادم:`
            : `Server-computed ${position} group total:`}
        </span>
        <span className="font-mono font-semibold text-foreground">
          {displayOfficialHours(report, position)}
        </span>
      </div>
    </div>
  );
}

function CrewReportTabPanel({
  report,
  tab,
  aircraftFilter,
  positionTokenFilter,
  hasClientSideDisplayFilter,
  expandedCrew,
  trnOverrides,
  ar,
  onToggleCrew,
  onToggleTrn,
}: {
  report: CrewHoursReport;
  tab: ReportTabDefinition;
  aircraftFilter: string;
  positionTokenFilter: PositionTokenFilter;
  hasClientSideDisplayFilter: boolean;
  expandedCrew: Record<string, boolean>;
  trnOverrides: Record<string, boolean>;
  ar: boolean;
  onToggleCrew: (crewId: string) => void;
  onToggleTrn: (crewId: string) => void;
}) {
  const crews = report.crew_members.filter((crew) => crew.position_type === tab.position);

  if (tab.summary) {
    return <CrewSummaryTable report={report} crews={crews} position={tab.position} ar={ar} />;
  }

  return (
    <CrewDetailTable
      report={report}
      crews={crews}
      aircraftFilter={aircraftFilter}
      positionTokenFilter={positionTokenFilter}
      hasClientSideDisplayFilter={hasClientSideDisplayFilter}
      expandedCrew={expandedCrew}
      trnOverrides={trnOverrides}
      ar={ar}
      onToggleCrew={onToggleCrew}
      onToggleTrn={onToggleTrn}
    />
  );
}

function matchesDisplayFilters(
  flight: FlightItem,
  aircraftFilter: string,
  positionTokenFilter: PositionTokenFilter,
): boolean {
  const matchesAircraft = aircraftFilter === ALL_AIRCRAFT || flight.aircraft_reg === aircraftFilter;
  const matchesPositionToken =
    positionTokenFilter === ALL_POSITION_TOKENS ||
    (positionTokenFilter === ACTIVE_POSITION_TOKEN
      ? !isPositioningToken(flight.position)
      : flight.position === positionTokenFilter);

  return matchesAircraft && matchesPositionToken;
}

function formatLastLoadedAt(value: Date, ar: boolean): string {
  return value.toLocaleString(ar ? "ar-EG" : undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function CrewHoursPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";

  const [fromDate, setFromDate] = useState("2026-06-01");
  const [toDate, setToDate] = useState("2026-06-30");
  const [position, setPosition] = useState("All");
  const [crewSearch, setCrewSearch] = useState("");
  const [aircraftFilter, setAircraftFilter] = useState(ALL_AIRCRAFT);
  const [positionTokenFilter, setPositionTokenFilter] =
    useState<PositionTokenFilter>(ALL_POSITION_TOKENS);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<CrewHoursReport | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const requestInFlightRef = useRef(false);

  // Interactive TRN override per crew member
  const [trnOverrides, setTrnOverrides] = useState<Record<string, boolean>>({});
  // Expanded crew cards
  const [expandedCrew, setExpandedCrew] = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab] = useState<ReportTab>("cockpit");

  const officialSourceAvailable = report?.hours_source_status === OFFICIAL_MCP_SOURCE;

  const fetchReport = async () => {
    if (requestInFlightRef.current) {
      return;
    }

    requestInFlightRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        from: fromDate,
        to: toDate,
        position: position,
      });
      if (crewSearch.trim()) {
        params.append("crew_member", crewSearch.trim());
      }

      const data = await ApiClient.fetch<CrewHoursReport>(
        `/statistics/crew-hours/report?${params.toString()}`,
      );
      const loadedAt = new Date();
      setReport(data);
      setLastLoadedAt(loadedAt);
      setAircraftFilter(ALL_AIRCRAFT);
      setPositionTokenFilter(ALL_POSITION_TOKENS);

      // Expand all crew members by default
      const exp: Record<string, boolean> = {};
      data.crew_members.forEach((c) => {
        exp[c.crew_id] = true;
      });
      setExpandedCrew(exp);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : ar
            ? "فشل تحميل تقرير ساعات الطاقم"
            : "Failed to load crew hours report",
      );
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, []);

  const toggleTrn = (crewId: string) => {
    setTrnOverrides((prev) => ({
      ...prev,
      [crewId]: !prev[crewId],
    }));
  };

  const toggleExpand = (crewId: string) => {
    setExpandedCrew((prev) => ({
      ...prev,
      [crewId]: !prev[crewId],
    }));
  };

  const aircraftOptions =
    report === null
      ? []
      : Array.from(
          new Set(
            report.crew_members.flatMap((crew) =>
              crew.flights
                .map((flight) => flight.aircraft_reg)
                .filter(
                  (registration): registration is string =>
                    typeof registration === "string" && registration.trim().length > 0,
                ),
            ),
          ),
        ).sort();

  const positionTokenOptions =
    report === null
      ? []
      : POSITIONING_TOKENS.filter((token) =>
          report.crew_members.some((crew) =>
            crew.flights.some((flight) => flight.position === token),
          ),
        );

  const unclassifiedRoles =
    report?.crew_members.filter((crew) => crew.position_type === null).length ?? 0;
  const hasClientSideDisplayFilter =
    aircraftFilter !== ALL_AIRCRAFT || positionTokenFilter !== ALL_POSITION_TOKENS;
  const activeTabOutsideMessage = report
    ? outsideTabCrewMessage(report, reportTabPosition(activeTab), ar)
    : null;

  return (
    <div className="container mx-auto space-y-6 p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col gap-5 border-b border-border/70 pb-5 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20">
            <Users className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">
              {ar ? "ساعات الطاقم" : "Crew Hours"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {ar ? "قطاع الإحصائيات · المرحلة الأولى" : "Statistics Sector · Phase 1"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          {report && !error && officialSourceAvailable && (
            <Badge
              variant="outline"
              className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            >
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
              {ar ? "LEON MCP الرسمي" : "Official LEON MCP"}
            </Badge>
          )}
          {lastLoadedAt && (
            <span className="text-xs text-muted-foreground">
              {ar ? "آخر تحميل" : "Last loaded"}: {formatLastLoadedAt(lastLoadedAt, ar)}
            </span>
          )}
        </div>
      </div>

      {/* Filter Toolbar */}
      <Card className="rounded-xl border-border/80 bg-card shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Filter className="h-4 w-4 text-primary" />
            {ar ? "تصفية التقرير" : "Report Filters"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "من" : "From"}</Label>
              <div className="relative">
                <Calendar className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="pl-8 text-sm"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "إلى" : "To"}</Label>
              <div className="relative">
                <Calendar className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="pl-8 text-sm"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "الموقع (Position)" : "Position"}</Label>
              <Select value={position} onValueChange={setPosition}>
                <SelectTrigger className="text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="All">{ar ? "الكل (All)" : "All Positions"}</SelectItem>
                  <SelectItem value="Cockpit">
                    {ar ? "قمرة القيادة (Cockpit)" : "Cockpit"}
                  </SelectItem>
                  <SelectItem value="Cabin">{ar ? "الضيافة (Cabin)" : "Cabin"}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">
                {ar ? "اسم / كود الطاقم" : "Crew Search"}
              </Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder={ar ? "ابحث باسم الطيار أو الكود..." : "Search name or code..."}
                  value={crewSearch}
                  onChange={(e) => setCrewSearch(e.target.value)}
                  className="pl-8 text-sm"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "الطائرة" : "Aircraft"}</Label>
              <Select
                value={aircraftFilter}
                onValueChange={setAircraftFilter}
                disabled={!report || loading}
              >
                <SelectTrigger className="text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_AIRCRAFT}>
                    {ar ? "كل الطائرات (All aircraft)" : "All aircraft"}
                  </SelectItem>
                  {aircraftOptions.map((registration) => (
                    <SelectItem key={registration} value={registration}>
                      {registration}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "رمز الموقع" : "Position token"}</Label>
              <Select
                value={positionTokenFilter}
                onValueChange={(value) => setPositionTokenFilter(value as PositionTokenFilter)}
                disabled={!report || loading}
              >
                <SelectTrigger className="text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_POSITION_TOKENS}>{ar ? "الكل (All)" : "All"}</SelectItem>
                  <SelectItem value={ACTIVE_POSITION_TOKEN}>
                    {ar ? "نشط (Active)" : "Active"}
                  </SelectItem>
                  {positionTokenOptions.map((token) => (
                    <SelectItem key={token} value={token}>
                      {token}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-1">
              <Button onClick={fetchReport} disabled={loading} className="w-full gap-2">
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                {ar ? "تحميل التقرير" : "Load Report"}
              </Button>
            </div>
          </div>
          <p
            className="mt-4 rounded-md border border-primary/15 bg-primary/5 px-3 py-2 text-xs text-muted-foreground"
            role="note"
          >
            {ar
              ? "تغيّر المرشحات تفاصيل الرحلات الظاهرة فقط. تظل الإجماليات الرسمية شاملة لأرجل PAD / غير النشطة."
              : "Filters change visible flight details only. Official totals still include PAD / Not-Active legs."}
          </p>
        </CardContent>
      </Card>

      {/* KPI Grid */}
      {report && (
        <section aria-labelledby="crew-hours-kpi-heading" className="space-y-3">
          <h2 id="crew-hours-kpi-heading" className="sr-only">
            {ar ? "مؤشرات ساعات الطاقم" : "Crew hours KPIs"}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {ar ? "الساعات الرسمية لقمرة القيادة" : "Cockpit official hours"}
                </CardTitle>
                <ShieldCheck className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="font-mono text-3xl font-semibold tracking-tight">
                  {displayOfficialHours(report, "Cockpit")}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {ar
                    ? "الساعات الرسمية المقدمة من LEON لطاقم قمرة القيادة"
                    : "Server-provided official LEON hours for cockpit crew"}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {ar ? "الساعات الرسمية للصيانة:" : "Maintenance official hours:"}{" "}
                  <span className="font-mono">{displayOfficialHours(report, "Maintenance")}</span>
                </p>
              </CardContent>
            </Card>

            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {ar ? "الساعات الرسمية للضيافة" : "Cabin official hours"}
                </CardTitle>
                <ShieldCheck className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="font-mono text-3xl font-semibold tracking-tight">
                  {displayOfficialHours(report, "Cabin")}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {ar
                    ? "الساعات الرسمية المقدمة من LEON لطاقم الضيافة"
                    : "Server-provided official LEON hours for cabin crew"}
                </p>
              </CardContent>
            </Card>

            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {ar ? "الأرجل المطابقة" : "Matched legs"}
                </CardTitle>
                <Plane className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold tracking-tight">{report.total_flights}</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {ar
                    ? "عدد الرحلات المطابقة لسجلات التقرير، وليس عدد صفوف LEON"
                    : "Flights matched to report records; not the LEON row count"}
                </p>
              </CardContent>
            </Card>

            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {ar ? "سجلات LEON" : "LEON records"}
                </CardTitle>
                <FileSpreadsheet className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold tracking-tight">{report.records_count}</div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {ar
                    ? "عدد الصفوف التي أعادها LEON، وليس عدد الأرجل المطابقة"
                    : "Rows returned by LEON; not the matched-leg count"}
                </p>
              </CardContent>
            </Card>

            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {ar ? "الأدوار غير المصنفة" : "Unclassified roles"}
                </CardTitle>
                <Users
                  className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
                  aria-hidden="true"
                />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold tracking-tight text-amber-600 dark:text-amber-400">
                  {unclassifiedRoles}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {ar
                    ? "عدد أفراد الطاقم الذين قيمة position_type لديهم null"
                    : "Crew rows where position_type is null"}
                </p>
              </CardContent>
            </Card>
          </div>
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground"
            role="status"
            aria-live="polite"
          >
            <span>
              {ar
                ? `الإجماليات الرسمية المتاحة: ${report.official_totals_available}`
                : `Official totals available: ${report.official_totals_available}`}
            </span>
            <span>
              {ar
                ? `الإجماليات الرسمية غير المتاحة: ${report.official_totals_unavailable}`
                : `Official totals unavailable: ${report.official_totals_unavailable}`}
            </span>
          </div>
        </section>
      )}

      {/* Main Content Area */}
      {loading && (
        <Card
          className="p-8 space-y-4"
          role="status"
          aria-live="polite"
          aria-busy="true"
          aria-label={ar ? "جاري تحميل تقرير ساعات الطاقم" : "Loading crew hours report"}
        >
          <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <div className="space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
          <div className="space-y-2 pt-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        </Card>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{ar ? "خطأ في تحميل التقرير" : "Error Loading Report"}</AlertTitle>
          <AlertDescription className="mt-1 flex items-center justify-between">
            <span>{error}</span>
            <Button variant="outline" size="sm" onClick={fetchReport} className="ml-4">
              {ar ? "إعادة المحاولة" : "Retry"}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {!loading && !error && report && report.crew_members.length === 0 && (
        <Card className="p-12 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <Users className="h-6 w-6 text-muted-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-semibold">
            {ar ? "لا توجد سجلات" : "No Crew Records Found"}
          </h3>
          <p className="mt-2 text-sm text-muted-foreground">
            {ar
              ? "لم يتم العثور على رحلات أو طاقم بالفلاتر المحددة. جرب تغيير النطاق الزمني."
              : "No flight or crew data matched your criteria for this interval."}
          </p>
        </Card>
      )}

      {!loading && !error && report && report.crew_members.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">
              {ar ? "تفاصيل الطاقم والرحلات" : "Crew Members & Flight Breakdown"}
            </h2>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button variant="outline" size="sm" disabled className="gap-2 opacity-60">
                      <FileSpreadsheet className="h-4 w-4" />
                      {ar ? "تصدير Excel (قريباً)" : "Export Excel (Soon)"}
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">
                    {ar
                      ? "سيتم تفعيل التصدير لـ Excel في المرحلة التالية بعد اعتماد النموذج."
                      : "Excel Export will be enabled in the upcoming phase."}
                  </p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          <TooltipProvider>
            <Tabs
              value={activeTab}
              onValueChange={(value) => setActiveTab(value as ReportTab)}
              className="min-w-0"
              aria-label={ar ? "تبويبات تقرير ساعات الطاقم" : "Crew hours report tabs"}
            >
              <TabsList
                aria-label={ar ? "تبويبات تقرير ساعات الطاقم" : "Crew hours report tabs"}
                className="flex h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-b border-border/70 bg-transparent p-0"
              >
                {REPORT_TABS.map((tab) => (
                  <TabsTrigger
                    key={tab.value}
                    value={tab.value}
                    className="rounded-none border-b-2 border-transparent px-3 py-2.5 text-xs sm:text-sm data-[state=active]:border-info data-[state=active]:bg-transparent data-[state=active]:text-info data-[state=active]:shadow-none"
                  >
                    {reportTabLabel(tab, ar)}
                  </TabsTrigger>
                ))}
              </TabsList>

              {activeTabOutsideMessage && (
                <p className="mt-2 text-xs text-muted-foreground" role="status" aria-live="polite">
                  {activeTabOutsideMessage}
                </p>
              )}

              {REPORT_TABS.map((tab) => (
                <TabsContent key={tab.value} value={tab.value} className="mt-4 min-w-0">
                  <CrewReportTabPanel
                    report={report}
                    tab={tab}
                    aircraftFilter={aircraftFilter}
                    positionTokenFilter={positionTokenFilter}
                    hasClientSideDisplayFilter={hasClientSideDisplayFilter}
                    expandedCrew={expandedCrew}
                    trnOverrides={trnOverrides}
                    ar={ar}
                    onToggleCrew={toggleExpand}
                    onToggleTrn={toggleTrn}
                  />
                </TabsContent>
              ))}
            </Tabs>
          </TooltipProvider>
        </div>
      )}
    </div>
  );
}
