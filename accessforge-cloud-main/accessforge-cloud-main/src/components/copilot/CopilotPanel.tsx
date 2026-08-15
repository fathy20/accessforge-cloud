import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import { useI18n } from "@/lib/i18n";
import { CopilotComposer } from "./CopilotComposer";
import { CopilotMessageItem } from "./CopilotMessageItem";
import { CopilotPill } from "./CopilotPill";
import type { CopilotMessage, CopilotQuickTopic } from "./types";

export function CopilotPanel({
  messages,
  busy,
  quickTopics,
  onClose,
  onAsk,
}: {
  messages: CopilotMessage[];
  busy: boolean;
  quickTopics: CopilotQuickTopic[];
  onClose: () => void;
  onAsk: (question: string) => void;
}) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Keep the newest turn in view. Assigning scrollTop rather than calling
  // scrollIntoView keeps this safe in non-browser render environments.
  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [messages.length, busy]);

  return (
    <>
      {/*
        The page underneath stays visible and dimmed — the panel is a layer on
        top of whatever the user was already doing, never a replacement for it.
      */}
      <div
        data-testid="copilot-scrim"
        onClick={onClose}
        className="fixed inset-0 z-shell-overlay bg-black/45"
        aria-hidden="true"
      />

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="copilot-title"
        aria-describedby="copilot-subtitle"
        className="fixed end-3 top-3 bottom-3 z-shell-overlay flex w-[400px] max-w-[calc(100vw-1.5rem)] flex-col overflow-hidden rounded-lg border border-border bg-background shadow-copilot-panel"
      >
        <header className="flex items-start gap-3 border-b border-border p-3">
          {/* The product's existing logo convention: real wave mark, white tile, never recolored. */}
          <div className="grid size-9 shrink-0 place-items-center rounded-md border border-border/50 bg-white p-1.5">
            <img
              src="/logo.png"
              alt={t("shell.brand.logo_alt")}
              className="h-full w-full object-contain"
            />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 id="copilot-title" className="text-heading-3 text-fg-primary">
                {t("copilot.title")}
              </h2>
              <CopilotPill tone="spark">{t("copilot.beta")}</CopilotPill>
            </div>
            <p id="copilot-subtitle" className="mt-0.5 text-caption text-fg-muted">
              {t("copilot.subtitle")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("copilot.close")}
            className="grid size-7 shrink-0 cursor-pointer place-items-center rounded-md text-fg-muted transition-colors hover:bg-interactive-hover hover:text-fg-primary"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        <div ref={threadRef} className="flex-1 overflow-y-auto p-3">
          {messages.length === 0 ? (
            <p className="text-body text-fg-muted">{t("copilot.empty")}</p>
          ) : (
            <ul
              aria-label={t("copilot.thread_label")}
              aria-live="polite"
              aria-busy={busy}
              className="flex flex-col gap-3.5"
            >
              {messages.map((message) => (
                <CopilotMessageItem key={message.id} message={message} />
              ))}
              {busy && (
                <li className="text-body text-fg-muted">{t("copilot.thinking")}</li>
              )}
            </ul>
          )}
        </div>

        <CopilotComposer
          quickTopics={quickTopics}
          busy={busy}
          inputRef={inputRef}
          onSubmit={onAsk}
        />
      </aside>
    </>
  );
}
