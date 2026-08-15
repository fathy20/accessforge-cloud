import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useI18n } from "@/lib/i18n";
import { CopilotLauncher } from "./CopilotLauncher";
import { CopilotPanel } from "./CopilotPanel";
import type { CopilotMessage, CopilotQuickTopic, CopilotTransport } from "./types";

let messageCounter = 0;
const nextMessageId = () => `copilot-${(messageCounter += 1)}`;

/**
 * RedSea Copilot — floating launcher plus the docked assistant panel.
 *
 * Mount once inside the app shell.  All data comes from `transport`; the panel
 * itself knows nothing about LEON.
 */
export function RedSeaCopilot({ transport }: { transport: CopilotTransport }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const quickTopics = useMemo<CopilotQuickTopic[]>(
    () => [
      {
        id: "crew-hours",
        label: t("copilot.chip.crew_hours"),
        question: t("copilot.chip.crew_hours_question"),
      },
      {
        id: "heavy-status",
        label: t("copilot.chip.heavy_status"),
        question: t("copilot.chip.heavy_status_question"),
      },
      {
        id: "rosters",
        label: t("copilot.chip.rosters"),
        question: t("copilot.chip.rosters_question"),
      },
    ],
    [t],
  );

  const close = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setOpen(false);
    launcherRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, close]);

  // Never leave an in-flight LEON query running behind an unmounted panel.
  useEffect(() => () => abortRef.current?.abort(), []);

  const ask = useCallback(
    async (question: string) => {
      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;

      setMessages((current) => [
        ...current,
        { id: nextMessageId(), role: "user", text: question },
      ]);
      setBusy(true);

      try {
        const answer = await transport(question, controller.signal);
        if (controller.signal.aborted) return;
        setMessages((current) => [
          ...current,
          {
            id: nextMessageId(),
            role: "assistant",
            text: answer.text,
            citation: answer.citation,
          },
        ]);
      } catch (error) {
        if (controller.signal.aborted) return;
        setMessages((current) => [
          ...current,
          {
            id: nextMessageId(),
            role: "error",
            text: error instanceof Error && error.message ? error.message : t("copilot.error"),
          },
        ]);
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
          setBusy(false);
        }
      }
    },
    [transport, t],
  );

  return (
    <>
      <CopilotLauncher ref={launcherRef} expanded={open} onClick={() => setOpen(true)} />
      {open && (
        <CopilotPanel
          messages={messages}
          busy={busy}
          quickTopics={quickTopics}
          onClose={close}
          onAsk={ask}
        />
      )}
    </>
  );
}
