import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import { ApiClient } from "@/lib/apiClient";
import type { CrewHoursReport } from "../types";


vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-router")>(
    "@tanstack/react-router",
  );
  return {
    ...actual,
    createFileRoute: () => (configuration: unknown) => ({ options: configuration }),
  };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { Route } from "@/routes/_authenticated/modules/crew-hours";

type PreloadableComponent = ComponentType & { preload?: () => Promise<unknown> };
const CrewHoursPage = Route.options.component as PreloadableComponent;


const report: CrewHoursReport = {
  period: { from: "2026-06-01", to: "2026-06-30" },
  source: "leon_mcp_report",
  hours_source_status: "official_mcp_report",
  total_crew: 1,
  total_flights: 1,
  records_count: 1,
  official_totals_available: 1,
  official_totals_unavailable: 0,
  official_totals_by_position: {},
  crew_members: [
    {
      crew_id: "TRAINING",
      person_code: "TRAINING",
      display_name: "Training Fixture",
      full_name: "Training Fixture",
      position_type: "Cockpit",
      position_name: "CPT",
      status: "TRN",
      official_total: "TRN",
      raw_official_total: "TRN",
      reference_total: null,
      variance_minutes: null,
      flight_count: 1,
      flights: [
        {
          flight_nid: "trn-leg",
          flight_number: "RSX-TRN",
          departure_airport: "SSH",
          arrival_airport: "CAI",
          start_time_utc: "08:00",
          end_time_utc: "08:00",
          aircraft_reg: "SU-T",
          aircraft_type: "A320",
          flight_date: "15-06-2026",
          block_time: null,
          position: "CPT",
          flight_training_type: "TRN",
          is_trn: true,
        },
      ],
    },
  ],
};


function renderPage(lang: "ar" | "en" = "en") {
  localStorage.setItem("redsea.lang", lang);
  return render(
    <I18nProvider>
      <CrewHoursPage />
    </I18nProvider>,
  );
}


describe("Crew Hours page request contract", () => {
  let originalDocumentLang: string | null;
  let originalDocumentDir: string | null;

  beforeAll(async () => {
    await CrewHoursPage.preload?.();
  });

  beforeEach(() => {
    originalDocumentLang = document.documentElement.getAttribute("lang");
    originalDocumentDir = document.documentElement.getAttribute("dir");
    vi.spyOn(ApiClient, "fetch").mockResolvedValue(report);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    if (originalDocumentLang === null) document.documentElement.removeAttribute("lang");
    else document.documentElement.setAttribute("lang", originalDocumentLang);
    if (originalDocumentDir === null) document.documentElement.removeAttribute("dir");
    else document.documentElement.setAttribute("dir", originalDocumentDir);
  });

  it("sends exactly one additional request per Load click with exact date strings", async () => {
    renderPage();
    await waitFor(() => expect(ApiClient.fetch).toHaveBeenCalledTimes(1));

    fireEvent.click(await screen.findByRole("button", { name: /load report/i }));

    await waitFor(() => expect(ApiClient.fetch).toHaveBeenCalledTimes(2));
    expect(ApiClient.fetch).toHaveBeenLastCalledWith(
      "/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30",
    );
  });

  it("blocks From after To before fetch", async () => {
    renderPage();
    await waitFor(() => expect(ApiClient.fetch).toHaveBeenCalledTimes(1));
    const inputs = document.querySelectorAll<HTMLInputElement>('input[type="date"]');
    fireEvent.change(inputs[0], { target: { value: "2026-06-30" } });
    fireEvent.change(inputs[1], { target: { value: "2026-06-01" } });

    fireEvent.click(await screen.findByRole("button", { name: /load report/i }));

    expect(ApiClient.fetch).toHaveBeenCalledTimes(1);
  });

  it("renders Arabic in RTL without physical direction utilities", async () => {
    const { container } = renderPage("ar");

    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("lang", "ar");
      expect(document.documentElement).toHaveAttribute("dir", "rtl");
    });
    expect(screen.getByRole("heading", { name: "ساعات الطاقم" })).toBeInTheDocument();
    expect(screen.getByText("تصفية التقرير")).toBeInTheDocument();

    const physicalDirectionUtility = /(?:^|:)(?:left|right|ml|mr|pl|pr)-/;
    for (const element of container.querySelectorAll("[class]")) {
      for (const className of (element.getAttribute("class") ?? "").split(/\s+/)) {
        expect(className).not.toMatch(physicalDirectionUtility);
      }
    }
  });
});
