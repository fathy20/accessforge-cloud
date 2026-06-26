import { createFileRoute } from "@tanstack/react-router";
import { PlaceholderPage } from "@/components/app/PlaceholderPage";

export const Route = createFileRoute("/_authenticated/profile")({
  head: () => ({ meta: [{ title: "Profile · REDSEA" }] }),
  component: () => (
    <PlaceholderPage
      title="Profile"
      description="Manage your account details and preferences."
    />
  ),
});
