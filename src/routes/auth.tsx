import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { z } from "zod";
import { Plane, Loader2, ArrowLeft, CheckCircle2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";
import { lovable } from "@/integrations/lovable";
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

async function checkStatusAndRoute(userId: string, navigate: ReturnType<typeof useNavigate>) {
  const { data } = await supabase
    .from("profiles")
    .select("status")
    .eq("id", userId)
    .maybeSingle();
  if (data?.status === "pending") {
    await supabase.auth.signOut();
    toast.info("Your account is awaiting administrator approval.", { duration: 6000 });
    return false;
  }
  if (data?.status === "suspended") {
    await supabase.auth.signOut();
    toast.error("Your account has been suspended. Please contact an administrator.");
    return false;
  }
  navigate({ to: "/dashboard", replace: true });
  return true;
}

function AuthPage() {
  const navigate = useNavigate();
  const search = Route.useSearch();
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">(search.mode ?? "signin");
  const [signedUp, setSignedUp] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
      if (data.session) await checkStatusAndRoute(data.session.user.id, navigate);
    });
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
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            emailRedirectTo: `${window.location.origin}/auth`,
            data: { full_name: fullName },
          },
        });
        if (error) throw error;
        // If email confirmation is required, session is null.
        if (data.session) {
          // First user (auto super_admin + active) or edge case: check status.
          await checkStatusAndRoute(data.session.user.id, navigate);
        }
        setSignedUp(true);
      } else {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
        if (data.session) await checkStatusAndRoute(data.session.user.id, navigate);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const google = async () => {
    setLoading(true);
    const result = await lovable.auth.signInWithOAuth("google", {
      redirect_uri: window.location.origin + "/auth",
    });
    if (result.error) {
      toast.error(result.error.message || "Google sign-in failed");
      setLoading(false);
      return;
    }
    if (result.redirected) return;
    const { data } = await supabase.auth.getSession();
    if (data.session) await checkStatusAndRoute(data.session.user.id, navigate);
    setLoading(false);
  };

  if (signedUp) {
    return (
      <div className="dark min-h-screen w-full surface-gradient flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-2xl border border-border bg-card panel-shadow p-8 text-center">
          <div className="size-14 rounded-full bg-success/10 grid place-items-center mx-auto mb-4">
            <CheckCircle2 className="size-7 text-success" />
          </div>
          <h1 className="text-xl font-semibold">Account created</h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Thank you for signing up to REDSEA. Your account is now awaiting administrator approval.
            You'll be able to sign in once activated.
          </p>
          <Link
            to="/"
            className="mt-6 inline-flex items-center gap-2 text-sm text-primary hover:underline"
          >
            <ArrowLeft className="size-4" /> Back to home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="dark min-h-screen w-full surface-gradient flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors"
        >
          <ArrowLeft className="size-4" /> Back to home
        </Link>

        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="size-12 rounded-xl brand-gradient grid place-items-center glow-ring">
            <Plane className="size-6 text-primary-foreground" />
          </div>
          <div>
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

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase tracking-wider">
              <span className="bg-card px-2 text-muted-foreground">or</span>
            </div>
          </div>

          <Button type="button" variant="outline" className="w-full" onClick={google} disabled={loading}>
            <GoogleIcon /> Continue with Google
          </Button>
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

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.6 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.5 6.1 29.6 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.4-.4-3.5z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34.5 6.1 29.6 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.4 0 10.3-2.1 14-5.4l-6.5-5.5C29.4 34.7 26.8 36 24 36c-5.3 0-9.7-3.4-11.3-8.1l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.3-4.3 5.7l6.5 5.5C40.6 35.6 44 30.3 44 24c0-1.2-.1-2.4-.4-3.5z"/>
    </svg>
  );
}
