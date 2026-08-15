import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import {
  Languages,
  LogOut,
  Menu,
  Search as SearchIcon,
  User as UserIcon,
} from "lucide-react";
import { ApiClient } from "@/lib/apiClient";
import { useAuth } from "@/lib/auth/use-auth";
import { usePermissions } from "@/lib/auth/use-permissions";
import { useI18n } from "@/lib/i18n";
import { getModuleLabel, sortModules } from "@/lib/modules/registry";
import {
  getActiveShellNavigationItem,
  shellRouteMatches,
} from "@/lib/navigation/shell-nav";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { NotificationBell } from "@/components/app/NotificationBell";

export interface AppTopbarProps {
  onOpenNavigation?: () => void;
}

export function AppTopbar({ onOpenNavigation }: AppTopbarProps = {}) {
  const { user } = useAuth();
  const perms = usePermissions();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const queryClient = useQueryClient();
  const { t, lang, setLang } = useI18n();

  const fullName = ((user as any)?.full_name || (user as any)?.user_metadata?.full_name) as
    | string
    | undefined;
  const initials =
    fullName
      ?.split(" ")
      .map((word) => word[0])
      .slice(0, 2)
      .join("")
      .toUpperCase() ??
    user?.email?.[0]?.toUpperCase() ??
    "U";

  const shellItem = getActiveShellNavigationItem(pathname);
  const moduleItem = sortModules(perms.modules)
    .filter((module) => module.route && shellRouteMatches(pathname, module.route))
    .sort((a, b) => (b.route?.length ?? 0) - (a.route?.length ?? 0))[0];
  const moduleProvidesContext =
    (moduleItem?.route?.length ?? 0) > (shellItem?.to.length ?? 0);
  const currentTitle = moduleProvidesContext
    ? getModuleLabel(moduleItem, t)
    : shellItem
      ? t(shellItem.labelKey)
      : t("shell.current_page");

  const signOut = async () => {
    ApiClient.clearToken();
    await queryClient.cancelQueries();
    queryClient.clear();
    navigate({ to: "/auth", replace: true });
  };

  const topRole = perms.roles[0] ?? "guest";
  const roleLabel = topRole.replace("_", " ");

  return (
    <header className="flex min-h-16 items-center gap-2 border-b border-surface-raised-border bg-surface-raised px-shell-padding">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="shrink-0 md:hidden"
        onClick={onOpenNavigation}
        aria-label={t("shell.open_navigation")}
        data-testid="mobile-navigation-trigger"
      >
        <Menu aria-hidden="true" />
      </Button>

      <div className="min-w-0 flex-1 md:max-w-48">
        <p className="hidden text-caption text-fg-muted sm:block">{t("shell.current_page")}</p>
        <p className="truncate text-label text-fg-primary" aria-live="polite">
          {currentTitle}
        </p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          const query = (new FormData(event.currentTarget).get("q") as string)?.trim();
          navigate({ to: "/search", search: query ? { q: query } : undefined });
        }}
        className="relative hidden max-w-md flex-1 md:flex"
        role="search"
      >
        <label htmlFor="shell-search" className="sr-only">
          {t("top.search_label")}
        </label>
        <SearchIcon
          className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-fg-muted"
          aria-hidden="true"
        />
        <Input
          id="shell-search"
          name="q"
          placeholder={t("top.search_placeholder")}
          className="h-9 ps-9"
        />
      </form>

      <div className="ms-auto flex shrink-0 items-center gap-1 sm:gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setLang(lang === "ar" ? "en" : "ar")}
          className="gap-2"
          aria-label={t("top.language_switch")}
        >
          <Languages aria-hidden="true" />
          <span className="hidden text-label sm:inline">{t("top.language_target_short")}</span>
        </Button>
        <label className="contents">
          <span className="sr-only">{t("top.notifications")}</span>
          <NotificationBell />
        </label>
        <Badge
          variant="secondary"
          className="hidden max-w-28 truncate capitalize sm:inline-flex"
          aria-label={t("top.role", { role: roleLabel })}
        >
          {roleLabel}
        </Badge>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="rounded-full"
              aria-label={t("top.account_menu")}
            >
              <Avatar className="size-8">
                <AvatarFallback className="bg-brand-subtle text-label text-primary">
                  {initials}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="flex flex-col">
              <span className="font-medium">{fullName ?? t("top.signed_in")}</span>
              <span className="truncate text-label text-fg-muted">{user?.email}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate({ to: "/profile" })}>
              <UserIcon aria-hidden="true" /> {t("nav.profile")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={signOut} className="text-destructive focus:text-destructive">
              <LogOut className="rtl:rotate-180" aria-hidden="true" /> {t("top.signout")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
