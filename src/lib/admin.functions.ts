import { createServerFn } from "@tanstack/react-start";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { z } from "zod";

const roleEnum = z.enum(["super_admin", "admin", "engineer", "viewer", "guest"]);
const statusEnum = z.enum(["pending", "active", "suspended"]);

async function assertAdmin(supabase: any, userId: string) {
  const { data, error } = await supabase.rpc("is_admin", { _user_id: userId });
  if (error) throw new Error(error.message);
  if (!data) throw new Error("Forbidden: admin access required");
}

// ============================================================
// List users (with email, status, roles, modules)
// ============================================================
export const listUsers = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    await assertAdmin(context.supabase, context.userId);

    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

    const [{ data: profiles, error: pErr }, { data: roles }, { data: authUsersResp }] =
      await Promise.all([
        supabaseAdmin
          .from("profiles")
          .select(
            "id, full_name, avatar_url, status, phone, department, job_title, employee_id, last_seen_at, created_at",
          )
          .order("created_at", { ascending: false }),
        supabaseAdmin.from("user_roles").select("user_id, role"),
        supabaseAdmin.auth.admin.listUsers({ page: 1, perPage: 1000 }),
      ]);

    if (pErr) throw new Error(pErr.message);

    const emailById = new Map<string, string | undefined>();
    for (const u of authUsersResp?.users ?? []) emailById.set(u.id, u.email ?? undefined);

    const rolesByUser: Record<string, string[]> = {};
    for (const r of roles ?? []) (rolesByUser[r.user_id] ||= []).push(r.role);

    return (profiles ?? []).map((p) => ({
      ...p,
      email: emailById.get(p.id) ?? null,
      roles: rolesByUser[p.id] ?? [],
    }));
  });

// ============================================================
// Set user status (activate / suspend)
// ============================================================
export const setUserStatus = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { userId: string; status: string }) =>
    z.object({ userId: z.string().uuid(), status: statusEnum }).parse(data),
  )
  .handler(async ({ data, context }) => {
    await assertAdmin(context.supabase, context.userId);

    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { error } = await supabaseAdmin
      .from("profiles")
      .update({ status: data.status })
      .eq("id", data.userId);
    if (error) throw new Error(error.message);

    // Notify user
    const kind = data.status === "active" ? "account_activated" : "account_suspended";
    const title =
      data.status === "active"
        ? "Your account is now active"
        : data.status === "suspended"
          ? "Your account has been suspended"
          : "Your account is pending";
    await supabaseAdmin.from("notifications").insert({
      user_id: data.userId,
      kind,
      title,
      link: "/dashboard",
    });

    return { ok: true };
  });

// ============================================================
// Set role (single-role model)
// ============================================================
export const setUserRole = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { userId: string; role: string }) =>
    z.object({ userId: z.string().uuid(), role: roleEnum }).parse(data),
  )
  .handler(async ({ data, context }) => {
    await assertAdmin(context.supabase, context.userId);
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const del = await supabaseAdmin.from("user_roles").delete().eq("user_id", data.userId);
    if (del.error) throw new Error(del.error.message);
    const ins = await supabaseAdmin
      .from("user_roles")
      .insert({ user_id: data.userId, role: data.role });
    if (ins.error) throw new Error(ins.error.message);
    return { ok: true };
  });

// ============================================================
// Delete user (auth + cascades)
// ============================================================
export const deleteUser = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { userId: string }) =>
    z.object({ userId: z.string().uuid() }).parse(data),
  )
  .handler(async ({ data, context }) => {
    await assertAdmin(context.supabase, context.userId);
    if (data.userId === context.userId) throw new Error("You cannot delete your own account");
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { error } = await supabaseAdmin.auth.admin.deleteUser(data.userId);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

// ============================================================
// Send password-reset email
// ============================================================
export const sendPasswordReset = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { email: string; redirectTo?: string }) =>
    z.object({ email: z.string().email(), redirectTo: z.string().url().optional() }).parse(data),
  )
  .handler(async ({ data, context }) => {
    await assertAdmin(context.supabase, context.userId);
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { error } = await supabaseAdmin.auth.admin.generateLink({
      type: "recovery",
      email: data.email,
      options: { redirectTo: data.redirectTo },
    });
    if (error) throw new Error(error.message);
    return { ok: true };
  });

// ============================================================
// Invite user by email (uses Supabase Auth invite)
// ============================================================
export const inviteUser = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { email: string; role: string; redirectTo?: string }) =>
    z
      .object({
        email: z.string().email(),
        role: roleEnum,
        redirectTo: z.string().url().optional(),
      })
      .parse(data),
  )
  .handler(async ({ data, context }) => {
    await assertAdmin(context.supabase, context.userId);
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

    // Record invitation
    const token = crypto.randomUUID().replace(/-/g, "");
    await supabaseAdmin.from("user_invitations").insert({
      email: data.email,
      role: data.role,
      token,
      invited_by: context.userId,
    });

    // Send Supabase Auth invite (creates user + emails link)
    const { data: inv, error } = await supabaseAdmin.auth.admin.inviteUserByEmail(data.email, {
      redirectTo: data.redirectTo,
      data: { invited_role: data.role },
    });
    if (error) throw new Error(error.message);

    // Pre-assign role & activate so they can log in after accepting
    if (inv?.user?.id) {
      await supabaseAdmin.from("user_roles").delete().eq("user_id", inv.user.id);
      await supabaseAdmin
        .from("user_roles")
        .insert({ user_id: inv.user.id, role: data.role });
      await supabaseAdmin
        .from("profiles")
        .update({ status: "active" })
        .eq("id", inv.user.id);
    }

    return { ok: true };
  });

// ============================================================
// List invitations
// ============================================================
export const listInvitations = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    await assertAdmin(context.supabase, context.userId);
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { data, error } = await supabaseAdmin
      .from("user_invitations")
      .select("id, email, role, token, invited_by, accepted_at, expires_at, created_at")
      .order("created_at", { ascending: false })
      .limit(500);
    if (error) throw new Error(error.message);
    return data ?? [];
  });

// ============================================================
// Revoke (delete) invitation
// ============================================================
export const revokeInvitation = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { id: string }) => z.object({ id: z.string().uuid() }).parse(data))
  .handler(async ({ data, context }) => {
    await assertAdmin(context.supabase, context.userId);
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
    const { error } = await supabaseAdmin.from("user_invitations").delete().eq("id", data.id);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

// ============================================================
// Notifications helpers
// ============================================================
export const listMyNotifications = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { data, error } = await context.supabase
      .from("notifications")
      .select("id, kind, title, body, link, read_at, created_at")
      .eq("user_id", context.userId)
      .order("created_at", { ascending: false })
      .limit(30);
    if (error) throw new Error(error.message);
    return data ?? [];
  });

export const markNotificationRead = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((data: { id: string }) => z.object({ id: z.string().uuid() }).parse(data))
  .handler(async ({ data, context }) => {
    const { error } = await context.supabase
      .from("notifications")
      .update({ read_at: new Date().toISOString() })
      .eq("id", data.id)
      .eq("user_id", context.userId);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

export const markAllNotificationsRead = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    const { error } = await context.supabase
      .from("notifications")
      .update({ read_at: new Date().toISOString() })
      .eq("user_id", context.userId)
      .is("read_at", null);
    if (error) throw new Error(error.message);
    return { ok: true };
  });
