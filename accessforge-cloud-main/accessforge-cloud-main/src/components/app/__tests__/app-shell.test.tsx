import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/apiClient";
import { I18nProvider } from "@/lib/i18n";
import { getShellNavigationItems } from "@/lib/navigation/shell-nav";
import type { ModuleRegistryItem } from "@/lib/modules/registry";
import { AppLayout } from "@/components/app/AppLayout";
import { AppSidebar } from "@/components/app/AppSidebar";
import { AppTopbar } from "@/components/app/AppTopbar";

const testState = vi.hoisted(() => ({
  isMobile: false,
  pathname: "/dashboard",
  navigate: vi.fn(),
}));

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-router")>(
    "@tanstack/react-router",
  );
  return {
    ...actual,
    Link: ({ to, children, ...props }: any) => (
      <a href={String(to)} {...props}>
        {children}
      </a>
    ),
    useNavigate: () => testState.navigate,
    useRouterState: () => testState.pathname,
  };
});

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => testState.isMobile,
}));

vi.mock("@/components/app/NotificationBell", () => ({
  NotificationBell: () => <button />,
}));

const moduleFixture = (
  overrides: Partial<ModuleRegistryItem> = {},
): ModuleRegistryItem => ({
  key: "task_extractor",
  name: "Task Extractor",
  description: null,
  icon: null,
  category: "PDF Processing",
  enabled: true,
  sort_order: 1,
  business_area: "maintenance",
  route: "/modules/task-extractor",
  module_status: "active",
  required_view_permission: "task_extractor.view",
  display_name_key: "modules.task_extractor.name",
  action_permissions: [],
  granted_action_permissions: [],
  readiness: "available",
  ...overrides,
});

const registryModules = [
  moduleFixture(),
  moduleFixture({
    key: "admin_users",
    name: "User Management",
    business_area: "admin",
    route: "/admin/users",
    sort_order: 2,
  }),
];

function renderWithProviders(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

describe("application shell", () => {
  beforeEach(() => {
    testState.isMobile = false;
    testState.pathname = "/dashboard";
    testState.navigate.mockReset();
    localStorage.setItem("access_token", "test-token");
    localStorage.setItem("redsea.lang", "en");

    vi.spyOn(ApiClient, "fetch").mockImplementation(async (endpoint: string) => {
      if (endpoint === "/auth/me") {
        return {
          id: "admin-1",
          email: "admin@example.com",
          full_name: "Admin",
          roles: ["admin"],
        };
      }
      if (endpoint === "/modules") return registryModules;
      throw new Error(`Unexpected endpoint: ${endpoint}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    document.documentElement.lang = "en";
    document.documentElement.removeAttribute("dir");
  });

  it("renders workspace navigation from the declared shell source", async () => {
    renderWithProviders(<AppSidebar />);

    await waitFor(() => expect(screen.getByTestId("shell-nav-dashboard")).toBeInTheDocument());

    for (const item of getShellNavigationItems("workspace")) {
      expect(screen.getByTestId(`shell-nav-${item.key}`)).toHaveAttribute("href", item.to);
    }
  });

  it("exposes the active item with aria-current", () => {
    testState.pathname = "/projects/project-1";
    renderWithProviders(<AppSidebar />);

    expect(screen.getByTestId("shell-nav-projects")).toHaveAttribute("aria-current", "page");
    expect(screen.getByTestId("shell-nav-dashboard")).not.toHaveAttribute("aria-current");
  });

  it("opens reachable navigation in a drawer below md", async () => {
    testState.isMobile = true;
    renderWithProviders(<AppLayout>Page content</AppLayout>);

    fireEvent.click(screen.getByTestId("mobile-navigation-trigger"));

    const drawer = await screen.findByRole("dialog", { name: "Main navigation" });
    expect(within(drawer).getByTestId("shell-nav-dashboard")).toHaveAttribute(
      "href",
      "/dashboard",
    );
  });

  it("resolves module context in the topbar from the registry", async () => {
    testState.pathname = "/modules/task-extractor";
    renderWithProviders(<AppTopbar />);

    await waitFor(() => expect(screen.getByText("Task Extractor")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Notifications" })).toBeInTheDocument();
  });

  it("renders the Arabic shell in RTL without physical direction utilities", async () => {
    localStorage.setItem("redsea.lang", "ar");
    const { container } = renderWithProviders(<AppLayout>محتوى الصفحة</AppLayout>);

    await waitFor(() => expect(document.documentElement).toHaveAttribute("dir", "rtl"));
    expect(container.firstElementChild).toHaveAttribute("dir", "rtl");
    expect(screen.getByText("مساحة العمل")).toBeInTheDocument();

    const physicalDirectionUtility = /(?:^|\s)(?:ml|mr|left|right)-/;
    for (const element of container.querySelectorAll("[class]")) {
      expect(element.getAttribute("class") ?? "").not.toMatch(physicalDirectionUtility);
    }
  });
});
