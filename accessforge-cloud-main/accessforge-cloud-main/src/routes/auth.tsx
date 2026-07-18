import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { Plane, Loader2, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";

const searchSchema = z.object({
  mode: z.enum(["signin", "signup"]).optional(),
});

export const Route = createFileRoute("/auth")({
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      { title: "Sign in · REDSEA Toolkit" },
      { name: "description", content: "Sign in to the REDSEA Aviation Maintenance Toolkit." },
    ],
  }),
  component: AuthPage,
});

const emailSchema = z.string().trim().email("Invalid email").max(255);
const passwordSchema = z.string().min(8, "Min 8 characters").max(72);

import { ApiClient } from "@/lib/apiClient";

async function checkStatusAndRoute(navigate: ReturnType<typeof useNavigate>) {
  try {
    const user = await ApiClient.fetch("/auth/me");
    if (user && user.id) {
      navigate({ to: "/dashboard", replace: true });
      return true;
    }
  } catch (e) {
    ApiClient.clearToken();
  }
  return false;
}

function AuthPage() {
  const navigate = useNavigate();
  const search = Route.useSearch();
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">(search.mode ?? "signin");

  useEffect(() => {
    if (ApiClient.getToken()) {
      checkStatusAndRoute(navigate);
    }
  }, [navigate]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      emailSchema.parse(email);
      passwordSchema.parse(password);
    } catch (err) {
      if (err instanceof z.ZodError) {
        toast.error(err.issues[0].message);
        return;
      }
    }

    setLoading(true);
    try {
      if (mode === "signup") {
        const data = await ApiClient.fetch("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password, full_name: fullName || "User" }),
        });
        if (data.access_token) {
          ApiClient.setToken(data.access_token);
        }
        toast.success("Account created successfully!");
        navigate({ to: "/dashboard", replace: true });
      } else {
        const data = await ApiClient.fetch("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        if (data.access_token) {
          ApiClient.setToken(data.access_token);
        }
        toast.success("Signed in successfully!");
        navigate({ to: "/dashboard", replace: true });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const isDev = import.meta.env.DEV;

  const demoLogin = async () => {
    setLoading(true);
    try {
      // Offline local mode fallback quick sign in
      const data = await ApiClient.fetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: "admin@redsea.com", password: "password" }),
      });
      if (data.access_token) {
        ApiClient.setToken(data.access_token);
      }
      toast.success("Signed in with demo account!");
      navigate({ to: "/dashboard", replace: true });
    } catch (err) {
      toast.error("Demo sign in failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      className="dark min-h-screen w-full flex items-center justify-center p-4 relative"
      style={{
        backgroundImage: "url('/login_bg.jpg')",
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      <div className="absolute inset-0 bg-background/80 backdrop-blur-sm" />
      <div className="w-full max-w-md relative z-10">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
        >
          <ArrowLeft className="size-4" /> Back to home
        </Link>

        <div className="flex flex-col items-center justify-center gap-3 mb-8">
          <div className="size-20 rounded-2xl bg-white grid place-items-center glow-ring overflow-hidden p-2">
            <img src="/logo.png" alt="REDSEA Logo" className="w-full h-full object-contain" />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">REDSEA</h1>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
              Aviation Toolkit
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card panel-shadow p-6">
          <Tabs value={mode} onValueChange={(v) => setMode(v as "signin" | "signup")}>
            <TabsList className="grid grid-cols-2 w-full">
              <TabsTrigger value="signin">Sign in</TabsTrigger>
              <TabsTrigger value="signup">Sign up</TabsTrigger>
            </TabsList>

            <TabsContent value="signin" className="mt-6">
              <form onSubmit={submit} className="space-y-4">
                <Field label="Email" id="email" type="email" value={email} onChange={setEmail} />
                <Field
                  label="Password"
                  id="password"
                  type="password"
                  value={password}
                  onChange={setPassword}
                />
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading && <Loader2 className="size-4 animate-spin" />}
                  Sign in
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="signup" className="mt-6">
              <form onSubmit={submit} className="space-y-4">
                <Field label="Full name" id="full_name" value={fullName} onChange={setFullName} />
                <Field
                  label="Email"
                  id="email-su"
                  type="email"
                  value={email}
                  onChange={setEmail}
                />
                <Field
                  label="Password"
                  id="password-su"
                  type="password"
                  value={password}
                  onChange={setPassword}
                />
                <p className="text-xs text-muted-foreground">
                  New accounts require administrator approval before first sign-in.
                </p>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading && <Loader2 className="size-4 animate-spin" />}
                  Create account
                </Button>
              </form>
            </TabsContent>
          </Tabs>

          {isDev && (
            <>
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase tracking-wider">
                  <span className="bg-card px-2 text-muted-foreground">dev only</span>
                </div>
              </div>

              <Button type="button" variant="outline" className="w-full" onClick={demoLogin} disabled={loading}>
                🧪 Quick Demo Login (Admin)
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  id,
  type = "text",
  value,
  onChange,
}: {
  label: string;
  id: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
        autoComplete={type === "password" ? "current-password" : "email"}
      />
    </div>
  );
}

