import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { useState } from "react";
import { supabase } from "@/integrations/supabase/client";
import {
  listUsers,
  setUserRole,
  setUserStatus,
  deleteUser,
  sendPasswordReset,
  inviteUser,
} from "@/lib/admin.functions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Users2,
  UserPlus,
  Search as SearchIcon,
  CheckCircle2,
  Ban,
  KeyRound,
  Trash2,
  Mail,
} from "lucide-react";

export const Route = createFileRoute("/_authenticated/admin/users")({
  head: () => ({ meta: [{ title: "Users & Roles · REDSEA Admin" }] }),
  component: UsersAdmin,
});

const ROLES = ["super_admin", "admin", "engineer", "viewer", "guest"] as const;
type AppRole = (typeof ROLES)[number];

const statusTone: Record<string, string> = {
  active: "bg-success/15 text-success border-success/30",
  pending: "bg-warning/15 text-warning border-warning/30",
  suspended: "bg-destructive/15 text-destructive border-destructive/30",
};

function UsersAdmin() {
  const qc = useQueryClient();
  const list = useServerFn(listUsers);
  const setRoleFn = useServerFn(setUserRole);
  const setStatusFn = useServerFn(setUserStatus);
  const deleteFn = useServerFn(deleteUser);
  const resetFn = useServerFn(sendPasswordReset);
  const inviteFn = useServerFn(inviteUser);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<AppRole>("engineer");

  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users-v2"],
    queryFn: () => list(),
  });

  const { data: modules } = useQuery({
    queryKey: ["modules-list"],
    queryFn: async () => {
      const { data } = await supabase.from("modules").select("id, key, name").order("sort_order");
      return data ?? [];
    },
  });

  const { data: access } = useQuery({
    queryKey: ["module-access-all"],
    queryFn: async () => {
      const { data } = await supabase.from("module_access").select("user_id, module_id, can_view, can_run");
      const map: Record<string, Record<string, { v: boolean; r: boolean }>> = {};
      for (const a of data ?? []) {
        (map[a.user_id] ||= {})[a.module_id] = { v: a.can_view, r: a.can_run };
      }
      return map;
    },
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["admin-users-v2"] });
    qc.invalidateQueries({ queryKey: ["module-access-all"] });
  };

  const roleMut = useMutation({
    mutationFn: (v: { userId: string; role: AppRole }) => setRoleFn({ data: v }),
    onSuccess: () => { toast.success("Role updated"); invalidate(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const statusMut = useMutation({
    mutationFn: (v: { userId: string; status: "active" | "suspended" | "pending" }) =>
      setStatusFn({ data: v }),
    onSuccess: (_, v) => {
      toast.success(v.status === "active" ? "User activated" : v.status === "suspended" ? "User suspended" : "Set to pending");
      invalidate();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const deleteMut = useMutation({
    mutationFn: (userId: string) => deleteFn({ data: { userId } }),
    onSuccess: () => { toast.success("User deleted"); invalidate(); },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const resetMut = useMutation({
    mutationFn: (email: string) =>
      resetFn({ data: { email, redirectTo: `${window.location.origin}/reset-password` } }),
    onSuccess: () => toast.success("Password reset email sent"),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const inviteMut = useMutation({
    mutationFn: () =>
      inviteFn({
        data: {
          email: inviteEmail,
          role: inviteRole,
          redirectTo: `${window.location.origin}/auth`,
        },
      }),
    onSuccess: () => {
      toast.success(`Invitation sent to ${inviteEmail}`);
      setInviteOpen(false);
      setInviteEmail("");
      setInviteRole("engineer");
      invalidate();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const toggleAccess = useMutation({
    mutationFn: async (v: {
      userId: string; moduleId: string; field: "can_view" | "can_run"; value: boolean;
      current: { v: boolean; r: boolean } | undefined;
    }) => {
      const can_view = v.field === "can_view" ? v.value : v.current?.v ?? true;
      const can_run = v.field === "can_run" ? v.value : v.current?.r ?? false;
      const { error } = await supabase
        .from("module_access")
        .upsert({ user_id: v.userId, module_id: v.moduleId, can_view, can_run }, { onConflict: "user_id,module_id" });
      if (error) throw error;
    },
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(e instanceof Error ? e.message : "Failed"),
  });

  const filtered = (users ?? []).filter((u) => {
    if (statusFilter !== "all" && u.status !== statusFilter) return false;
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      u.full_name?.toLowerCase().includes(q) ||
      u.email?.toLowerCase().includes(q) ||
      u.department?.toLowerCase().includes(q) ||
      u.employee_id?.toLowerCase().includes(q)
    );
  });

  const pendingCount = (users ?? []).filter((u) => u.status === "pending").length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <Users2 className="size-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold">Users &amp; Roles</h1>
            <p className="text-sm text-muted-foreground">
              Approve, manage roles, and set per-module access.
              {pendingCount > 0 && (
                <span className="ml-2">
                  <Badge className="bg-warning/15 text-warning border-warning/30" variant="outline">
                    {pendingCount} pending
                  </Badge>
                </span>
              )}
            </p>
          </div>
        </div>
        <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2"><UserPlus className="size-4" /> Invite user</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Invite a new user</DialogTitle>
              <DialogDescription>
                They'll receive an email invitation and their account will be activated automatically.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label htmlFor="invite-email">Email</Label>
                <Input
                  id="invite-email" type="email" placeholder="engineer@company.com"
                  value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="invite-role">Role</Label>
                <Select value={inviteRole} onValueChange={(v) => setInviteRole(v as AppRole)}>
                  <SelectTrigger id="invite-role"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map((r) => (
                      <SelectItem key={r} value={r} className="capitalize">{r.replace("_", " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setInviteOpen(false)}>Cancel</Button>
              <Button
                onClick={() => inviteMut.mutate()}
                disabled={!inviteEmail || inviteMut.isPending}
              >
                Send invitation
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-64 max-w-md">
          <SearchIcon className="size-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search name, email, department…" value={query}
            onChange={(e) => setQuery(e.target.value)} className="pl-9" />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="suspended">Suspended</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : (
        <div className="space-y-4">
          {filtered.map((u) => (
            <Card key={u.id}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <CardTitle className="text-base">{u.full_name ?? "Unnamed user"}</CardTitle>
                      <Badge
                        variant="outline"
                        className={statusTone[u.status] ?? ""}
                      >
                        {u.status}
                      </Badge>
                      {u.roles.length === 0 ? (
                        <Badge variant="outline">no role</Badge>
                      ) : (
                        u.roles.map((r) => (
                          <Badge key={r} variant="secondary" className="capitalize">
                            {r.replace("_", " ")}
                          </Badge>
                        ))
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground flex items-center gap-1.5 mt-1">
                      <Mail className="size-3.5" /> {u.email ?? "no email"}
                    </p>
                    {u.department && (
                      <p className="text-xs text-muted-foreground mt-0.5">
                        {u.department} {u.job_title ? `· ${u.job_title}` : ""}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <Select
                      value={u.roles[0] ?? ""}
                      onValueChange={(v) => roleMut.mutate({ userId: u.id, role: v as AppRole })}
                    >
                      <SelectTrigger className="w-36"><SelectValue placeholder="Role" /></SelectTrigger>
                      <SelectContent>
                        {ROLES.map((r) => (
                          <SelectItem key={r} value={r} className="capitalize">
                            {r.replace("_", " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {u.status !== "active" ? (
                      <Button size="sm" variant="default" onClick={() => statusMut.mutate({ userId: u.id, status: "active" })}
                        className="gap-1.5"><CheckCircle2 className="size-4" /> Activate</Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => statusMut.mutate({ userId: u.id, status: "suspended" })}
                        className="gap-1.5"><Ban className="size-4" /> Suspend</Button>
                    )}
                    {u.email && (
                      <Button size="sm" variant="outline" onClick={() => resetMut.mutate(u.email!)}
                        className="gap-1.5" title="Send password reset email">
                        <KeyRound className="size-4" />
                      </Button>
                    )}
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button size="sm" variant="outline" className="gap-1.5 text-destructive hover:text-destructive">
                          <Trash2 className="size-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete this user?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This permanently removes {u.full_name ?? u.email} and all their data. This cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => deleteMut.mutate(u.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Module access</p>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2">
                  {(modules ?? []).map((m) => {
                    const cur = access?.[u.id]?.[m.id];
                    return (
                      <div key={m.id} className="rounded-lg border border-border p-3 flex flex-col gap-2">
                        <p className="text-sm font-medium truncate">{m.name}</p>
                        <div className="flex gap-4 text-xs">
                          <label className="flex items-center gap-1.5">
                            <Checkbox checked={cur?.v ?? false}
                              onCheckedChange={(v) => toggleAccess.mutate({ userId: u.id, moduleId: m.id, field: "can_view", value: Boolean(v), current: cur })} />
                            View
                          </label>
                          <label className="flex items-center gap-1.5">
                            <Checkbox checked={cur?.r ?? false}
                              onCheckedChange={(v) => toggleAccess.mutate({ userId: u.id, moduleId: m.id, field: "can_run", value: Boolean(v), current: cur })} />
                            Run
                          </label>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          ))}
          {filtered.length === 0 && (
            <Card>
              <CardContent className="p-6 text-sm text-muted-foreground">No users match your filter.</CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
