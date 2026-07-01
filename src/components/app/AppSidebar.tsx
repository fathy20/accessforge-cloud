import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  FolderKanban,
  Upload,
  Search,
  ListTodo,
  Users2,
  ShieldCheck,
  Settings,
  Plane,
  FileSearch,
  Stamp,
  ListChecks,
  CheckCircle,
  GaugeCircle,
  FileBarChart,
  Layers,
  BookCopy,
  Mailbox,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePermissions } from "@/lib/auth/use-permissions";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  moduleKey?: string;
  adminOnly?: boolean;
}

const mainNav: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/uploads", label: "Uploads", icon: Upload },
  { to: "/search", label: "Search", icon: Search },
  { to: "/jobs", label: "Jobs", icon: ListTodo },
  { to: "/reports", label: "Reports", icon: FileBarChart },
];

const moduleNav: NavItem[] = [
  { to: "/modules", label: "All Modules", icon: LayoutDashboard },
  { to: "/modules/task-extractor", label: "Task Extractor",         icon: FileSearch,  moduleKey: "task_extractor" },
  { to: "/modules/task-stamping",  label: "Task Stamping",          icon: Stamp,       moduleKey: "task_stamping" },
  { to: "/modules/effectivity",    label: "EFFECTIVITY / TCM",      icon: ListChecks,  moduleKey: "effectivity" },
  { to: "/modules/check-control",  label: "Check Control",          icon: CheckCircle, moduleKey: "check_control" },
  { to: "/modules/utilization",    label: "Utilization",            icon: GaugeCircle, moduleKey: "utilization" },
  { to: "/modules/cmp-tcm",        label: "CMP / TCM Tasks",        icon: Layers,      moduleKey: "cmp_tcm" },
  { to: "/modules/cover-merge",    label: "Cover Merge",            icon: BookCopy,    moduleKey: "cover_merge" },
  { to: "/modules/mail-merge",     label: "Mail Merge (Covering)",  icon: Mailbox,     moduleKey: "mail_merge" },
];

const adminNav: NavItem[] = [
  { to: "/admin/users",    label: "Users & Roles", icon: Users2,      adminOnly: true },
  { to: "/admin/audit",    label: "Audit Log",     icon: ShieldCheck, adminOnly: true },
  { to: "/admin/settings", label: "Settings",      icon: Settings,    adminOnly: true },
];

export function AppSidebar() {
  const perms = usePermissions();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const renderGroup = (title: string, items: NavItem[]) => {
    const filtered = items.filter((i) => {
      if (i.adminOnly) return perms.isAdmin;
      if (i.moduleKey) return perms.canViewModule(i.moduleKey);
      return true;
    });
    if (!filtered.length) return null;
    return (
      <div className="px-3 py-2">
        <p className="px-2 mb-1.5 text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50">
          {title}
        </p>
        <nav className="flex flex-col gap-0.5">
          {filtered.map((item) => {
            const active = pathname === item.to || pathname.startsWith(item.to + "/");
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  "flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    );
  };

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
      <div className="px-5 py-5 flex items-center gap-2.5 border-b border-sidebar-border">
        <div className="size-9 rounded-lg brand-gradient grid place-items-center">
          <Plane className="size-4 text-primary-foreground" />
        </div>
        <div className="leading-tight">
          <p className="font-bold tracking-tight">REDSEA</p>
          <p className="text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50">
            Aviation Toolkit
          </p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {renderGroup("Workspace", mainNav)}
        {renderGroup("Modules", moduleNav)}
        {renderGroup("Administration", adminNav)}
      </div>
      <div className="px-4 py-3 border-t border-sidebar-border text-[11px] text-sidebar-foreground/50">
        v0.1 · Phase 1
      </div>
    </aside>
  );
}
