import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import { CopilotCitationCard } from "../CopilotCitationCard";
import { RedSeaCopilot } from "../RedSeaCopilot";
import { createUnconnectedTransport } from "../transport";
import type { CopilotAnswer, CopilotTransport } from "../types";

function wrap(node: ReactNode) {
  return render(<I18nProvider>{node}</I18nProvider>);
}

const answer: CopilotAnswer = {
  text: "Yes — RSX431 is Augmented (Heavy).",
  citation: {
    tone: "heavy",
    headline: "RSX431 · 12 Jun 2026",
    facts: [
      { label: "Aircraft", value: "B738", raw: true },
      { label: "Rule", value: "EXTRA_COCKPIT_CREW", raw: true },
    ],
    source: "LEON · unique_id 660214 · EXTRA_COCKPIT_CREW",
  },
};

const resolvingTransport: CopilotTransport = async () => answer;

describe("RedSeaCopilot", () => {
  it("opens the panel from the launcher without replacing the page", () => {
    wrap(
      <>
        <p>page content</p>
        <RedSeaCopilot transport={resolvingTransport} />
      </>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Ask RedSea Copilot|اسأل/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // The page underneath is still mounted and visible, just dimmed.
    expect(screen.getByText("page content")).toBeInTheDocument();
    expect(screen.getByTestId("copilot-scrim")).toBeInTheDocument();
  });

  it("shows the answer and its mandatory LEON source line", async () => {
    wrap(<RedSeaCopilot transport={resolvingTransport} />);
    fireEvent.click(screen.getByRole("button", { name: /Ask RedSea Copilot|اسأل/ }));

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "Is RSX431 heavy?" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Yes — RSX431 is Augmented (Heavy).")).toBeInTheDocument();
    });
    expect(
      screen.getByText("LEON · unique_id 660214 · EXTRA_COCKPIT_CREW"),
    ).toBeInTheDocument();
    expect(screen.getByText("Is RSX431 heavy?")).toBeInTheDocument();
  });

  it("names what is missing instead of softening a failure", async () => {
    wrap(
      <RedSeaCopilot transport={createUnconnectedTransport("LEON report source unavailable.")} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Ask RedSea Copilot|اسأل/ }));

    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "crew hours" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("LEON report source unavailable.")).toBeInTheDocument();
    });
  });

  it("sends a quick topic without typing", async () => {
    const transport = vi.fn(resolvingTransport);
    wrap(<RedSeaCopilot transport={transport} />);
    fireEvent.click(screen.getByRole("button", { name: /Ask RedSea Copilot|اسأل/ }));

    fireEvent.click(screen.getByRole("button", { name: /Heavy status|حالة Heavy/ }));

    await waitFor(() => expect(transport).toHaveBeenCalledTimes(1));
  });

  it("closes on Escape and returns focus to the launcher", async () => {
    wrap(<RedSeaCopilot transport={resolvingTransport} />);
    const launcher = screen.getByRole("button", { name: /Ask RedSea Copilot|اسأل/ });
    fireEvent.click(launcher);

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(launcher).toHaveFocus();
  });
});

describe("CopilotCitationCard", () => {
  it("carries a tone-coloured leading edge for each state", () => {
    const tones = ["heavy", "resolved", "unresolved"] as const;
    const edges = ["border-s-primary", "border-s-copilot-resolved", "border-s-destructive/70"];

    tones.forEach((tone, index) => {
      const { container, unmount } = wrap(
        <CopilotCitationCard citation={{ ...answer.citation!, tone }} />,
      );
      expect(container.firstElementChild?.className).toContain(edges[index]);
      unmount();
    });
  });
});
