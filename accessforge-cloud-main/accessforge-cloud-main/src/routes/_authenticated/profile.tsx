import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Save, KeyRound, User as UserIcon } from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

export const Route = createFileRoute("/_authenticated/profile")({
  head: () => ({ meta: [{ title: "Profile · REDSEA" }] }),
  component: ProfilePage,
});

function ProfilePage() {
  const { user } = useAuth();
  const perms = usePermissions();
  const { lang } = useI18n();
  const ar = lang === "ar";
  const qc = useQueryClient();

  const { data: profile, isLoading } = useQuery({
    queryKey: ["profile", user?.id],
    queryFn: async () => {
      if (!user) return null;
      return await ApiClient.fetch("/auth/me");
    },
    enabled: !!user,
  });

  const [form, setForm] = useState({ full_name: "", department: "", job_title: "", phone: "", employee_id: "", avatar_url: "" });
  const [saving, setSaving] = useState(false);
  const [pwd, setPwd] = useState({ current: "", a: "", b: "" });
  const [pwdSaving, setPwdSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setForm({
        full_name: profile.full_name ?? "",
        department: profile.department ?? "",
        job_title: profile.job_title ?? "",
        phone: profile.phone ?? "",
        employee_id: profile.employee_id ?? "",
        avatar_url: profile.avatar_url ?? "",
      });
    }
  }, [profile]);

  const save = async () => {
    if (!user) return;
    setSaving(true);
    try {
      await ApiClient.fetch("/auth/profile", {
        method: "PUT",
        body: JSON.stringify(form),
      });
      toast.success(ar ? "تم الحفظ" : "Saved");
      qc.invalidateQueries({ queryKey: ["profile", user.id] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setSaving(false);
    }
  };

  const changePassword = async () => {
    if (!pwd.current) { toast.error(ar ? "أدخل كلمة المرور الحالية" : "Enter your current password"); return; }
    if (pwd.a.length < 12) { toast.error(ar ? "12 حرفًا على الأقل" : "Min 12 characters"); return; }
    if (pwd.a !== pwd.b) { toast.error(ar ? "كلمتا المرور غير متطابقتين" : "Passwords do not match"); return; }
    setPwdSaving(true);
    try {
      const data = await ApiClient.fetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: pwd.current, new_password: pwd.a }),
      });
      // The change revokes the old token; adopt the replacement the server returns.
      if (data.access_token) {
        ApiClient.setToken(data.access_token);
      }
      toast.success(ar ? "تم تحديث كلمة المرور" : "Password updated");
      setPwd({ current: "", a: "", b: "" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setPwdSaving(false);
    }
  };

  const initials = (form.full_name || user?.email || "?").slice(0, 2).toUpperCase();

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{ar ? "الملف الشخصي" : "Profile"}</h1>
        <p className="text-sm text-muted-foreground">
          {ar ? "إدارة بياناتك وكلمة المرور." : "Manage your account details and password."}
        </p>
      </div>

      {isLoading ? (
        <div className="p-10 grid place-items-center"><Loader2 className="size-5 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base flex items-center gap-2"><UserIcon className="size-4" />{ar ? "المعلومات" : "Information"}</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-4">
                <Avatar className="size-16">
                  <AvatarImage src={form.avatar_url || undefined} />
                  <AvatarFallback>{initials}</AvatarFallback>
                </Avatar>
                <div>
                  <p className="font-medium">{user?.email}</p>
                  <div className="flex gap-1.5 flex-wrap mt-1">
                    {perms.roles.map((r) => (
                      <Badge key={r} variant="outline" className="capitalize">{r.replace("_", " ")}</Badge>
                    ))}
                  </div>
                </div>
              </div>

              <div className="grid sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label>{ar ? "الاسم الكامل" : "Full name"}</Label>
                  <Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "المسمى الوظيفي" : "Job title"}</Label>
                  <Input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "القسم" : "Department"}</Label>
                  <Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "رقم الهاتف" : "Phone"}</Label>
                  <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+20…" />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "الرقم الوظيفي" : "Employee ID"}</Label>
                  <Input value={form.employee_id} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "رابط الصورة" : "Avatar URL"}</Label>
                  <Input value={form.avatar_url} onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} placeholder="https://…" />
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={save} disabled={saving}>
                  {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  {ar ? "حفظ" : "Save changes"}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-base flex items-center gap-2"><KeyRound className="size-4" />{ar ? "كلمة المرور" : "Password"}</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid sm:grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <Label>{ar ? "كلمة المرور الحالية" : "Current password"}</Label>
                  <Input type="password" autoComplete="current-password" value={pwd.current} onChange={(e) => setPwd({ ...pwd, current: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "كلمة المرور الجديدة" : "New password"}</Label>
                  <Input type="password" autoComplete="new-password" value={pwd.a} onChange={(e) => setPwd({ ...pwd, a: e.target.value })} />
                </div>
                <div className="space-y-1.5">
                  <Label>{ar ? "تأكيد كلمة المرور" : "Confirm password"}</Label>
                  <Input type="password" autoComplete="new-password" value={pwd.b} onChange={(e) => setPwd({ ...pwd, b: e.target.value })} />
                </div>
              </div>
              <div className="flex justify-end">
                <Button variant="outline" onClick={changePassword} disabled={pwdSaving || !pwd.a}>
                  {pwdSaving ? <Loader2 className="size-4 animate-spin" /> : <KeyRound className="size-4" />}
                  {ar ? "تحديث كلمة المرور" : "Update password"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
