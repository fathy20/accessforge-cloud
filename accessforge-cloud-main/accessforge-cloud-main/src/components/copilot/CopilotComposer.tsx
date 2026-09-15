import { useState, type FormEvent } from "react";
import { ArrowUp } from "lucide-react";

import { useI18n } from "@/lib/i18n";
import type { CopilotQuickTopic } from "./types";

export function CopilotComposer({
  quickTopics,
  busy,
  inputRef,
  onSubmit,
}: {
  quickTopics: CopilotQuickTopic[];
  busy: boolean;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  onSubmit: (question: string) => void;
}) {
  const { t } = useI18n();
  const [value, setValue] = useState("");

  const submit = (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    setValue("");
    onSubmit(trimmed);
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(value);
  };

  return (
    // shrink-0 keeps the composer at its natural height so only the thread
    // scrolls — without it the flex child collapses and the panel scrolls.
    <div
      className="shrink-0 border-t p-3"
      style={{ borderColor: "var(--copilot-border)" }}
    >
      <ul className="mb-2.5 flex flex-wrap gap-1.5">
        {quickTopics.map((topic) => (
          <li key={topic.id}>
            <button
              type="button"
              disabled={busy}
              onClick={() => submit(topic.question)}
              className="rounded-full border px-2.5 py-1 text-[12px] font-semibold whitespace-nowrap transition-colors hover:border-[var(--copilot-accent-1)] hover:text-[var(--copilot-accent-1)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--copilot-accent-1)] disabled:pointer-events-none disabled:opacity-50"
              style={{ borderColor: "var(--copilot-control)", color: "var(--copilot-secondary)" }}
            >
              {topic.label}
            </button>
          </li>
        ))}
      </ul>

      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-full border py-1 pe-1 ps-4 transition-colors focus-within:border-[var(--copilot-accent-1)]"
        style={{ borderColor: "var(--copilot-control)", background: "var(--copilot-surface)" }}
      >
        <input
          ref={inputRef}
          value={value}
          disabled={busy}
          onChange={(event) => setValue(event.target.value)}
          placeholder={t("copilot.input_placeholder")}
          aria-label={t("copilot.input_label")}
          className="min-w-0 flex-1 bg-transparent text-[13.5px] outline-none placeholder:text-[var(--copilot-faint)] disabled:opacity-50"
          style={{ color: "var(--copilot-ink)" }}
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          aria-label={t("copilot.send")}
          className="grid size-[38px] shrink-0 cursor-pointer place-items-center rounded-full transition-[filter] hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--copilot-accent-1)] disabled:pointer-events-none disabled:opacity-40"
          style={{
            background:
              "linear-gradient(135deg, var(--copilot-accent-1), var(--copilot-accent-2))",
            color: "var(--copilot-on-accent)",
          }}
        >
          <ArrowUp className="size-4" aria-hidden="true" />
        </button>
      </form>
    </div>
  );
}
