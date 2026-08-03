import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  Users,
  Calendar,
  Filter,
  Search,
  RefreshCw,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle2,
  Clock,
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
import { useI18n } from "@/lib/i18n";

export const Route = createFileRoute("/_authenticated/modules/crew-hours")({
  head: () => ({ meta: [{ title: "Crew Hours (LEON) · REDSEA" }] }),
  component: CrewHoursPage,
});

interface FlightItem {
  flight_nid: string;
  flight_number?: string;
  departure_airport?: string;
  arrival_airport?: string;
  start_time_utc: string;
  end_time_utc: string;
  aircraft_reg?: string;
  aircraft_type?: string;
  position?: string;
  flight_training_type?: string;
  is_trn: boolean;
  journey_log?: any;
}

interface CrewMemberSummary {
  crew_id: string;
  person_code?: string;
  name: string;
  surname: string;
  position_type?: string;
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
  crew_members: CrewMemberSummary[];
}

const OFFICIAL_MCP_SOURCE = "official_mcp_report";

function hasOfficialTotal(crew: CrewMemberSummary): boolean {
  return typeof crew.official_total === "string" && crew.official_total.trim().length > 0;
}

function officialSourceLabel(status: string, ar: boolean): string {
  if (status === OFFICIAL_MCP_SOURCE) {
    return ar ? "LEON MCP الرسمي" : "Official LEON MCP";
  }
  return ar ? "الساعات الرسمية غير متاحة" : "Official hours unavailable";
}

function CrewHoursPage() {
  const { lang } = useI18n();
  const ar = lang === "ar";

  const [fromDate, setFromDate] = useState("2026-06-01");
  const [toDate, setToDate] = useState("2026-06-30");
  const [position, setPosition] = useState("All");
  const [crewSearch, setCrewSearch] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<CrewHoursReport | null>(null);

  // Interactive TRN override per crew member
  const [trnOverrides, setTrnOverrides] = useState<Record<string, boolean>>({});
  // Expanded crew cards
  const [expandedCrew, setExpandedCrew] = useState<Record<string, boolean>>({});

  const officialTotalsAvailable = report?.crew_members.filter(hasOfficialTotal).length ?? 0;
  const officialTotalsUnavailable = report
    ? report.crew_members.length - officialTotalsAvailable
    : 0;
  const officialSourceAvailable = report?.hours_source_status === OFFICIAL_MCP_SOURCE;
  const allOfficialTotalsAvailable = officialSourceAvailable && officialTotalsUnavailable === 0;
  const hasPartialOfficialTotals = officialTotalsAvailable > 0 && officialTotalsUnavailable > 0;

  const fetchReport = async () => {
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

      const res = await fetch(`/api/statistics/crew-hours/report?${params.toString()}`);
      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`);
      }
      const data: CrewHoursReport = await res.json();
      setReport(data);

      // Expand all crew members by default
      const exp: Record<string, boolean> = {};
      data.crew_members.forEach((c) => {
        exp[c.crew_id] = true;
      });
      setExpandedCrew(exp);
    } catch (err: any) {
      setError(err.message || "Failed to load crew hours report");
    } finally {
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

  return (
    <div className="container mx-auto space-y-6 p-4 md:p-8">
      {/* Header */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Users className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                {ar ? "ساعات الطاقم (LEON API)" : "Crew Hours (LEON)"}
              </h1>
              <p className="text-sm text-muted-foreground">
                {ar
                  ? "قراءة البيانات الرسمية للرحلات وأفراد الطاقم وحالات التدريب"
                  : "Official flight & crew records, position details, and training status"}
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
            {ar ? "اتصال LEON نشط" : "LEON Connection Active"}
          </Badge>
          {report && (
            <Badge
              variant={officialSourceAvailable ? "outline" : "secondary"}
              className="gap-1.5"
              aria-label={officialSourceLabel(report.hours_source_status, ar)}
            >
              {officialSourceAvailable ? (
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {officialSourceLabel(report.hours_source_status, ar)}
            </Badge>
          )}
        </div>
      </div>

      {/* Filter Toolbar */}
      <Card className="border-primary/20 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Filter className="h-4 w-4 text-primary" />
            {ar ? "تصفية التقرير" : "Report Filters"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-5">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "من تاريخ" : "From Date"}</Label>
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
              <Label className="text-xs font-medium">{ar ? "إلى تاريخ" : "To Date"}</Label>
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
                  <SelectItem value="Cockpit">{ar ? "قمرة القيادة (Cockpit)" : "Cockpit"}</SelectItem>
                  <SelectItem value="Cabin">{ar ? "الضيافة (Cabin)" : "Cabin"}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">{ar ? "اسم / كود الطاقم" : "Crew Search"}</Label>
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

            <div className="flex items-end gap-2 sm:col-span-2 md:col-span-1">
              <Button onClick={fetchReport} disabled={loading} className="w-full gap-2">
                <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                {ar ? "تحميل التقرير" : "Load Report"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary Cards */}
      {report && (
        <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4">
          <Card className="bg-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {ar ? "إجمالي الطاقم" : "Total Crew Members"}
              </CardTitle>
              <Users className="h-4 w-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{report.total_crew}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {ar ? "أفراد مسجلين في الفتره" : "Active during selected period"}
              </p>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {ar ? "إجمالي الرحلات" : "Total Flights"}
              </CardTitle>
              <Plane className="h-4 w-4 text-blue-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{report.total_flights}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {ar ? "رحلة مؤكدة من LEON" : "Confirmed flights in interval"}
              </p>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {ar ? "الساعات الرسمية المتاحة" : "Official Totals Available"}
              </CardTitle>
              <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-hidden="true" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{officialTotalsAvailable}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {ar ? "أفراد لديهم إجمالي LEON رسمي" : "Crew members with official LEON totals"}
              </p>
            </CardContent>
          </Card>

          <Card className="bg-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                {ar ? "الساعات الرسمية غير المتاحة" : "Official Totals Unavailable"}
              </CardTitle>
              <Clock className="h-4 w-4 text-amber-500" aria-hidden="true" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{officialTotalsUnavailable}</div>
              <p className="text-xs text-muted-foreground mt-1" role="status" aria-live="polite">
                {hasPartialOfficialTotals
                  ? ar
                    ? "بيانات رسمية جزئية لهذا التقرير"
                    : "Partial official totals for this report"
                  : allOfficialTotalsAvailable
                    ? ar
                      ? "كل الإجماليات الرسمية متاحة"
                      : "All official totals are available"
                    : ar
                      ? "الإجماليات الرسمية غير متاحة"
                      : "Official totals are unavailable"}
              </p>
            </CardContent>
          </Card>
        </div>
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
          <h3 className="mt-4 text-lg font-semibold">{ar ? "لا توجد سجلات" : "No Crew Records Found"}</h3>
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

          <div className="space-y-4">
            {report.crew_members.map((crew) => {
              const isTrnActive = trnOverrides[crew.crew_id] ?? (crew.status === "TRN");
              const isExpanded = expandedCrew[crew.crew_id] ?? true;

              return (
                <Card key={crew.crew_id} className="overflow-hidden border-border/80 transition-all shadow-sm">
                  {/* Card Header */}
                  <div
                    className="flex flex-col gap-3 p-4 bg-muted/30 sm:flex-row sm:items-center sm:justify-between cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => toggleExpand(crew.crew_id)}
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 font-bold text-primary">
                        {crew.name[0]}
                        {crew.surname[0]}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-base">
                            {crew.name} {crew.surname}
                          </h3>
                          {crew.person_code && (
                            <Badge variant="secondary" className="text-xs">
                              {crew.person_code}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {crew.position_name || crew.position_type} • {crew.flight_count}{" "}
                          {ar ? "رحلات" : "flights"}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                      {/* TRN Override Toggle */}
                      <Button
                        variant={isTrnActive ? "default" : "outline"}
                        size="sm"
                        onClick={() => toggleTrn(crew.crew_id)}
                        className={`h-8 gap-1.5 text-xs ${
                          isTrnActive ? "bg-amber-600 hover:bg-amber-700 text-white" : ""
                        }`}
                      >
                        <Badge
                          variant={isTrnActive ? "secondary" : "outline"}
                          className="px-1 py-0 text-[10px]"
                        >
                          TRN
                        </Badge>
                        {isTrnActive ? (ar ? "حالة تدريب (TRN)" : "Training (TRN)") : (ar ? "عادي (Normal)" : "Normal")}
                      </Button>

                      <div className="flex items-center gap-2 text-right text-xs">
                        <div>
                          <span className="text-muted-foreground block">
                            {ar ? "الساعات الرسمية" : "Official Block Time"}
                          </span>
                          <span
                            className={`font-mono font-medium ${hasOfficialTotal(crew) ? "text-foreground" : "text-muted-foreground"}`}
                          >
                            {crew.official_total ??
                              (ar ? "الساعات الرسمية غير متاحة" : "Official hours unavailable")}
                          </span>
                        </div>
                        <Badge
                          variant={
                            hasOfficialTotal(crew) && officialSourceAvailable
                              ? "outline"
                              : "secondary"
                          }
                          aria-label={
                            hasOfficialTotal(crew) && officialSourceAvailable
                              ? officialSourceLabel(report.hours_source_status, ar)
                              : ar
                                ? "الساعات الرسمية غير متاحة"
                                : "Official hours unavailable"
                          }
                        >
                          {hasOfficialTotal(crew) && officialSourceAvailable
                            ? officialSourceLabel(report.hours_source_status, ar)
                            : ar
                              ? "غير متاح"
                              : "Unavailable"}
                        </Badge>
                      </div>

                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => toggleExpand(crew.crew_id)}
                      >
                        {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>

                  {/* Flight Details Table */}
                  {isExpanded && (
                    <CardContent className="p-0 border-t">
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                          <thead className="bg-muted/20 text-xs uppercase text-muted-foreground">
                            <tr>
                              <th className="py-2.5 px-4 font-medium">{ar ? "الرحلة" : "Flight"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "المغادرة" : "DEP"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "الوصول" : "ARR"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "وقت الاقلاع (UTC)" : "Start (UTC)"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "وقت الهبوط (UTC)" : "End (UTC)"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "الطائرة" : "Aircraft"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "الموقع" : "Position"}</th>
                              <th className="py-2.5 px-4 font-medium">{ar ? "التدريب" : "TRN"}</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {crew.flights.map((flight, idx) => (
                              <tr key={`${crew.crew_id}-${flight.flight_nid}-${idx}`} className="hover:bg-muted/10">
                                <td className="py-2.5 px-4 font-mono font-medium">{flight.flight_nid}</td>
                                <td className="py-2.5 px-4">
                                  <Badge variant="outline" className="font-mono">
                                    {flight.departure_airport || "CAI"}
                                  </Badge>
                                </td>
                                <td className="py-2.5 px-4">
                                  <Badge variant="outline" className="font-mono">
                                    {flight.arrival_airport || "MED"}
                                  </Badge>
                                </td>
                                <td className="py-2.5 px-4 text-xs font-mono">
                                  {flight.start_time_utc.replace("T", " ").replace("Z", "")}
                                </td>
                                <td className="py-2.5 px-4 text-xs font-mono">
                                  {flight.end_time_utc.replace("T", " ").replace("Z", "")}
                                </td>
                                <td className="py-2.5 px-4 text-xs">
                                  {flight.aircraft_reg || "SU-RSX"}{" "}
                                  <span className="text-muted-foreground">({flight.aircraft_type || "B738"})</span>
                                </td>
                                <td className="py-2.5 px-4 text-xs font-medium">
                                  {flight.position || "CPT"}
                                </td>
                                <td className="py-2.5 px-4">
                                  {flight.is_trn || isTrnActive ? (
                                    <Badge variant="secondary" className="bg-amber-500/10 text-amber-600 border-amber-500/20 text-[11px]">
                                      TRN
                                    </Badge>
                                  ) : (
                                    <span className="text-xs text-muted-foreground">-</span>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
