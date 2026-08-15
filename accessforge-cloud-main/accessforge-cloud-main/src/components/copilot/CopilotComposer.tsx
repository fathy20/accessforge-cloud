import { useState, type FormEvent } from "react";
import { ArrowUp } from "lucide-react";

import { Input } from "@/components/ui/input";
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
    <div className="border-t border-border p-3">
      <ul className="mb-2.5 flex flex-wrap gap-1.5">
        {quickTopics.map((topic) => (
          <li key={topic.id}>
            <button
              type="button"
              disabled={busy}
              onClick={() => submit(topic.question)}
              className="rounded-full border border-border px-2.5 py-1 text-[10.5px] leading-none font-medium text-fg-secondary transition-colors hover:bg-interactive-hover disabled:pointer-events-none disabled:opacity-50"
            >
              {topic.label}
            </button>
          </li>
        ))}
      </ul>

      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <Input
          ref={inputRef}
          value={value}
          disabled={busy}
          onChange={(event) => setValue(event.target.value)}
          placeholder={t("copilot.input_placeholder")}
          aria-label={t("copilot.input_label")}
          className="h-9 flex-1 border-input bg-card text-body shadow-none placeholder:text-fg-disabled"
        />
        {/* Coral stays reserved for the single primary action, as it is elsewhere. */}
        <button
          type="submit"
          disabled={busy || !value.trim()}
          aria-label={t("copilot.send")}
          className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-md bg-primary text-primary-foreground transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-40"
        >
          <ArrowUp className="size-4" aria-hidden="true" />
        </button>
      </form>
    </div>
  );
}
