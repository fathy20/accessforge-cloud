import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ApiClient } from "@/lib/apiClient";
import { usePermissions } from "@/lib/auth/use-permissions";
import type { ModuleRegistryItem } from "@/lib/modules/registry";

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
  readiness: "under_validation",
  ...overrides,
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("usePermissions", () => {
  beforeEach(() => {
    localStorage.setItem("access_token", "test-token");
    vi.spyOn(ApiClient, "fetch").mockImplementation(async (endpoint: string) => {
      if (endpoint === "/auth/me") {
        return { id: "admin-1", email: "admin@example.com", full_name: "Admin", roles: ["admin"] };
      }
      if (endpoint === "/modules") {
        return [
          moduleFixture({ action_permissions: ["task_extractor.export"] }),
        ];
      }
      throw new Error(`Unexpected endpoint: ${endpoint}`);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("does not fabricate module visibility for admins", async () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.isAdmin).toBe(true);
    expect(result.current.canViewModule("task_extractor")).toBe(true);
    expect(result.current.canViewModule("module_not_returned_by_api")).toBe(false);
  });

  it("does not treat declared module actions as user grants", async () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.canRunModuleAction("task_extractor", "task_extractor.export")).toBe(false);
    expect(result.current.canRunModuleAction("task_extractor", "task_extractor.delete")).toBe(false);
    expect(result.current.canRunModuleAction("missing", "task_extractor.export")).toBe(false);
  });

  it("allows a module action present in the user-filtered grants", async () => {
    vi.mocked(ApiClient.fetch).mockImplementation(async (endpoint: string) => {
      if (endpoint === "/auth/me") {
        return { id: "admin-1", email: "admin@example.com", full_name: "Admin", roles: ["admin"] };
      }
      if (endpoint === "/modules") {
        return [
          moduleFixture({
            action_permissions: ["task_extractor.export"],
            granted_action_permissions: ["task_extractor.export"],
          }),
        ];
      }
      throw new Error(`Unexpected endpoint: ${endpoint}`);
    });

    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.canRunModuleAction("task_extractor", "task_extractor.export")).toBe(true);
  });
});
