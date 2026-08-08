import { FlightPathBackground } from "@/components/FlightPathBackground/FlightPathBackground";
import { DEFAULT_MODULE_ICON, MODULE_ICONS } from "@/lib/modules/icons";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  ShieldCheck,
  Zap,
  Users,
  Database,
  ArrowRight,
} from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "REDSEA · Aviation Maintenance Toolkit" },
      {
        name: "description",
        content:
          "Professional aviation maintenance platform: extract, stamp, index, and merge maintenance documents with role-based collaboration, jobs pipeline, and secure storage.",
      },
      { property: "og:title", content: "REDSEA · Aviation Maintenance Toolkit" },
      {
        property: "og:description",
        content:
          "Extract, stamp, index, and merge aviation maintenance documents with role-based collaboration.",
      },
      { property: "og:type", content: "website" },
    ],
  }),
  component: LandingPage,
});

const modules = [
  { key: "task_extractor", title: "Task Extractor", desc: "Extract maintenance tasks from PDFs with OCR fallback." },
  { key: "task_stamping", title: "Task Stamping", desc: "Overlay tail number, station and date on every task page." },
  { key: "effectivity", title: "EFFECTIVITY / TCM", desc: "Normalize Excel/CSV effectivity data across fleets." },
  { key: "check_control", title: "Check Control", desc: "Expand check relations and validate maintenance packages." },
  { key: "utilization", title: "Utilization", desc: "Compute hash-verified utilization rows for audit trails." },
  { key: "cmp_tcm", title: "CMP / TCM Tasks", desc: "Index and cross-reference CMP tasks with TCM entries." },
  { key: "cover_merge", title: "Cover Merge", desc: "Merge cover pages onto task cards, cleanly and reproducibly." },
  { key: "mail_merge", title: "Mail Merge", desc: "Populate DOCX templates with per-task merge fields." },
];

function RegistryModuleIcon({ moduleKey }: { moduleKey: string }) {
  const Icon = MODULE_ICONS[moduleKey] ?? DEFAULT_MODULE_ICON;
  return <Icon className="size-5 text-primary-foreground" />;
}

const features = [
  {
    icon: ShieldCheck,
    title: "Role-based Access",
    desc: "Fine-grained permissions per module — view or run — controlled by admins.",
  },
  {
    icon: Zap,
    title: "Async Job Pipeline",
    desc: "Heavy processing runs on a Python worker with real-time progress updates.",
  },
  {
    icon: Users,
    title: "Team Management",
    desc: "Invite engineers by email, approve pending accounts, and manage their access.",
  },
  {
    icon: Database,
    title: "Secure Storage",
    desc: "Signed, private buckets for every upload and generated output. RLS everywhere.",
  },
];

function LandingPage() {

  return (
    <div className="dark min-h-screen w-full bg-background text-foreground">
      {/* Header */}
      <header className="border-b border-border/60 bg-background/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="size-10 rounded-xl bg-white grid place-items-center p-1.5 shrink-0 shadow-sm border border-border/50">
              <img src="/logo.png" alt="REDSEA Logo" className="w-full h-full object-contain" />
            </div>
            <div className="leading-tight">
              <p className="font-bold tracking-tight text-lg">REDSEA</p>
              <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Aviation Toolkit
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link
              to="/auth"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Sign in
            </Link>
            <Link
              to="/auth"
              search={{ mode: "signup" } as never}
              className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md brand-gradient text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Get started <ArrowRight className="size-3.5" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <FlightPathBackground />
        <div className="absolute inset-0 bg-black/20 z-0 pointer-events-none" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(0,0,0,0.5)_0%,transparent_60%)] z-0 pointer-events-none" />
        <div className="relative max-w-7xl mx-auto px-6 py-24 md:py-32 text-center z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-border bg-card/40 text-xs text-muted-foreground mb-6 backdrop-blur-sm">
            <span className="size-1.5 rounded-full bg-success animate-pulse" />
            Production-ready · v0.1
          </div>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight max-w-4xl mx-auto drop-shadow-lg">
            Aviation maintenance,{" "}
            <span className="bg-clip-text text-transparent brand-gradient drop-shadow-sm">
              streamlined end-to-end
            </span>
          </h1>
          <p className="mt-6 text-lg text-muted-foreground max-w-2xl mx-auto drop-shadow-md">
            REDSEA turns your maintenance PDFs, task cards and effectivity sheets into a
            structured, searchable, auditable workflow — with role-based access and background
            processing that scales.
          </p>
          <div className="mt-10 flex items-center justify-center gap-3">
            <Link
              to="/auth"
              search={{ mode: "signup" } as never}
              className="inline-flex items-center gap-2 h-11 px-6 rounded-md brand-gradient text-primary-foreground font-medium hover:opacity-90 glow-ring transition-opacity shadow-lg shadow-primary/20"
            >
              Create your account <ArrowRight className="size-4" />
            </Link>
            <Link
              to="/auth"
              className="inline-flex items-center gap-2 h-11 px-6 rounded-md border border-border bg-card/40 backdrop-blur-sm text-foreground font-medium hover:bg-card/60 transition-colors"
            >
              Sign in
            </Link>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">
            New accounts are reviewed by an administrator before activation.
          </p>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-border/60">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="text-center mb-14">
            <p className="text-xs uppercase tracking-[0.2em] text-primary font-semibold mb-2">
              Built for operations
            </p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
              Everything your maintenance team needs
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {features.map((f) => (
              <div
                key={f.title}
                className="rounded-xl border border-border bg-card p-6 panel-shadow"
              >
                <div className="size-10 rounded-lg bg-primary/10 grid place-items-center mb-4">
                  <f.icon className="size-5 text-primary" />
                </div>
                <h3 className="font-semibold mb-1.5">{f.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Modules */}
      <section className="border-t border-border/60 bg-card/20">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="text-center mb-14">
            <p className="text-xs uppercase tracking-[0.2em] text-primary font-semibold mb-2">
              8 processing modules
            </p>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
              The full REDSEA toolkit, on the web
            </h2>
            <p className="mt-4 text-muted-foreground max-w-2xl mx-auto">
              Each module wraps the same battle-tested Python processing logic — now with a modern
              UI, job queue, and cloud storage.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {modules.map((m) => (
              <div
                key={m.key}
                className="group rounded-xl border border-border bg-card p-5 hover:border-primary/50 transition-colors"
              >
                <div className="size-10 rounded-lg brand-gradient grid place-items-center mb-3 group-hover:glow-ring transition-shadow">
                  <RegistryModuleIcon moduleKey={m.key} />
                </div>
                <h3 className="font-semibold text-sm mb-1">{m.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{m.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-border/60">
        <div className="max-w-4xl mx-auto px-6 py-24 text-center">
          <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
            Ready to modernize your maintenance workflow?
          </h2>
          <p className="mt-4 text-muted-foreground">
            Create an account and an administrator will activate your access. First-time setups get
            a full super-admin account automatically.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link
              to="/auth"
              search={{ mode: "signup" } as never}
              className="inline-flex items-center gap-2 h-11 px-6 rounded-md brand-gradient text-primary-foreground font-medium hover:opacity-90 glow-ring transition-opacity"
            >
              Get started <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/60 bg-background">
        <div className="max-w-7xl mx-auto px-6 py-8 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
          <div className="flex items-center gap-2">
            <div className="size-6 rounded bg-white grid place-items-center p-0.5 shrink-0 shadow-sm border border-border/50">
              <img src="/logo.png" alt="REDSEA Logo" className="w-full h-full object-contain" />
            </div>
            <span>REDSEA Aviation Toolkit · v0.1</span>
          </div>
          <p>&copy; {new Date().getFullYear()} REDSEA. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
