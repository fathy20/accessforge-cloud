import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { ApiClient } from "@/lib/apiClient";
import { authMeQuery } from "@/lib/auth/use-auth";
import { AppLayout } from "@/components/app/AppLayout";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  beforeLoad: async ({ context }) => {
    const token = ApiClient.getToken();
    if (!token) {
      throw redirect({ to: "/auth" });
    }

    try {
      // ensureQueryData reuses the cached user for five minutes, so moving
      // between pages no longer costs a /auth/me round-trip each time.
      const user = await context.queryClient.ensureQueryData(authMeQuery);
      if (!user?.id) throw new Error("unauthenticated");
      return { user };
    } catch {
      ApiClient.clearToken();
      context.queryClient.removeQueries({ queryKey: authMeQuery.queryKey });
      throw redirect({ to: "/auth" });
    }
  },
  component: () => (
    <AppLayout>
      <Outlet />
    </AppLayout>
  ),
});
