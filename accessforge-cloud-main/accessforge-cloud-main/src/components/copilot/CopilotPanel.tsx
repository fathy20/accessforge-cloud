import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import { useI18n } from "@/lib/i18n";
import { CopilotAvatar } from "./CopilotAvatar";
import { CopilotComposer } from "./CopilotComposer";
import { CopilotEmptyState } from "./CopilotEmptyState";
import { CopilotMessageItem } from "./CopilotMessageItem";
import { CopilotPill } from "./CopilotPill";
import type { CopilotMessage, CopilotQuickTopic } from "./types";

export function CopilotPanel({
  messages,
  busy,
  quickTopics,
  firstName,
  onClose,
  onAsk,
  onNewChat,
}: {
  messages: CopilotMessage[];
  busy: boolean;
  quickTopics: CopilotQuickTopic[];
  firstName: string;
  onClose: () => void;
  onAsk: (question: string) => void;
  onNewChat: () => void;
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
        className="fixed end-0 top-0 bottom-0 z-shell-overlay flex w-[440px] max-w-[100vw] flex-col overflow-hidden border-s"
        style={{ background: "var(--copilot-panel)", borderColor: "var(--copilot-border)" }}
      >
        <header
          className="flex shrink-0 items-center gap-3 border-b p-3.5"
          style={{ borderColor: "var(--copilot-border)" }}
        >
          <CopilotAvatar size={34} alt={t("shell.brand.logo_alt")} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2
                id="copilot-title"
                className="text-[15.5px] font-semibold"
                style={{ fontFamily: "var(--font-display)", color: "var(--copilot-ink)" }}
              >
                {t("copilot.title")}
              </h2>
              <CopilotPill tone="spark">{t("copilot.beta")}</CopilotPill>
            </div>
            <p
              id="copilot-subtitle"
              className="mt-0.5 text-[11.5px]"
              style={{ color: "var(--copilot-muted)" }}
            >
              {t("copilot.subtitle")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("copilot.close")}
            className="grid size-[30px] shrink-0 cursor-pointer place-items-center rounded-md border transition-colors hover:text-[var(--copilot-ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--copilot-accent-1)]"
            style={{ borderColor: "var(--copilot-border)", color: "var(--copilot-muted)" }}
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </header>

        {/* min-h-0 is what actually lets this flex child scroll instead of
            growing and pushing the composer off the bottom. */}
        <div ref={threadRef} className="min-h-0 flex-1 overflow-y-auto p-3.5">
          {messages.length === 0 ? (
            <CopilotEmptyState
              firstName={firstName}
              quickTopics={quickTopics}
              onAsk={onAsk}
            />
          ) : (
            <ul
              aria-label={t("copilot.thread_label")}
              aria-live="polite"
              aria-busy={busy}
              className="flex flex-col gap-4"
            >
              {messages.map((message) => (
                <CopilotMessageItem
                  key={message.id}
                  message={message}
                  onNewChat={message.role === "assistant" ? onNewChat : undefined}
                />
              ))}
              {busy && (
                <li className="flex items-center gap-2.5">
                  <CopilotAvatar size={26} alt={t("shell.brand.logo_alt")} />
                  {/* The dots are decorative; aria-busy on the list is what
                      announces the wait, so screen readers are not told about
                      three pulsing circles. */}
                  <span className="flex items-center gap-1.5" aria-hidden="true">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="copilot-dot block size-1.5 rounded-full"
                        style={{
                          background: "var(--copilot-accent-1)",
                          animationDelay: `${i * 0.2}s`,
                        }}
                      />
                    ))}
                  </span>
                  <span className="sr-only">{t("copilot.thinking")}</span>
                </li>
              )}
            </ul>
          )}
        </div>

        <CopilotComposer
          /* The empty state already offers these three as cards. Showing the
             chips too would put two buttons for the same question on screen at
             once, so the chips appear only once a conversation has started. */
          quickTopics={messages.length === 0 ? [] : quickTopics}
          busy={busy}
          inputRef={inputRef}
          onSubmit={onAsk}
        />
      </aside>
    </>
  );
}
