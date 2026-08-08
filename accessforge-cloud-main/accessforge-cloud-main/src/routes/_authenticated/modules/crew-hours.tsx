import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { AlertCircle, Calendar, FileSpreadsheet, Filter, Plane, RefreshCw, Search, ShieldCheck, Users } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiClient } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n";
import { toast } from "sonner";
import { CrewReportTabPanel } from "@/components/crew-hours/CrewReportTabPanel";
import { displayOfficialHours, formatLastLoadedAt } from "@/components/crew-hours/format";
import { hasOfficialMcpTotal, isValidReportPeriod, reportTabPosition } from "@/components/crew-hours/filters";
import { outsideTabCrewMessage, reportTabLabel } from "@/components/crew-hours/messages";
import { ACTIVE_POSITION_TOKEN, ALL_AIRCRAFT, ALL_POSITION_TOKENS, OFFICIAL_MCP_SOURCE, POSITIONING_TOKENS, REPORT_TABS } from "@/components/crew-hours/types";
import type { CrewHoursReport, PositionTokenFilter, ReportTab } from "@/components/crew-hours/types";
export const Route = createFileRoute("/_authenticated/modules/crew-hours")({
  head: () => ({ meta: [{ title: "Crew Hours (LEON) · REDSEA" }] }),
  component: CrewHoursPage,
});
function CrewHoursPage() {
  const { lang, t } = useI18n();
  const [fromDate, setFromDate] = useState("2026-06-01");
  const [toDate, setToDate] = useState("2026-06-30");
  const [position, setPosition] = useState("All");
  const [crewSearch, setCrewSearch] = useState("");
  const [aircraftFilter, setAircraftFilter] = useState(ALL_AIRCRAFT);
  const [positionTokenFilter, setPositionTokenFilter] = useState<PositionTokenFilter>(ALL_POSITION_TOKENS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{
    kind: "validation" | "rate_limited" | "unavailable" | "timeout" | "generic";
    detail: string;
  } | null>(null);
  const [report, setReport] = useState<CrewHoursReport | null>(null);
  const [lastLoadedAt, setLastLoadedAt] = useState<Date | null>(null);
  const [exporting, setExporting] = useState(false);
  const requestInFlightRef = useRef(false);
  const [trnOverrides, setTrnOverrides] = useState<Record<string, boolean>>({});
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
      const data = await ApiClient.fetch<CrewHoursReport>(`/statistics/crew-hours/report?${params.toString()}`);
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
      const detail = err instanceof Error ? err.message : t("crew.load.failed");
      const normalizedDetail = detail.toLowerCase();
      const kind = normalizedDetail.includes("timed out") ? "timeout" : normalizedDetail.includes("rate limit") ? "rate_limited" : normalizedDetail.includes("not configured") || normalizedDetail.includes("transport failed") ? "unavailable" : normalizedDetail.includes("query parameter") || normalizedDetail.includes("does not provide position data") ? "validation" : "generic";
      setError({ kind, detail });
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };
  const exportReport = async () => {
    if (exporting || !isValidReportPeriod(report?.period)) {
      return;
    }
    setExporting(true);
    try {
      const params = new URLSearchParams({
        from: fromDate,
        to: toDate,
        position,
      });
      if (crewSearch.trim()) {
        params.append("crew_member", crewSearch.trim());
      }
      const { blob, filename } = await ApiClient.fetchBlob(`/statistics/crew-hours/report/export?${params.toString()}`);
      if (!filename) {
        throw new Error(t("crew.export.no_filename"));
      }
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.style.display = "none";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      toast.success(t("crew.export.success"));
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : t("crew.export.failed"));
    } finally {
      setExporting(false);
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
  const aircraftOptions = report === null ? [] : Array.from(new Set(report.crew_members.flatMap((crew) => crew.flights.map((flight) => flight.aircraft_reg).filter((registration): registration is string => typeof registration === "string" && registration.trim().length > 0)))).sort();
  const positionTokenOptions = report === null ? [] : POSITIONING_TOKENS.filter((token) => report.crew_members.some((crew) => crew.flights.some((flight) => flight.position === token)));
  const unclassifiedRoles = report?.crew_members.filter((crew) => crew.position_type === null).length ?? 0;
  const hasClientSideDisplayFilter = aircraftFilter !== ALL_AIRCRAFT || positionTokenFilter !== ALL_POSITION_TOKENS;
  const activeTabOutsideMessage = report ? outsideTabCrewMessage(report, reportTabPosition(activeTab), t) : null;
  const hasPartialOfficialTotals = report !== null && (report.total_flights > 0 || report.crew_members.some((crew) => crew.flights.length > 0)) && report.crew_members.some((crew) => !hasOfficialMcpTotal(report, crew));
  const errorCopy = error
    ? {
        validation: {
          title: t("crew.error.validation.title"),
          description: t("crew.error.validation.description"),
        },
        rate_limited: {
          title: t("crew.error.rate_limited.title"),
          description: t("crew.error.rate_limited.description"),
        },
        unavailable: {
          title: t("crew.error.unavailable.title"),
          description: t("crew.error.unavailable.description"),
        },
        timeout: {
          title: t("crew.error.timeout.title"),
          description: t("crew.error.timeout.description"),
        },
        generic: {
          title: t("crew.error.title"),
          description: t("crew.load.failed"),
        },
      }[error.kind]
    : null;
  return (
    <div className="container mx-auto max-w-full space-y-6 overflow-x-hidden p-4 md:p-8">
      <div className="flex flex-col gap-5 border-b border-border/70 pb-5 md:flex-row md:items-start md:justify-between">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20"><Users className="h-5 w-5" /></div>
          <div><h1 className="text-3xl font-bold tracking-tight">{t("crew.title")}</h1><p className="mt-1 text-sm text-muted-foreground">{t("crew.subtitle")}</p></div>
        </div>
        <div className="flex flex-wrap items-center gap-2 md:justify-end">
          {report && !error && officialSourceAvailable && <Badge variant="outline" className="gap-1.5 border-success/30 bg-success/10 text-success"><ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />{t("crew.official_mcp")}</Badge>}
          {lastLoadedAt && <span className="text-xs text-muted-foreground">{t("crew.last_loaded")}: {formatLastLoadedAt(lastLoadedAt, lang === "ar")}</span>}
        </div>
      </div>
      <Card className="rounded-xl border-border/80 bg-card shadow-sm">
        <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base font-semibold"><Filter className="h-4 w-4 text-primary" />{t("crew.filters.title")}</CardTitle></CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
            <div className="space-y-1.5"><Label className="text-xs font-medium">{t("crew.filters.from")}</Label><div className="relative"><Calendar className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="pl-8 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" /></div></div>
            <div className="space-y-1.5"><Label className="text-xs font-medium">{t("crew.filters.to")}</Label><div className="relative"><Calendar className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="pl-8 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" /></div></div>
            <div className="space-y-1.5"><Label className="text-xs font-medium">{t("crew.filters.position")}</Label><Select value={position} onValueChange={setPosition}><SelectTrigger className="text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="All">{t("crew.filters.all_positions")}</SelectItem><SelectItem value="Cockpit">{t("crew.tabs.cockpit")}</SelectItem><SelectItem value="Cabin">{t("crew.tabs.cabin")}</SelectItem></SelectContent></Select></div>
            <div className="space-y-1.5"><Label className="text-xs font-medium">{t("crew.filters.crew_search")}</Label><div className="relative"><Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input placeholder={t("crew.filters.crew_search_placeholder")} value={crewSearch} onChange={(e) => setCrewSearch(e.target.value)} className="pl-8 text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2" /></div></div>
            <div className="space-y-1.5"><Label className="text-xs font-medium">{t("crew.filters.aircraft")}</Label><Select value={aircraftFilter} onValueChange={setAircraftFilter} disabled={!report || loading}><SelectTrigger className="text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"><SelectValue /></SelectTrigger><SelectContent><SelectItem value={ALL_AIRCRAFT}>{t("crew.filters.all_aircraft")}</SelectItem>{aircraftOptions.map((registration) => <SelectItem key={registration} value={registration}>{registration}</SelectItem>)}</SelectContent></Select></div>
            <div className="space-y-1.5"><Label className="text-xs font-medium">{t("crew.filters.position_token")}</Label><Select value={positionTokenFilter} onValueChange={(value) => setPositionTokenFilter(value as PositionTokenFilter)} disabled={!report || loading}><SelectTrigger className="text-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"><SelectValue /></SelectTrigger><SelectContent><SelectItem value={ALL_POSITION_TOKENS}>{t("crew.filters.all_tokens")}</SelectItem><SelectItem value={ACTIVE_POSITION_TOKEN}>{t("crew.filters.active")}</SelectItem>{positionTokenOptions.map((token) => <SelectItem key={token} value={token}>{token}</SelectItem>)}</SelectContent></Select></div>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-1"><Button onClick={fetchReport} disabled={loading} aria-busy={loading} className="w-full gap-2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />{t("crew.filters.load")}</Button></div>
          </div>
          <p className="mt-4 rounded-md border border-primary/15 bg-primary/5 px-3 py-2 text-xs text-muted-foreground" role="note">
            {t("crew.filters.note")}
          </p>
        </CardContent>
      </Card>
      {/* KPI Grid */}
      {report && (
        <section aria-labelledby="crew-hours-kpi-heading" className="space-y-3">
          <h2 id="crew-hours-kpi-heading" className="sr-only">
            {t("crew.kpi.heading")}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("crew.kpi.cockpit_hours")}</CardTitle>
                <ShieldCheck className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="font-mono text-3xl font-semibold tracking-tight">{report.crew_members.some((crew) => crew.position_type === "Cockpit" && hasOfficialMcpTotal(report, crew)) ? displayOfficialHours(report, "Cockpit") : t("crew.unavailable")}</div>
                <p className="mt-1 text-xs text-muted-foreground">{t("crew.kpi.cockpit_description")}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {t("crew.kpi.maintenance_hours")} <span className="font-mono">{report.crew_members.some((crew) => crew.position_type === "Maintenance" && hasOfficialMcpTotal(report, crew)) ? displayOfficialHours(report, "Maintenance") : t("crew.unavailable")}</span>
                </p>
              </CardContent>
            </Card>
            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("crew.kpi.cabin_hours")}</CardTitle>
                <ShieldCheck className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="font-mono text-3xl font-semibold tracking-tight">{report.crew_members.some((crew) => crew.position_type === "Cabin" && hasOfficialMcpTotal(report, crew)) ? displayOfficialHours(report, "Cabin") : t("crew.unavailable")}</div>
                <p className="mt-1 text-xs text-muted-foreground">{t("crew.kpi.cabin_description")}</p>
              </CardContent>
            </Card>
            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("crew.kpi.matched_legs")}</CardTitle>
                <Plane className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold tracking-tight">{report.total_flights}</div>
                <p className="mt-1 text-xs text-muted-foreground">{t("crew.kpi.matched_legs_description")}</p>
              </CardContent>
            </Card>
            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("crew.kpi.leon_records")}</CardTitle>
                <FileSpreadsheet className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold tracking-tight">{report.records_count}</div>
                <p className="mt-1 text-xs text-muted-foreground">{t("crew.kpi.leon_records_description")}</p>
              </CardContent>
            </Card>
            <Card className="rounded-xl border-border/80 bg-card shadow-sm">
              <CardHeader className="flex flex-row items-start justify-between gap-3 pb-2">
                <CardTitle className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{t("crew.kpi.unclassified_roles")}</CardTitle>
                <Users className="h-4 w-4 shrink-0 text-warning-foreground" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold tracking-tight text-warning-foreground">{unclassifiedRoles}</div>
                <p className="mt-1 text-xs text-muted-foreground">{t("crew.kpi.unclassified_roles_description")}</p>
              </CardContent>
            </Card>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-xs text-muted-foreground" role="status" aria-live="polite">
            <span>{t("crew.kpi.totals_available", { count: report.official_totals_available })}</span>
            <span>{t("crew.kpi.totals_unavailable", { count: report.official_totals_unavailable })}</span>
          </div>
        </section>
      )}
      {/* Main Content Area */}
      {loading && (
        <Card className="space-y-4 p-8" role="status" aria-live="polite" aria-busy="true" aria-label={t("crew.loading.aria")}>
          <div className="flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <div className="space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
          <div className="w-full overflow-x-auto rounded-lg border border-border/80 bg-card">
            <div className="min-w-[760px] space-y-3 p-4">
              <div className="grid grid-cols-6 gap-3">
                {Array.from({ length: 6 }, (_, index) => (
                  <Skeleton key={`heading-${index}`} className="h-4 w-full" />
                ))}
              </div>
              <div className="space-y-2">
                {Array.from({ length: 5 }, (_, row) => (
                  <div key={`row-${row}`} className="grid grid-cols-6 gap-3">
                    {Array.from({ length: 6 }, (_, column) => (
                      <Skeleton key={`cell-${row}-${column}`} className="h-8 w-full" />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Card>
      )}
      {error && errorCopy && (
        <Alert variant="destructive" role="alert" aria-live="assertive">
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <AlertTitle>{errorCopy.title}</AlertTitle>
          <AlertDescription className="mt-1 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <p>{error.detail}</p>
              <p className="text-xs">{errorCopy.description}</p>
            </div>
            <Button variant="outline" size="sm" onClick={fetchReport} className="ms-0 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:ms-4">
              {t("crew.error.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {!loading && !error && report && hasPartialOfficialTotals && (
        <Alert className="border-warning/40 bg-warning/5 text-foreground" role="status" aria-live="polite">
          <AlertCircle className="h-4 w-4 text-warning-foreground" aria-hidden="true" />
          <AlertTitle>{t("crew.partial.title")}</AlertTitle>
          <AlertDescription>{t("crew.partial.description")}</AlertDescription>
        </Alert>
      )}
      {!loading && !error && report && report.crew_members.length === 0 && (
        <Card className="p-12 text-center" role="status" aria-live="polite">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <Users className="h-6 w-6 text-muted-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-semibold">{t("crew.empty.title")}</h3>
          <p className="mt-2 text-sm text-muted-foreground">{t("crew.empty.description")}</p>
        </Card>
      )}
      {!loading && !error && report && report.crew_members.length > 0 && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold tracking-tight">{t("crew.details.title")}</h2>
            <Button type="button" variant="outline" size="sm" onClick={exportReport} disabled={exporting || !isValidReportPeriod(report?.period)} aria-busy={exporting} aria-label={t(exporting ? "crew.export.aria_exporting" : "crew.export.aria_export")} className="gap-2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
              <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
              {t(exporting ? "crew.export.button_exporting" : "crew.export.button_export")}
            </Button>
          </div>
          <TooltipProvider>
            <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as ReportTab)} className="min-w-0" aria-label={t("crew.tabs.aria")}>
              <TabsList aria-label={t("crew.tabs.aria")} className="flex h-auto w-full justify-start gap-1 overflow-x-auto rounded-none border-b border-border/70 bg-transparent p-0">
                {REPORT_TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value} className="rounded-none border-b-2 border-transparent px-3 py-2.5 text-xs focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 sm:text-sm data-[state=active]:border-info data-[state=active]:bg-transparent data-[state=active]:text-info data-[state=active]:shadow-none">
                    {reportTabLabel(tab, t)}
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
                  <CrewReportTabPanel report={report} tab={tab} aircraftFilter={aircraftFilter} positionTokenFilter={positionTokenFilter} hasClientSideDisplayFilter={hasClientSideDisplayFilter} expandedCrew={expandedCrew} trnOverrides={trnOverrides} onToggleCrew={toggleExpand} onToggleTrn={toggleTrn} />
                </TabsContent>
              ))}
            </Tabs>
          </TooltipProvider>
        </div>
      )}
    </div>
  );
}
