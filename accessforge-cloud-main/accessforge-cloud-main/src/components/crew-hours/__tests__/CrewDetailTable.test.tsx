import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("shows Heavy provenance in the tooltip and marks LEON/local conflicts", async () => {
    const provenanceCrew: CrewMemberSummary = {
      ...crew,
      flights: [
        {
          ...crew.flights[0],
          heavy_source: "LEON",
          heavy_reason: "EXTRA_COCKPIT_CREW",
          leon_heavy: false,
          derived_heavy: true,
          effective_heavy: false,
          heavy_conflict: true,
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [provenanceCrew] }}
        crews={[provenanceCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    const marker = screen.getByRole("img", { name: "Conflict: LEON takes precedence" });
    expect(marker).toBeInTheDocument();
    const trigger = marker.closest("[tabindex='0']");
    expect(trigger).not.toBeNull();
    fireEvent.focus(trigger as HTMLElement);

    await waitFor(() => {
      expect(screen.getAllByText("Source: LEON").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Reason: EXTRA_COCKPIT_CREW").length).toBeGreaterThan(0);
      expect(screen.getAllByText("LEON value: No").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Derived value: Yes").length).toBeGreaterThan(0);
    });
  });

  it("renders the conflict marker in Arabic RTL", () => {
    const provenanceCrew: CrewMemberSummary = {
      ...crew,
      flights: [{ ...crew.flights[0], heavy_conflict: true }],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [provenanceCrew] }}
        crews={[provenanceCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
      "ar",
    );

    expect(screen.getByRole("img", { name: "تعارض: LEON له الأولوية" })).toBeInTheDocument();
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

  it("marks locally-resolved rows with a red exclamation badge and reason tooltip", async () => {
    const locallyResolvedCrew: CrewMemberSummary = {
      ...crew,
      flights: [
        {
          ...crew.flights[0],
          heavy_source: "LOCAL_RULE",
          effective_heavy: true,
          augmented_heavy: true,
          unknown_resolved: true,
          unknown_resolution_reason: "SAME_DAY_SHORT_BREAK_SAME_CREW",
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [locallyResolvedCrew] }}
        crews={[locallyResolvedCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    const badge = screen.getByTestId("local-resolution-marker");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAccessibleName(
      "Not found in LEON augmented data — resolved by local rotation rule",
    );

    const trigger = badge.closest("[tabindex='0']");
    expect(trigger).not.toBeNull();
    fireEvent.focus(trigger as HTMLElement);

    await waitFor(() => {
      expect(
        screen.getAllByText("Unknown resolution: SAME_DAY_SHORT_BREAK_SAME_CREW").length,
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByText(
          "Not found in LEON augmented data — resolved by local rotation rule",
        ).length,
      ).toBeGreaterThan(0);
    });
  });

  it("shows the decision trace on a deterministic row, which carries no badge", async () => {
    // 2.6: every leg explains itself, not only resolver-decided ones. This row
    // is decided by the airport rule, so it has no badge and must still show
    // the steps that produced its Yes.
    const tracedCrew: CrewMemberSummary = {
      ...crew,
      flight_count: 1,
      flights: [
        {
          ...crew.flights[0],
          flight_number: "RSX331",
          heavy_source: "LOCAL_RULE",
          heavy_reason: "SVX_AIRPORT",
          effective_heavy: true,
          augmented_heavy: true,
          unknown_resolved: false,
          heavy_trace: [
            {
              step: "LEON_AUGMENTATION",
              outcome: "LEON is silent for this leg",
              inputs: { ftl_index_available: true },
            },
            {
              step: "STEP_2_SVX_AIRPORT",
              outcome: "matched 'USSS' -> Heavy Yes",
              inputs: { route_airports: ["SSH", "SVX", "HESH", "USSS"] },
            },
            { step: "VERDICT", outcome: "Heavy Yes", inputs: { badge: false } },
          ],
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [tracedCrew] }}
        crews={[tracedCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("local-resolution-marker")).toBeNull();

    const verdict = screen.getAllByLabelText(/Augmented \(Heavy\)/)[0];
    fireEvent.focus(verdict);

    await waitFor(() => {
      expect(screen.getAllByTestId("heavy-trace").length).toBeGreaterThan(0);
    });
    const trace = screen.getAllByTestId("heavy-trace")[0];
    expect(trace).toHaveTextContent("STEP_2_SVX_AIRPORT");
    // Airports as received, in both code systems.
    expect(trace).toHaveTextContent("SSH, SVX, HESH, USSS");
    expect(trace).toHaveTextContent("VERDICT");
  });

  it("renders no badge on airport-decided EVN/SVX rows", () => {
    // RSX331/RSX121 evidence: SVX/EVN verdicts are deterministic rules, not
    // resolver guesses — unknown_resolved is false and no badge may render.
    const airportCrew: CrewMemberSummary = {
      ...crew,
      flight_count: 2,
      flights: [
        {
          ...crew.flights[0],
          flight_nid: "svx-leg",
          flight_number: "RSX331",
          heavy_source: "LOCAL_RULE",
          heavy_reason: "SVX_AIRPORT",
          effective_heavy: true,
          augmented_heavy: true,
          unknown_resolved: false,
        },
        {
          ...crew.flights[1],
          flight_nid: "evn-leg",
          flight_number: "RSX121",
          heavy_source: "LOCAL_RULE",
          heavy_reason: "EVN_AIRPORT",
          effective_heavy: false,
          augmented_heavy: false,
          unknown_resolved: false,
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [airportCrew] }}
        crews={[airportCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("local-resolution-marker")).not.toBeInTheDocument();
  });

  it("renders the badge on both legs of a resolver-decided rotation", () => {
    // RSX6081/RSX6084 evidence: every leg that entered STEP 4 carries the
    // badge, regardless of its Yes/No outcome.
    const rotationCrew: CrewMemberSummary = {
      ...crew,
      flight_count: 2,
      flights: [
        {
          ...crew.flights[0],
          flight_nid: "leg-out",
          flight_number: "RSX6081",
          heavy_source: "LOCAL_RULE",
          effective_heavy: true,
          augmented_heavy: true,
          unknown_resolved: true,
          unknown_resolution_reason: "SAME_DAY_SHORT_BREAK_SAME_CREW",
        },
        {
          ...crew.flights[1],
          flight_nid: "leg-back",
          flight_number: "RSX6084",
          heavy_source: "LOCAL_RULE",
          effective_heavy: false,
          augmented_heavy: false,
          unknown_resolved: true,
          unknown_resolution_reason: "BREAK_EXCEEDS_LIMIT",
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [rotationCrew] }}
        crews={[rotationCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    expect(screen.getAllByTestId("local-resolution-marker")).toHaveLength(2);
  });

  it("renders no local-resolution badge for LEON-sourced rows", () => {
    const leonCrew: CrewMemberSummary = {
      ...crew,
      flights: [
        {
          ...crew.flights[0],
          heavy_source: "LEON",
          effective_heavy: true,
          unknown_resolved: false,
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [leonCrew] }}
        crews={[leonCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("local-resolution-marker")).not.toBeInTheDocument();
  });

  it("renders the local-resolution badge label in Arabic", () => {
    const locallyResolvedCrew: CrewMemberSummary = {
      ...crew,
      flights: [
        {
          ...crew.flights[0],
          heavy_source: "LOCAL_RULE",
          unknown_resolved: true,
          unknown_resolution_reason: "SAME_DAY_SHORT_BREAK_SAME_CREW",
        },
      ],
    };

    renderI18n(
      <CrewDetailTable
        report={{ ...report, crew_members: [locallyResolvedCrew] }}
        crews={[locallyResolvedCrew]}
        aircraftFilter="__all_aircraft__"
        positionTokenFilter="All"
        hasClientSideDisplayFilter={false}
        expandedCrew={{ ALPHA: true }}
        onToggleCrew={vi.fn()}
      />,
      "ar",
    );

    const badge = screen.getByTestId("local-resolution-marker");
    expect(badge).toHaveAccessibleName(
      "غير موجود في بيانات LEON للتعزيز — تم الحل بقاعدة الدوران المحلية",
    );
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
