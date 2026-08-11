import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import { TooltipProvider } from "@/components/ui/tooltip";
import { CrewDetailTable } from "../CrewDetailTable";
import { CrewGroupHeader } from "../CrewGroupHeader";
import type { CrewHoursReport, CrewMemberSummary } from "../types";


const crew: CrewMemberSummary = {
  crew_id: "ALPHA",
  person_code: "ALPHA",
  display_name: "Alice Alpha",
  full_name: "Alice Alpha",
  position_type: "Cockpit",
  position_name: "CPT",
  status: "normal",
  official_total: "57:35",
  raw_official_total: "57:35",
  reference_total: null,
  variance_minutes: null,
  flight_count: 2,
  flights: [
    {
      flight_nid: "pad-leg",
      flight_number: "RSX-PAD",
      departure_airport: "SSH",
      arrival_airport: "SVX",
      start_time_utc: "17:20",
      end_time_utc: "23:05",
      aircraft_reg: "SU-A",
      aircraft_type: "A320",
      flight_date: "30-06-2026",
      block_time: "05:45",
      position: "PAD",
      flight_training_type: null,
      is_trn: false,
      augmented_heavy: true,
    },
    {
      flight_nid: "psn-leg",
      flight_number: "RSX-PSN",
      departure_airport: "SVX",
      arrival_airport: "SSH",
      start_time_utc: "00:00",
      end_time_utc: "05:40",
      aircraft_reg: "SU-B",
      aircraft_type: "A320",
      flight_date: "01-07-2026",
      block_time: "05:40",
      position: "PSN",
      flight_training_type: null,
      is_trn: false,
      augmented_heavy: false,
    },
  ],
};

const report: CrewHoursReport = {
  period: { from: "2026-06-01", to: "2026-06-30" },
  source: "leon_mcp_report",
  hours_source_status: "official_mcp_report",
  total_crew: 1,
  total_flights: 2,
  records_count: 2,
  official_totals_available: 1,
  official_totals_unavailable: 0,
  official_totals_by_position: { Cockpit: "57:35" },
  crew_members: [crew],
};


function renderI18n(ui: ReactNode, lang: "ar" | "en" = "en") {
  localStorage.setItem("redsea.lang", lang);
  return render(
    <I18nProvider>
      <TooltipProvider>{ui}</TooltipProvider>
    </I18nProvider>,
  );
}


describe("Crew Hours detail rendering", () => {
  it("renders Yes, No, and Unknown from the API response", () => {
    const statesCrew: CrewMemberSummary = {
      ...crew,
      flight_count: 3,
      flights: [
        ...crew.flights,
        { ...crew.flights[0], flight_nid: "unknown-leg", augmented_heavy: null },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [statesCrew] }}
        crews={[statesCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    expect(screen.getByRole("columnheader", { name: "Augmented (Heavy)" })).toBeInTheDocument();
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("Unknown")).toBeInTheDocument();
  });

  it("renders the augmented column and values in Arabic RTL", () => {
    const statesCrew: CrewMemberSummary = {
      ...crew,
      flight_count: 3,
      flights: [
        ...crew.flights,
        { ...crew.flights[0], flight_nid: "unknown-leg", augmented_heavy: null },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [statesCrew] }}
        crews={[statesCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
      "ar",
    );

    expect(screen.getByRole("columnheader", { name: "التعزيز (Heavy)" })).toBeInTheDocument();
    expect(screen.getByText("نعم")).toBeInTheDocument();
    expect(screen.getByText("لا")).toBeInTheDocument();
    expect(screen.getByText("غير معروف")).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute("dir", "rtl");
  });

  it("filters visible rows while keeping the authoritative member total", () => {
    renderI18n(
      <CrewDetailTable
        report={report}
        crews={[crew]}
        aircraftFilter="SU-B"
        positionTokenFilter="PSN"
        hasClientSideDisplayFilter
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    expect(screen.getByText("RSX-PSN")).toBeInTheDocument();
    expect(screen.queryByText("RSX-PAD")).not.toBeInTheDocument();
    expect(screen.getAllByText("57:35").length).toBeGreaterThan(0);
  });

  it("keeps the authoritative total under Block time with the enrichment column", () => {
    renderI18n(
      <CrewDetailTable
        report={report}
        crews={[crew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    const totalLabel = screen.getByText("Total", { selector: "td" });
    const totalRow = totalLabel.closest("tr");
    expect(totalRow).not.toBeNull();
    const totalCells = totalRow?.querySelectorAll("td");
    expect(totalCells).toHaveLength(3);
    expect(totalCells?.[0]).toHaveAttribute("colspan", "9");
    expect(totalCells?.[1]).toHaveTextContent("57:35");
    expect(totalCells?.[2]?.textContent).toBe("");
  });

  it("renders authoritative TRN without a local manual override control", () => {
    const trnCrew = { ...crew, status: "TRN", official_total: "TRN", raw_official_total: "TRN" };
    renderI18n(
      <table>
        <tbody>
          <CrewGroupHeader
            report={{ ...report, crew_members: [trnCrew] }}
            crew={trnCrew}
            visibleFlightCount={2}
            hasClientSideDisplayFilter={false}
            isExpanded
            onToggle={vi.fn()}
          />
        </tbody>
      </table>,
    );

    expect(screen.getAllByText("TRN").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /manual local trn/i })).not.toBeInTheDocument();
  });
});
