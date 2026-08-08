import { Link, useRouterState } from "@tanstack/react-router";
import {
  FileBarChart,
  FolderKanban,
  LayoutDashboard,
  ListTodo,
  Mailbox,
  Search,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { usePermissions } from "@/lib/auth/use-permissions";
import { DEFAULT_MODULE_ICON, MODULE_ICONS } from "@/lib/modules/icons";
import {
  getModuleLabel,
  getReadinessLabel,
  sortModules,
  type ModuleRegistryItem,
} from "@/lib/modules/registry";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

const mainNav: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/projects", label: "Projects", icon: FolderKanban },
  { to: "/uploads", label: "Uploads", icon: Upload },
  { to: "/search", label: "Search", icon: Search },
  { to: "/jobs", label: "Jobs", icon: ListTodo },
  { to: "/reports", label: "Reports", icon: FileBarChart },
];

export function AppSidebar() {
  const perms = usePermissions();
  const { t } = useI18n();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const isActive = (to: string) => pathname === to || pathname.startsWith(to + "/");

  const renderStaticGroup = (title: string, items: NavItem[]) => (
    <div className="px-3 py-2">
      <p className="px-2 mb-1.5 text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50">
        {title}
      </p>
      <nav className="flex flex-col gap-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.to}
              to={item.to as any}
              className={cn(
                "flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                isActive(item.to)
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

  const renderRegistryItem = (module: ModuleRegistryItem) => {
    const Icon = MODULE_ICONS[module.key] ?? DEFAULT_MODULE_ICON;
    const label = getModuleLabel(module, t);
    const readinessLabel = getReadinessLabel(module, t);
    const showReadiness = module.route === null || module.readiness !== "available";
    const itemClassName = cn(
      "flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
      module.route === null
        ? "text-sidebar-foreground/50 cursor-not-allowed"
        : isActive(module.route)
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
    );

    const content = (
      <>
        <Icon className="size-4 shrink-0" />
        <span className="truncate">{label}</span>
        {showReadiness && (
          <span className="ms-auto text-[9px] tracking-wide text-sidebar-foreground/50 text-end">
            {readinessLabel}
          </span>
        )}
      </>
    );

    if (module.route === null) {
      return (
        <div key={module.key} data-testid={`module-nav-${module.key}`} className={itemClassName} aria-disabled="true">
          {content}
        </div>
      );
    }

    return (
      <Link
        key={module.key}
        data-testid={`module-nav-${module.key}`}
        to={module.route as any}
        className={itemClassName}
      >
        {content}
      </Link>
    );
  };

  const renderRegistryGroup = (
    title: string,
    modules: ModuleRegistryItem[],
    options: { includeAllModules?: boolean; includeInvitations?: boolean } = {},
  ) => {
    const includeAllModules = options.includeAllModules ?? false;
    const includeInvitations = options.includeInvitations ?? false;
    if (!includeAllModules && !modules.length && !includeInvitations) return null;

    return (
      <div className="px-3 py-2">
        <p className="px-2 mb-1.5 text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50">
          {title}
        </p>
        <nav className="flex flex-col gap-0.5">
          {includeAllModules && (
            <Link
              to="/modules"
              className={cn(
                "flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                isActive("/modules")
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <LayoutDashboard className="size-4 shrink-0" />
              <span className="truncate">{t("nav.modules")}</span>
            </Link>
          )}
          {perms.loading && includeAllModules ? (
            <div className="px-2.5 py-2 text-xs text-sidebar-foreground/50" role="status">
              {t("mod.loading")}
            </div>
          ) : (
            modules.map(renderRegistryItem)
          )}
          {includeInvitations && (
            // Invitations is not a registry module yet; keep this static until the backend adds it.
            <Link
              to="/admin/invitations"
              className={cn(
                "flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm transition-colors",
                isActive("/admin/invitations")
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <Mailbox className="size-4 shrink-0" />
              <span className="truncate">Invitations</span>
            </Link>
          )}
        </nav>
      </div>
    );
  };

  const registryModules = sortModules(perms.modules);
  const workspaceModules = registryModules.filter(
    (module) => module.business_area === "maintenance" || module.business_area === "crew",
  );
  const adminModules = registryModules.filter((module) => module.business_area === "admin");

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border">
      <div className="px-5 py-5 flex items-center gap-3 border-b border-sidebar-border">
        <div className="size-10 rounded-xl bg-white grid place-items-center p-1.5 shrink-0 shadow-sm border border-border/50">
          <img src="/logo.png" alt="REDSEA Logo" className="w-full h-full object-contain" />
        </div>
        <div className="leading-tight flex flex-col flex-1">
          <p className="font-bold tracking-tight text-white text-lg">REDSEA</p>
          <p className="text-[10px] uppercase tracking-[0.2em] text-sidebar-foreground/50">
            Aviation Toolkit
          </p>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {renderStaticGroup("Workspace", mainNav)}
        {renderRegistryGroup(t("nav.modules"), workspaceModules, { includeAllModules: true })}
        {renderRegistryGroup(t("nav.admin"), adminModules, {
          includeInvitations: perms.isAdmin,
        })}
      </div>
      <div className="px-4 py-3 border-t border-sidebar-border text-[11px] text-sidebar-foreground/50">
        v0.1 · Phase 1
      </div>
    </aside>
  );
}
