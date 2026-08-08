import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/apiClient";
import { I18nProvider } from "@/lib/i18n";
import { AppSidebar } from "@/components/app/AppSidebar";
import { MaintenancePage } from "@/routes/_authenticated/modules/maintenance";
import type { ModuleRegistryItem } from "@/lib/modules/registry";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
  return {
    ...actual,
    Link: ({ to, children, ...props }: any) => (
      <a href={String(to)} {...props}>
        {children}
      </a>
    ),
    useRouterState: () => "/dashboard",
  };
});

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

const apiModules = [
  moduleFixture(),
  moduleFixture({
    key: "crew_hours",
    name: "Crew Hours",
    business_area: "crew",
    route: "/modules/crew-hours",
    sort_order: 9,
  }),
  moduleFixture({
    key: "tcm_indexing",
    name: "TCM Indexing",
    route: null,
    sort_order: 10,
    readiness: "discovery_required",
  }),
  moduleFixture({
    key: "admin_users",
    name: "User Management",
    business_area: "admin",
    route: "/admin/users",
    sort_order: 11,
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

function mockRegistryApi(modules: ModuleRegistryItem[]) {
  localStorage.setItem("access_token", "test-token");
  localStorage.setItem("redsea.lang", "en");
  vi.spyOn(ApiClient, "fetch").mockImplementation(async (endpoint: string) => {
    if (endpoint === "/auth/me") {
      return { id: "admin-1", email: "admin@example.com", full_name: "Admin", roles: ["admin"] };
    }
    if (endpoint === "/modules") return modules;
    throw new Error(`Unexpected endpoint: ${endpoint}`);
  });
}

describe("registry-driven module UI", () => {
  beforeEach(() => mockRegistryApi(apiModules));

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders only returned sidebar modules and no link for a null route", async () => {
    renderWithProviders(<AppSidebar />);

    await waitFor(() => expect(screen.getByTestId("module-nav-task_extractor")).toBeInTheDocument());

    expect(screen.getByTestId("module-nav-crew_hours")).toBeInTheDocument();
    expect(screen.getByTestId("module-nav-tcm_indexing")).toBeInTheDocument();
    expect(screen.getByTestId("module-nav-admin_users")).toBeInTheDocument();
    expect(screen.getAllByTestId(/^module-nav-/)).toHaveLength(apiModules.length);
    expect(screen.queryByTestId("module-nav-effectivity")).not.toBeInTheDocument();
    expect(screen.getByTestId("module-nav-tcm_indexing").tagName).not.toBe("A");
    expect(screen.getByTestId("module-nav-tcm_indexing")).toHaveTextContent("Discovery required");
  });

  it("shows only maintenance modules on the maintenance dashboard", async () => {
    renderWithProviders(<MaintenancePage />);

    await waitFor(() => expect(screen.getByTestId("module-card-task_extractor")).toBeInTheDocument());

    expect(screen.getByTestId("module-card-task_extractor")).toBeInTheDocument();
    expect(screen.getByTestId("module-card-tcm_indexing")).toBeInTheDocument();
    expect(screen.queryByTestId("module-card-crew_hours")).not.toBeInTheDocument();
    expect(screen.queryByTestId("module-card-admin_users")).not.toBeInTheDocument();
    expect(screen.getByTestId("module-card-tcm_indexing").closest("a")).toBeNull();
  });

  it("renders a readiness badge for a discovery-required module", async () => {
    renderWithProviders(<MaintenancePage />);

    await waitFor(() => expect(screen.getByTestId("readiness-badge-tcm_indexing")).toBeInTheDocument());

    expect(screen.getByTestId("readiness-badge-tcm_indexing")).toHaveTextContent("Discovery required");
  });
});
