import {
  FileBarChart,
  FolderKanban,
  LayoutDashboard,
  ListTodo,
  Mailbox,
  Search,
  Upload,
  User,
  type LucideIcon,
} from "lucide-react";
import type { DictKey } from "@/lib/i18n";

export type ShellNavigationSection = "workspace" | "modules" | "admin" | "account";

export interface ShellNavigationItem {
  key: string;
  section: ShellNavigationSection;
  to: string;
  labelKey: DictKey;
  icon: LucideIcon;
  showInSidebar: boolean;
  adminOnly?: boolean;
}

export const SHELL_NAVIGATION = [
  {
    key: "dashboard",
    section: "workspace",
    to: "/dashboard",
    labelKey: "nav.dashboard",
    icon: LayoutDashboard,
    showInSidebar: true,
  },
  {
    key: "projects",
    section: "workspace",
    to: "/projects",
    labelKey: "nav.projects",
    icon: FolderKanban,
    showInSidebar: true,
  },
  {
    key: "uploads",
    section: "workspace",
    to: "/uploads",
    labelKey: "nav.uploads",
    icon: Upload,
    showInSidebar: true,
  },
  {
    key: "search",
    section: "workspace",
    to: "/search",
    labelKey: "nav.search",
    icon: Search,
    showInSidebar: true,
  },
  {
    key: "jobs",
    section: "workspace",
    to: "/jobs",
    labelKey: "nav.jobs",
    icon: ListTodo,
    showInSidebar: true,
  },
  {
    key: "reports",
    section: "workspace",
    to: "/reports",
    labelKey: "nav.reports",
    icon: FileBarChart,
    showInSidebar: true,
  },
  {
    key: "modules",
    section: "modules",
    to: "/modules",
    labelKey: "nav.modules",
    icon: LayoutDashboard,
    showInSidebar: true,
  },
  {
    key: "invitations",
    section: "admin",
    to: "/admin/invitations",
    labelKey: "nav.invitations",
    icon: Mailbox,
    showInSidebar: true,
    adminOnly: true,
  },
  {
    key: "profile",
    section: "account",
    to: "/profile",
    labelKey: "nav.profile",
    icon: User,
    showInSidebar: false,
  },
] as const satisfies readonly ShellNavigationItem[];

export const SHELL_SECTION_LABELS = {
  workspace: "shell.nav.workspace",
  modules: "nav.modules",
  admin: "nav.admin",
} as const satisfies Record<Exclude<ShellNavigationSection, "account">, DictKey>;

export const SHELL_RELEASE_LABEL_KEY = "shell.release" satisfies DictKey;
export const SHELL_SIDEBAR_STORAGE_KEY = "redsea.shell.sidebar-collapsed";

export function shellRouteMatches(pathname: string, route: string): boolean {
  return pathname === route || pathname.startsWith(`${route}/`);
}

export function getShellNavigationItems(section: ShellNavigationSection): ShellNavigationItem[] {
  return SHELL_NAVIGATION.filter(
    (item) => item.section === section && item.showInSidebar,
  );
}

export function getActiveShellNavigationItem(pathname: string): ShellNavigationItem | undefined {
  return SHELL_NAVIGATION.filter((item) => shellRouteMatches(pathname, item.to)).sort(
    (a, b) => b.to.length - a.to.length,
  )[0];
}
