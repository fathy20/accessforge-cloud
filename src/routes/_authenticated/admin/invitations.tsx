import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { toast } from "sonner";
import { Mail, Trash2, Loader2, Send } from "lucide-react";
import {
  listInvitations,
  revokeInvitation,
  inviteUser,
} from "@/lib/admin.functions";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

export const Route = createFileRoute("/_authenticated/admin/invitations")({
  head: () => ({ meta: [{ title: "Invitations · REDSEA Admin" }] }),
  component: InvitationsPage,
});

function InvitationsPage() {
  const qc = useQueryClient();
  const list = useServerFn(listInvitations);
  const revoke = useServerFn(revokeInvitation);
  const invite = useServerFn(inviteUser);

  const { data, isLoading } = useQuery({
    queryKey: ["invitations"],
    queryFn: () => list(),
  });

  const [email, setEmail] = useState("");
  const [role, setRole] = useState("engineer");
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!email) return;
    setBusy(true);
    try {
      await invite({ data: { email, role, redirectTo: window.location.origin + "/auth" } });
      toast.success("Invitation sent");
      setEmail("");
      qc.invalidateQueries({ queryKey: ["invitations"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); }
  };

  const del = async (id: string) => {
    try {
      await revoke({ data: { id } });
      toast.success("Revoked");
      qc.invalidateQueries({ queryKey: ["invitations"] });
    } catch (e) { toast.error(e instanceof Error ? e.message : "Failed"); }
  };

  const statusOf = (inv: { accepted_at: string | null; expires_at: string | null }) => {
    if (inv.accepted_at) return { label: "Accepted", tone: "success" as const };
    if (inv.expires_at && new Date(inv.expires_at) < new Date()) return { label: "Expired", tone: "muted" as const };
    return { label: "Pending", tone: "warning" as const };
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Mail className="size-5 text-primary" /> Invitations
        </h1>
        <p className="text-sm text-muted-foreground">Send and manage email invitations.</p>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Send new invitation</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-56">
              <label className="text-xs text-muted-foreground">Email</label>
              <Input type="email" placeholder="user@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="w-44">
              <label className="text-xs text-muted-foreground">Role</label>
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="guest">Guest</SelectItem>
                  <SelectItem value="viewer">Viewer</SelectItem>
                  <SelectItem value="engineer">Engineer</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                  <SelectItem value="super_admin">Super admin</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button onClick={send} disabled={busy || !email}>
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
              Send invite
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">All invitations ({data?.length ?? 0})</CardTitle></CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Loading…</p>
          ) : !data?.length ? (
            <p className="p-6 text-sm text-muted-foreground text-center">No invitations yet.</p>
          ) : (
            <div className="divide-y divide-border text-sm">
              {data.map((inv) => {
                const s = statusOf(inv);
                return (
                  <div key={inv.id} className="px-4 py-3 flex items-center gap-3 flex-wrap">
                    <span className="font-medium">{inv.email}</span>
                    <Badge variant="outline" className="capitalize">{inv.role.replace("_", " ")}</Badge>
                    <Badge
                      variant="outline"
                      className={
                        s.tone === "success" ? "text-emerald-600 border-emerald-600/40" :
                        s.tone === "muted" ? "text-muted-foreground" :
                        "text-amber-600 border-amber-600/40"
                      }
                    >{s.label}</Badge>
                    <span className="text-xs text-muted-foreground ml-auto">
                      {new Date(inv.created_at).toLocaleString()}
                    </span>
                    {!inv.accepted_at && (
                      <Button size="sm" variant="ghost" onClick={() => del(inv.id)}>
                        <Trash2 className="size-4 text-destructive" />
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
