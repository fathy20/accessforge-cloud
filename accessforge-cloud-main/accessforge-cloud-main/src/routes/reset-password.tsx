import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiClient } from "@/lib/apiClient";
import { toast } from "sonner";
import { Plane, Loader2 } from "lucide-react";

export const Route = createFileRoute("/reset-password")({
  component: ResetPasswordPage,
  head: () => ({ meta: [{ title: "Reset password · REDSEA" }] }),
});

function ResetPasswordPage() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password.length < 8) return toast.error("Min 8 characters");
    setLoading(true);
    try {
      await ApiClient.fetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ new_password: password }),
      });
      toast.success("Password updated");
      navigate({ to: "/dashboard", replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to update password");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dark min-h-screen surface-gradient grid place-items-center p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-2xl border border-border bg-card p-6 panel-shadow space-y-4"
      >
        <div className="flex items-center gap-2 mb-2">
          <Plane className="size-5 text-primary" />
          <h1 className="font-semibold">Set a new password</h1>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="new-pw">New password</Label>
          <Input
            id="new-pw"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading && <Loader2 className="size-4 animate-spin" />} Update password
        </Button>
      </form>
    </div>
  );
}
