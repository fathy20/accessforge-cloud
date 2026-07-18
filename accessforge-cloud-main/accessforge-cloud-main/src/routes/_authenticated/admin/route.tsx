import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { ApiClient } from "@/lib/apiClient";

export const Route = createFileRoute("/_authenticated/admin")({
  beforeLoad: async () => {
    try {
      const user = await ApiClient.fetch<{ roles?: string[] }>("/auth/me");
      if (!user) throw redirect({ to: "/auth" });
      const roles: string[] = user.roles || [];
      const isAdmin = roles.some((r) => r === "admin" || r === "super_admin");
      if (!isAdmin) throw redirect({ to: "/dashboard" });
    } catch {
      throw redirect({ to: "/dashboard" });
    }
  },
  component: () => <Outlet />,
});
