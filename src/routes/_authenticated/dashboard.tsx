import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, ListTodo, FolderKanban, Layers } from "lucide-react";

export const Route = createFileRoute("/_authenticated/dashboard")({
  head: () => ({ meta: [{ title: "Dashboard · REDSEA" }] }),
  component: DashboardPage,
});

function DashboardPage() {
  const { user } = useAuth();
  const perms = usePermissions();

  const { data: stats } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: async () => {
      const [up, prj, jb, mods] = await Promise.all([
        supabase.from("uploads").select("id", { count: "exact", head: true }),
        supabase.from("projects").select("id", { count: "exact", head: true }),
        supabase.from("jobs").select("id, status", { count: "exact" }).limit(1000),
        supabase.from("modules").select("id", { count: "exact", head: true }).eq("enabled", true),
      ]);
      const jobs = jb.data ?? [];
      return {
        uploads: up.count ?? 0,
        projects: prj.count ?? 0,
        modules: mods.count ?? 0,
        jobsTotal: jb.count ?? 0,
        running: jobs.filter((j) => j.status === "running").length,
        queued: jobs.filter((j) => j.status === "queued").length,
        failed: jobs.filter((j) => j.status === "failed").length,
        done: jobs.filter((j) => j.status === "done").length,
      };
    },
  });

  const fullName = (user?.user_metadata?.full_name as string | undefined) ?? user?.email;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">Welcome back</p>
        <h1 className="text-3xl font-bold tracking-tight">{fullName}</h1>
        <div className="flex flex-wrap gap-2 mt-2">
          {perms.roles.map((r) => (
            <Badge key={r} variant="outline" className="capitalize">
              {r.replace("_", " ")}
            </Badge>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Stat icon={FolderKanban} label="Projects"  value={stats?.projects} />
        <Stat icon={FileText}     label="Uploads"   value={stats?.uploads} />
        <Stat icon={ListTodo}     label="Jobs"      value={stats?.jobsTotal} />
        <Stat icon={Layers}       label="Modules"   value={stats?.modules} />
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Job queue</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-4 gap-3 text-center">
            <Pill label="Queued"  v={stats?.queued}  tone="info" />
            <Pill label="Running" v={stats?.running} tone="warning" />
            <Pill label="Done"    v={stats?.done}    tone="success" />
            <Pill label="Failed"  v={stats?.failed}  tone="destructive" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Your access</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2">
            <div className="flex justify-between"><span className="text-muted-foreground">Modules viewable</span><span className="font-medium">{perms.isAdmin ? "All" : perms.moduleKeys.view.length}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Modules runnable</span><span className="font-medium">{perms.isAdmin ? "All" : perms.moduleKeys.run.length}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Roles</span><span className="font-medium capitalize">{perms.roles.join(", ") || "—"}</span></div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ icon: Icon, label, value }: { icon: React.ComponentType<{ className?: string }>; label: string; value?: number }) {
  return (
    <Card>
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
}

const toneCls: Record<string, string> = {
  info: "bg-info/15 text-info",
  warning: "bg-warning/15 text-warning",
  success: "bg-success/15 text-success",
  destructive: "bg-destructive/15 text-destructive",
};
function Pill({ label, v, tone }: { label: string; v?: number; tone: keyof typeof toneCls }) {
  return (
    <div className={`rounded-lg py-3 ${toneCls[tone]}`}>
      <p className="text-xs uppercase tracking-wider opacity-80">{label}</p>
      <p className="text-xl font-bold mt-0.5">{v ?? 0}</p>
    </div>
  );
}
