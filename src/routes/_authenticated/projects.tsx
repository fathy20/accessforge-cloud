import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Trash2, FolderKanban, Loader2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";

export const Route = createFileRoute("/_authenticated/projects")({
  head: () => ({ meta: [{ title: "Projects · REDSEA" }] }),
  component: ProjectsPage,
});

function ProjectsPage() {
  const { user } = useAuth();
  const perms = usePermissions();
  const { lang } = useI18n();
  const ar = lang === "ar";
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", tail_number: "", station: "", description: "" });
  const [saving, setSaving] = useState(false);

  const canCreate = perms.hasAnyRole(["engineer", "admin", "super_admin"]);

  const { data: projects = [], isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: async () => {
      const { data, error } = await supabase
        .from("projects")
        .select("id, name, tail_number, station, description, owner_id, created_at")
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data;
    },
  });

  const create = async () => {
    if (!user || !form.name.trim()) return;
    setSaving(true);
    const { error } = await supabase.from("projects").insert({
      name: form.name.trim(),
      tail_number: form.tail_number.trim() || null,
      station: form.station.trim() || null,
      description: form.description.trim() || null,
      owner_id: user.id,
    });
    setSaving(false);
    if (error) { toast.error(error.message); return; }
    toast.success(ar ? "تم إنشاء المشروع" : "Project created");
    setForm({ name: "", tail_number: "", station: "", description: "" });
    setOpen(false);
    qc.invalidateQueries({ queryKey: ["projects"] });
  };

  const remove = async (id: string) => {
    if (!confirm(ar ? "حذف المشروع؟" : "Delete project?")) return;
    const { error } = await supabase.from("projects").delete().eq("id", id);
    if (error) { toast.error(error.message); return; }
    toast.success(ar ? "تم الحذف" : "Deleted");
    qc.invalidateQueries({ queryKey: ["projects"] });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{ar ? "المشاريع" : "Projects"}</h1>
          <p className="text-sm text-muted-foreground">
            {ar ? "تجميع الملفات والمهام تحت طائرة / محطة / فحص." : "Group uploads, jobs, and tasks under aircraft / station / check."}
          </p>
        </div>
        {canCreate && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button><Plus className="size-4 me-1.5" />{ar ? "مشروع جديد" : "New project"}</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>{ar ? "مشروع جديد" : "New project"}</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <div><Label>{ar ? "الاسم" : "Name"} *</Label>
                  <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div><Label>Tail #</Label>
                    <Input value={form.tail_number} onChange={(e) => setForm({ ...form, tail_number: e.target.value })} placeholder="A6-XXX" /></div>
                  <div><Label>{ar ? "المحطة" : "Station"}</Label>
                    <Input value={form.station} onChange={(e) => setForm({ ...form, station: e.target.value })} placeholder="DXB" /></div>
                </div>
                <div><Label>{ar ? "الوصف" : "Description"}</Label>
                  <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setOpen(false)}>{ar ? "إلغاء" : "Cancel"}</Button>
                <Button onClick={create} disabled={saving || !form.name.trim()}>
                  {saving && <Loader2 className="size-4 animate-spin me-1.5" />}{ar ? "إنشاء" : "Create"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>

      {isLoading ? (
        <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
      ) : projects.length === 0 ? (
        <Card><CardContent className="p-10 text-center text-sm text-muted-foreground">
          {ar ? "لا توجد مشاريع بعد." : "No projects yet."}
        </CardContent></Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((p) => {
            const mine = p.owner_id === user?.id;
            return (
              <Card key={p.id} className="hover:border-primary/50 transition-colors">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <FolderKanban className="size-4 text-primary" />
                    <span className="truncate">{p.name}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <div className="flex flex-wrap gap-1.5">
                    {p.tail_number && <Badge variant="secondary">{p.tail_number}</Badge>}
                    {p.station && <Badge variant="outline">{p.station}</Badge>}
                  </div>
                  {p.description && <p className="text-xs text-muted-foreground line-clamp-2">{p.description}</p>}
                  <div className="flex items-center justify-between pt-2 text-xs text-muted-foreground">
                    <span>{new Date(p.created_at).toLocaleDateString()}</span>
                    {(mine || perms.isAdmin) && (
                      <Button variant="ghost" size="icon" onClick={() => remove(p.id)} className="size-7">
                        <Trash2 className="size-3.5 text-destructive" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
