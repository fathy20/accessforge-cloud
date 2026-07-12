import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  FileText, ListTodo, FolderKanban, Layers, Activity, ArrowRight,
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { format, subDays, startOfDay } from "date-fns";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard · REDSEA" }] }),
  component: DashboardPage,
});

const STATUS_COLORS: Record<string, string> = {
  queued: "hsl(var(--info))",
  running: "hsl(var(--warning))",
  done: "hsl(var(--success))",
  failed: "hsl(var(--destructive))",
  cancelled: "hsl(var(--muted-foreground))",
};

function DashboardPage() {
  const { user } = useAuth();
  const perms = usePermissions();
  const { lang } = useI18n();
  const ar = lang === "ar";
  const qc = useQueryClient();

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: async () => {
      const since = subDays(new Date(), 14).toISOString();
      const [up, prj, jb, mods, recentJobs, recentUploads] = await Promise.all([
        supabase.from("uploads").select("id", { count: "exact", head: true }),
        supabase.from("projects").select("id", { count: "exact", head: true }),
        supabase.from("jobs").select("id, status, module_key, created_at, finished_at").gte("created_at", since).limit(2000),
        supabase.from("modules").select("id", { count: "exact", head: true }).eq("enabled", true),
        supabase.from("jobs").select("id, module_key, status, progress, created_at").order("created_at", { ascending: false }).limit(6),
        supabase.from("uploads").select("id, original_name, kind, created_at").order("created_at", { ascending: false }).limit(6),
      ]);
      const jobs = jb.data ?? [];

      // 14-day jobs trend
      const days: { day: string; queued: number; running: number; done: number; failed: number }[] = [];
      for (let i = 13; i >= 0; i--) {
        const d = startOfDay(subDays(new Date(), i));
        days.push({ day: format(d, "MMM d"), queued: 0, running: 0, done: 0, failed: 0 });
      }
      const idxByLabel = new Map(days.map((d, i) => [d.day, i]));
      for (const j of jobs) {
        const label = format(startOfDay(new Date(j.created_at)), "MMM d");
        const i = idxByLabel.get(label);
        if (i === undefined) continue;
        const k = j.status as keyof (typeof days)[number];
        if (k in days[i]) (days[i] as Record<string, number | string>)[k] = (days[i][k as "queued"] as number) + 1;
      }

      // Status breakdown
      const statusCounts: Record<string, number> = {};
      for (const j of jobs) statusCounts[j.status] = (statusCounts[j.status] ?? 0) + 1;
      const statusPie = Object.entries(statusCounts).map(([name, value]) => ({ name, value }));

      // Per-module usage
      const modCounts: Record<string, number> = {};
      for (const j of jobs) modCounts[j.module_key] = (modCounts[j.module_key] ?? 0) + 1;
      const moduleBars = Object.entries(modCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([name, value]) => ({ name: name.replace(/_/g, " "), value }));

      return {
        uploads: up.count ?? 0,
        projects: prj.count ?? 0,
        modules: mods.count ?? 0,
        jobsTotal: jb.count ?? 0,
        running: statusCounts.running ?? 0,
        queued: statusCounts.queued ?? 0,
        failed: statusCounts.failed ?? 0,
        done: statusCounts.done ?? 0,
        days,
        statusPie,
        moduleBars,
        recentJobs: recentJobs.data ?? [],
        recentUploads: recentUploads.data ?? [],
      };
    },
  });

  // Realtime: refresh when jobs change
  useEffect(() => {
    const ch = supabase
      .channel("dashboard-jobs")
      .on("postgres_changes", { event: "*", schema: "public", table: "jobs" }, () => {
        qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
      })
      .subscribe();
    return () => { supabase.removeChannel(ch); };
  }, [qc]);

  const fullName = (user?.user_metadata?.full_name as string | undefined) ?? user?.email;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{ar ? "مرحباً" : "Welcome back"}</p>
          <h1 className="text-3xl font-bold tracking-tight">{fullName}</h1>
          <div className="flex flex-wrap gap-2 mt-2">
            {perms.roles.map((r) => (
              <Badge key={r} variant="outline" className="capitalize">{r.replace("_", " ")}</Badge>
            ))}
          </div>
        </div>
        <Link to="/jobs" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
          {ar ? "متابعة المهام لحظياً" : "Live job monitor"}
          <Activity className="size-3.5" />
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat icon={FolderKanban} label={ar ? "المشاريع" : "Projects"} value={stats?.projects} to="/projects" />
        <Stat icon={FileText} label={ar ? "الملفات" : "Uploads"} value={stats?.uploads} to="/uploads" />
        <Stat icon={ListTodo} label={ar ? "المهام" : "Jobs"} value={stats?.jobsTotal} to="/jobs" />
        <Stat icon={Layers} label={ar ? "الموديولات" : "Modules"} value={stats?.modules} />
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ar ? "المهام آخر 14 يوم" : "Jobs · last 14 days"}</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stats?.days ?? []}>
                <defs>
                  <linearGradient id="g-done" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={STATUS_COLORS.done} stopOpacity={0.55} />
                    <stop offset="100%" stopColor={STATUS_COLORS.done} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="g-failed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={STATUS_COLORS.failed} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={STATUS_COLORS.failed} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="day" fontSize={11} stroke="hsl(var(--muted-foreground))" />
                <YAxis fontSize={11} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
                <Tooltip contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
                <Area type="monotone" dataKey="done" stroke={STATUS_COLORS.done} fill="url(#g-done)" />
                <Area type="monotone" dataKey="failed" stroke={STATUS_COLORS.failed} fill="url(#g-failed)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ar ? "توزيع الحالات" : "Status mix"}</CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {stats && stats.statusPie.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={stats.statusPie} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>
                    {stats.statusPie.map((s) => (
                      <Cell key={s.name} fill={STATUS_COLORS[s.name] ?? "hsl(var(--muted-foreground))"} />
                    ))}
                  </Pie>
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full grid place-items-center text-sm text-muted-foreground">
                {ar ? "لا توجد مهام بعد." : "No jobs yet."}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2 flex flex-row justify-between items-center">
            <CardTitle className="text-base">{ar ? "أحدث المهام" : "Recent jobs"}</CardTitle>
            <Link to="/jobs" className="text-xs text-primary hover:underline inline-flex items-center gap-1">
              {ar ? "الكل" : "All"} <ArrowRight className="size-3" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {!stats?.recentJobs.length ? (
              <p className="p-6 text-sm text-muted-foreground text-center">{ar ? "لا توجد مهام بعد." : "No jobs yet."}</p>
            ) : (
              <div className="divide-y divide-border">
                {stats.recentJobs.map((j) => (
                  <div key={j.id} className="px-4 py-2.5 flex items-center gap-3 text-sm">
                    <Badge variant="outline" className="capitalize" style={{ color: STATUS_COLORS[j.status] }}>
                      {j.status}
                    </Badge>
                    <span className="font-mono">{j.module_key}</span>
                    <span className="text-muted-foreground font-mono text-xs">{j.id.slice(0, 8)}</span>
                    <div className="flex-1" />
                    <span className="text-xs text-muted-foreground">{new Date(j.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2 flex flex-row justify-between items-center">
            <CardTitle className="text-base">{ar ? "أحدث الملفات" : "Recent uploads"}</CardTitle>
            <Link to="/uploads" className="text-xs text-primary hover:underline inline-flex items-center gap-1">
              {ar ? "الكل" : "All"} <ArrowRight className="size-3" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {!stats?.recentUploads.length ? (
              <p className="p-6 text-sm text-muted-foreground text-center">{ar ? "لا توجد ملفات." : "No uploads."}</p>
            ) : (
              <div className="divide-y divide-border">
                {stats.recentUploads.map((u) => (
                  <div key={u.id} className="px-4 py-2.5 flex items-center gap-2 text-sm">
                    <FileText className="size-3.5 text-muted-foreground shrink-0" />
                    <span className="truncate flex-1">{u.original_name}</span>
                    <Badge variant="outline" className="uppercase text-[10px]">{u.kind}</Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {stats && stats.moduleBars.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{ar ? "استخدام الموديولات" : "Module usage (last 14d)"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {stats.moduleBars.map((m) => {
              const max = stats.moduleBars[0].value || 1;
              const pct = (m.value / max) * 100;
              return (
                <div key={m.name} className="flex items-center gap-3 text-sm">
                  <span className="w-32 truncate capitalize">{m.name}</span>
                  <div className="flex-1 h-2.5 rounded-full bg-muted overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="font-mono text-xs w-8 text-right">{m.value}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Stat({
  icon: Icon, label, value, to,
}: { icon: React.ComponentType<{ className?: string }>; label: string; value?: number; to?: string }) {
  const inner = (
    <Card className={to ? "transition-colors hover:bg-muted/40" : ""}>
      <CardContent className="p-5 flex items-center gap-4">
        <div className="size-11 rounded-lg bg-primary/10 text-primary grid place-items-center">
          <Icon className="size-5" />
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="text-2xl font-bold leading-none mt-1">{value ?? "—"}</p>
        </div>
      </CardContent>
    </Card>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}
