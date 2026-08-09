import { useEffect, useState } from "react";
import { Link, useRouterState } from "@tanstack/react-router";
import {
  CircleCheck,
  Info,
  PanelLeftClose,
  PanelLeftOpen,
  SquareMinus,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { DEFAULT_MODULE_ICON, MODULE_ICONS } from "@/lib/modules/icons";
import {
  getModuleLabel,
  getReadinessLabel,
  getReadinessStatusFamily,
  sortModules,
  type ModuleRegistryItem,
  type ModuleReadinessStatusFamily,
} from "@/lib/modules/registry";
import {
  getActiveShellNavigationItem,
  getShellNavigationItems,
  SHELL_RELEASE_LABEL_KEY,
  SHELL_SECTION_LABELS,
  SHELL_SIDEBAR_STORAGE_KEY,
  shellRouteMatches,
  type ShellNavigationItem,
  type ShellNavigationSection,
} from "@/lib/navigation/shell-nav";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface AppSidebarProps {
  isMobile?: boolean;
  mobileOpen?: boolean;
  onMobileOpenChange?: (open: boolean) => void;
}

interface RegistryGroupOptions {
  staticSection?: ShellNavigationSection;
  showWhenLoading?: boolean;
}

const READINESS_INDICATOR: Record<
  ModuleReadinessStatusFamily,
  { icon: LucideIcon; className: string; shapeClassName: string }
> = {
  success: {
    icon: CircleCheck,
    shapeClassName: "rounded-full",
    className:
      "border-status-success-border bg-status-success-background text-status-success-foreground",
  },
  info: {
    icon: Info,
    shapeClassName: "rounded-full",
    className:
      "border-status-info-border bg-status-info-background text-status-info-foreground",
  },
  warning: {
    icon: TriangleAlert,
    shapeClassName: "rounded-sm",
    className:
      "border-status-warning-border bg-status-warning-background text-status-warning-foreground",
  },
  neutral: {
    icon: SquareMinus,
    shapeClassName: "rounded-none",
    className:
      "border-status-neutral-border bg-status-neutral-background text-status-neutral-foreground",
  },
};

export function AppSidebar({
  isMobile = false,
  mobileOpen = false,
  onMobileOpenChange,
}: AppSidebarProps = {}) {
  const perms = usePermissions();
  const { dir, t } = useI18n();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      setCollapsed(window.localStorage.getItem(SHELL_SIDEBAR_STORAGE_KEY) === "true");
    } catch {
      // Storage can be unavailable in privacy-restricted browser contexts.
    }
  }, []);

  const registryModules = sortModules(perms.modules);
  const workspaceModules = registryModules.filter(
    (module) => module.business_area === "maintenance" || module.business_area === "crew",
  );
  const adminModules = registryModules.filter((module) => module.business_area === "admin");
  const activeShellItem = getActiveShellNavigationItem(pathname);
  const activeRegistryModule = registryModules
    .filter((module) => module.route && shellRouteMatches(pathname, module.route))
    .sort((a, b) => (b.route?.length ?? 0) - (a.route?.length ?? 0))[0];
  const activeRoute =
    (activeRegistryModule?.route?.length ?? 0) > (activeShellItem?.to.length ?? 0)
      ? activeRegistryModule?.route
      : activeShellItem?.to;

  const toggleCollapsed = () => {
    setCollapsed((current) => {
      const next = !current;
      if (typeof window !== "undefined") {
        try {
          window.localStorage.setItem(SHELL_SIDEBAR_STORAGE_KEY, String(next));
        } catch {
          // The visual preference still works for this session without persistence.
        }
      }
      return next;
    });
  };

  const itemClassName = (active: boolean, isCollapsed: boolean, disabled = false) =>
    cn(
      "relative flex h-10 items-center rounded-md text-body transition-colors",
      isCollapsed ? "justify-center px-2" : "gap-2.5 px-2.5",
      disabled
        ? "cursor-not-allowed bg-interactive-disabled text-fg-disabled"
        : active
          ? "bg-interactive-selected font-semibold text-sidebar-accent-foreground before:absolute before:inset-y-2 before:start-0 before:w-0.5 before:rounded-full before:bg-primary"
          : "text-fg-secondary hover:bg-interactive-hover hover:text-fg-primary active:bg-interactive-active",
    );

  const renderShellItem = (
    item: ShellNavigationItem,
    isCollapsed: boolean,
    onNavigate?: () => void,
  ) => {
    const Icon = item.icon;
    const label = t(item.labelKey);
    const active = activeRoute === item.to;
    const link = (
      <Link
        key={item.key}
        to={item.to as any}
        aria-current={active ? "page" : undefined}
        aria-label={isCollapsed ? label : undefined}
        className={itemClassName(active, isCollapsed)}
        data-testid={`shell-nav-${item.key}`}
        onClick={onNavigate}
      >
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        <span className={cn("truncate", isCollapsed && "sr-only")}>{label}</span>
      </Link>
    );

    if (!isCollapsed) return link;

    return (
      <Tooltip key={item.key}>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent>{label}</TooltipContent>
      </Tooltip>
    );
  };

  const renderRegistryItem = (
    module: ModuleRegistryItem,
    isCollapsed: boolean,
    onNavigate?: () => void,
  ) => {
    const Icon = MODULE_ICONS[module.key] ?? DEFAULT_MODULE_ICON;
    const label = getModuleLabel(module, t);
    const readinessLabel = getReadinessLabel(module, t);
    const showReadiness = module.readiness !== "available";
    const readinessStatus = getReadinessStatusFamily(module.readiness);
    const readinessIndicator = READINESS_INDICATOR[readinessStatus];
    const ReadinessIcon = readinessIndicator.icon;
    const active = module.route === activeRoute;
    const accessibleLabel = showReadiness ? `${label} — ${readinessLabel}` : label;
    const content = (
      <>
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        <span
          className={cn(
            "min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap",
            isCollapsed && "sr-only",
          )}
        >
          {label}
        </span>
        {showReadiness && (
          <span
            data-testid={`module-readiness-${module.key}`}
            className={cn(
              "grid shrink-0 place-items-center border",
              isCollapsed ? "absolute end-1 top-1 size-4" : "ms-auto size-5",
              readinessIndicator.shapeClassName,
              readinessIndicator.className,
            )}
            aria-hidden="true"
          >
            <ReadinessIcon className={isCollapsed ? "size-3" : "size-3.5"} />
          </span>
        )}
        {showReadiness && <span className="sr-only">{readinessLabel}</span>}
      </>
    );

    const item = module.route === null ? (
      <div
        key={module.key}
        data-testid={`module-nav-${module.key}`}
        data-readiness-status={readinessStatus}
        className={itemClassName(false, isCollapsed, true)}
        aria-disabled="true"
        aria-label={accessibleLabel}
      >
        {content}
      </div>
    ) : (
      <Link
        key={module.key}
        data-testid={`module-nav-${module.key}`}
        data-readiness-status={readinessStatus}
        to={module.route as any}
        className={itemClassName(active, isCollapsed)}
        aria-current={active ? "page" : undefined}
        aria-label={accessibleLabel}
        onClick={onNavigate}
      >
        {content}
      </Link>
    );

    if (!isCollapsed && !showReadiness) return item;

    return (
      <Tooltip key={module.key}>
        <TooltipTrigger asChild>{item}</TooltipTrigger>
        <TooltipContent>{accessibleLabel}</TooltipContent>
      </Tooltip>
    );
  };

  const renderShellGroup = (
    section: ShellNavigationSection,
    isCollapsed: boolean,
    onNavigate?: () => void,
  ) => {
    const items = getShellNavigationItems(section).filter(
      (item) => !item.adminOnly || perms.isAdmin,
    );
    if (!items.length || section === "account") return null;

    const title = t(SHELL_SECTION_LABELS[section]);
    return (
      <section className="px-3 py-2" key={section}>
        <h2
          className={cn(
            "mb-1.5 px-2 text-label text-fg-muted",
            isCollapsed && "sr-only",
          )}
        >
          {title}
        </h2>
        <nav className="flex flex-col gap-0.5" aria-label={title}>
          {items.map((item) => renderShellItem(item, isCollapsed, onNavigate))}
        </nav>
      </section>
    );
  };

  const renderRegistryGroup = (
    title: string,
    modules: ModuleRegistryItem[],
    isCollapsed: boolean,
    options: RegistryGroupOptions = {},
    onNavigate?: () => void,
  ) => {
    const staticItems = options.staticSection
      ? getShellNavigationItems(options.staticSection).filter(
          (item) => !item.adminOnly || perms.isAdmin,
        )
      : [];
    if (!modules.length && !staticItems.length) return null;

    return (
      <section className="px-3 py-2" key={title}>
        <h2
          className={cn(
            "mb-1.5 px-2 text-label text-fg-muted",
            isCollapsed && "sr-only",
          )}
        >
          {title}
        </h2>
        <nav className="flex flex-col gap-0.5" aria-label={title}>
          {staticItems.map((item) => renderShellItem(item, isCollapsed, onNavigate))}
          {perms.loading && options.showWhenLoading ? (
            <div
              className={cn("px-2.5 py-2 text-caption text-fg-muted", isCollapsed && "sr-only")}
              role="status"
            >
              {t("mod.loading")}
            </div>
          ) : (
            modules.map((module) => renderRegistryItem(module, isCollapsed, onNavigate))
          )}
        </nav>
      </section>
    );
  };

  const renderPanel = (
    isCollapsed: boolean,
    options: { mobile?: boolean; onNavigate?: () => void } = {},
  ) => (
    <div className="flex h-full min-h-0 flex-col bg-sidebar text-sidebar-foreground">
      <div
        className={cn(
          "flex items-center border-b border-sidebar-border py-4",
          isCollapsed ? "justify-center px-3" : "gap-3 px-5",
        )}
      >
        <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-sidebar-border bg-primary-foreground p-1.5">
          <img
            src="/logo.png"
            alt={t("shell.brand.logo_alt")}
            className="size-full object-contain"
          />
        </div>
        {!isCollapsed && (
          <div className="flex min-w-0 flex-1 flex-col leading-tight">
            <p className="text-heading-3 tracking-tight text-fg-primary">REDSEA</p>
            <p className="truncate text-caption uppercase tracking-[0.16em] text-fg-muted">
              {t("shell.brand.tagline")}
            </p>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {renderShellGroup("workspace", isCollapsed, options.onNavigate)}
        {renderRegistryGroup(
          t(SHELL_SECTION_LABELS.modules),
          workspaceModules,
          isCollapsed,
          { staticSection: "modules", showWhenLoading: true },
          options.onNavigate,
        )}
        {renderRegistryGroup(
          t(SHELL_SECTION_LABELS.admin),
          adminModules,
          isCollapsed,
          { staticSection: "admin" },
          options.onNavigate,
        )}
      </div>

      <div
        className={cn(
          "flex min-h-14 items-center border-t border-sidebar-border px-3 py-2 text-caption text-fg-muted",
          isCollapsed ? "justify-center" : "gap-2",
        )}
      >
        {!isCollapsed && <span className="truncate">{t(SHELL_RELEASE_LABEL_KEY)}</span>}
        {!options.mobile && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn(
              "shrink-0 text-fg-secondary hover:bg-interactive-hover hover:text-fg-primary",
              !isCollapsed && "ms-auto",
            )}
            onClick={toggleCollapsed}
            aria-label={
              isCollapsed ? t("shell.expand_navigation") : t("shell.collapse_navigation")
            }
            aria-expanded={!isCollapsed}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="rtl:rotate-180" aria-hidden="true" />
            ) : (
              <PanelLeftClose className="rtl:rotate-180" aria-hidden="true" />
            )}
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <TooltipProvider delayDuration={250}>
      <aside
        className={cn(
          "hidden shrink-0 border-e border-sidebar-border md:flex md:flex-col",
          collapsed ? "w-20" : "w-64",
        )}
        aria-label={t("shell.navigation")}
        data-collapsed={collapsed}
      >
        {renderPanel(collapsed)}
      </aside>

      {isMobile && (
        <Sheet open={mobileOpen} onOpenChange={onMobileOpenChange}>
          <SheetContent
            side={dir === "rtl" ? "right" : "left"}
            dir={dir}
            className="w-[min(20rem,90vw)] border-sidebar-border bg-sidebar p-0 text-sidebar-foreground [&>button]:text-fg-primary"
          >
            <SheetTitle className="sr-only">{t("shell.navigation")}</SheetTitle>
            <SheetDescription className="sr-only">
              {t("shell.navigation_description")}
            </SheetDescription>
            {renderPanel(false, {
              mobile: true,
              onNavigate: () => onMobileOpenChange?.(false),
            })}
          </SheetContent>
        </Sheet>
      )}
    </TooltipProvider>
  );
}
