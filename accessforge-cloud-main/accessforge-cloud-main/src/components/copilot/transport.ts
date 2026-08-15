import { ApiClient } from "@/lib/apiClient";
import type { CopilotAnswer, CopilotTransport } from "./types";

/**
 * Placeholder transport. Refuses plainly rather than inventing an answer —
 * kept for tests and for shells where LEON is deliberately not wired.
 */
export function createUnconnectedTransport(message: string): CopilotTransport {
  return async () => {
    throw new Error(message);
  };
}

function apiErrorDetail(error: unknown): string | null {
  if (typeof error !== "object" || error === null) return null;
  const detail = (error as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "Copilot could not reach the server.";
}

/** What POST /api/copilot/ask returns; a superset of CopilotAnswer. */
export interface CopilotAskResponse extends CopilotAnswer {
  thread_id?: string | null;
  approval_required?: boolean;
  pending_tool_names?: string[];
}

/**
 * Live transport: RedSea Copilot -> our backend -> LEON's own Wingman chat.
 *
 * Wingman is stateful, so the thread id from each reply is carried into the
 * next question. When Wingman asks permission to read LEON data, the answer
 * comes back with approval_required set and the caller is told — we never
 * approve an assistant's data access on the user's behalf.
 */
export function createWingmanTransport(options?: {
  /** Forwarded to Wingman as localContext, e.g. the page the user asked from. */
  localContext?: () => string | undefined;
  onThreadChange?: (threadId: string | null) => void;
  onApprovalRequired?: (threadId: string, toolNames: string[]) => void;
}): CopilotTransport {
  let threadId: string | null = null;

  return async (question, signal) => {
    let response: CopilotAskResponse;
    try {
      response = (await ApiClient.fetch("/copilot/ask", {
        method: "POST",
        signal,
        body: JSON.stringify({
          question,
          thread_id: threadId,
          local_context: options?.localContext?.() ?? null,
        }),
      })) as CopilotAskResponse;
    } catch (error) {
      // ApiClient drops the server's detail for 5xx and shows a generic message.
      // Copilot needs the specific reason instead — naming what failed is the
      // difference between a usable refusal and a shrug.
      throw new Error(apiErrorDetail(error) ?? errorMessage(error));
    }

    if (response.thread_id && response.thread_id !== threadId) {
      threadId = response.thread_id;
      options?.onThreadChange?.(threadId);
    }
    if (response.approval_required && response.thread_id) {
      options?.onApprovalRequired?.(response.thread_id, response.pending_tool_names ?? []);
    }

    return { text: response.text, citation: response.citation };
  };
}
