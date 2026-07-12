import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { ApiClient } from "@/lib/apiClient";
import { AppLayout } from "@/components/app/AppLayout";

export const Route = createFileRoute("/_authenticated")({
  ssr: false,
  beforeLoad: async () => {
    const token = ApiClient.getToken();
    if (!token) {
      throw redirect({ to: "/auth" });
    }

    try {
      const user = await ApiClient.fetch("/auth/me");
      if (!user || !user.id) {
        ApiClient.clearToken();
        throw redirect({ to: "/auth" });
      }
      return { user };
    } catch {
      ApiClient.clearToken();
      throw redirect({ to: "/auth" });
    }
  },
  component: () => (
    <div className="dark">
      <AppLayout>
        <Outlet />
      </AppLayout>
    </div>
  ),
});
