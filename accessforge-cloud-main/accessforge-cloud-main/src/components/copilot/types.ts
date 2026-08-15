/**
 * RedSea Copilot — data contract.
 *
 * The panel is presentation only.  Everything it shows arrives through a
 * CopilotTransport, so engineering can wire the live LEON query without
 * touching a single component.
 */

/**
 * Drives the citation's leading-edge bar:
 * heavy = coral, resolved/normal = teal, unresolved = dim red.
 */
export type CopilotCitationTone = "heavy" | "resolved" | "unresolved";

export interface CopilotFact {
  label: string;
  value: string;
  /**
   * Render the value in the monospace face reserved for raw LEON tokens
   * (flight numbers, crew codes, rule names).  Prose stays in the body face.
   */
  raw?: boolean;
}

export interface CopilotCitation {
  tone: CopilotCitationTone;
  headline: string;
  facts: CopilotFact[];
  /**
   * Mandatory, and deliberately not optional in the type: literally what was
   * queried, e.g. "LEON · unique_id 660214 · EXTRA_COCKPIT_CREW".  This line is
   * what makes an answer safe to act on, so a data-backed answer cannot be
   * constructed without it.
   */
  source: string;
}

export interface CopilotAnswer {
  /** Plain-language sentence. Lead with the number or status, then the reason. */
  text: string;
  /** Present only when the answer is backed by a specific LEON record. */
  citation?: CopilotCitation;
}

/**
 * Resolves a question against LEON.  Reject with an Error whose message names
 * what is missing — the panel surfaces it verbatim, in the product's own plain
 * error voice.
 */
export type CopilotTransport = (
  question: string,
  signal: AbortSignal,
) => Promise<CopilotAnswer>;

export type CopilotMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string; citation?: CopilotCitation }
  | { id: string; role: "error"; text: string };

export interface CopilotQuickTopic {
  id: string;
  /** Chip label. */
  label: string;
  /** The question actually sent when the chip is used. */
  question: string;
}
