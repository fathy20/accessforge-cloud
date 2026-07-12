import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { supabase } from "@/integrations/supabase/client";
import { AppLayout } from "@/components/app/AppLayout";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  beforeLoad: async () => {
    const { data, error } = await supabase.auth.getUser();
    if (error || !data.user) throw redirect({ to: "/auth" });

    // Gate pending/suspended accounts
    const { data: profile } = await supabase
      .from("profiles")
      .select("status")
      .eq("id", data.user.id)
      .maybeSingle();

    if (profile?.status === "pending" || profile?.status === "suspended") {
      await supabase.auth.signOut();
      throw redirect({ to: "/auth" });
    }

    // Update last_seen (best-effort, no await block on failure)
    supabase
      .from("profiles")
      .update({ last_seen_at: new Date().toISOString() })
      .eq("id", data.user.id)
      .then(() => void 0);

    return { user: data.user };
  },
  component: () => (
    <div className="dark">
      <AppLayout>
        <Outlet />
      </AppLayout>
    </div>
  ),
});
