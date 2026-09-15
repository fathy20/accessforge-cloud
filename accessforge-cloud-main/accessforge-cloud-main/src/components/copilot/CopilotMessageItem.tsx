import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { CopilotAvatar } from "./CopilotAvatar";
import { CopilotCitationCard } from "./CopilotCitationCard";
import type { CopilotMessage } from "./types";

export function CopilotMessageItem({
  message,
  onNewChat,
}: {
  message: CopilotMessage;
  onNewChat?: () => void;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  if (message.role === "user") {
    return (
      <li className="copilot-rise flex justify-end">
        <p
          className="max-w-[85%] px-3 py-2 text-[13.5px]"
          style={{
            background: "var(--copilot-bubble)",
            color: "var(--copilot-ink)",
            borderRadius: "16px 16px 4px 16px",
          }}
        >
          <span className="sr-only">{t("copilot.role.you")}: </span>
          {message.text}
        </p>
      </li>
    );
  }

  if (message.role === "error") {
    // The spec describes only user and assistant turns, but the transport can
    // reject and the product has a plain error voice for it. Dropping this row
    // would silently swallow failures, so it stays.
    return (
      <li className="copilot-rise flex justify-start gap-2.5">
        <CopilotAvatar size={26} alt={t("shell.brand.logo_alt")} />
        <div className="max-w-[85%] rounded-md border border-status-danger-border bg-status-danger-background px-3 py-2">
          <p className="text-[13.5px] text-status-danger-foreground">
            <span className="sr-only">{t("copilot.role.copilot")}: </span>
            {message.text}
          </p>
        </div>
      </li>
    );
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard is unavailable in insecure contexts and some webviews; the
      // answer is still selectable, so this is not worth an error toast.
    }
  };

  return (
    <li className="copilot-rise flex justify-start gap-2.5">
      <CopilotAvatar size={26} alt={t("shell.brand.logo_alt")} />
      <div className="min-w-0 max-w-[85%]">
        <p
          className="text-[13.5px] leading-[1.6]"
          style={{ color: "var(--copilot-answer)" }}
        >
          <span className="sr-only">{t("copilot.role.copilot")}: </span>
          {message.text}
        </p>

        {message.citation && <CopilotCitationCard citation={message.citation} />}

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <ActionPill onClick={copy}>
            {copied ? t("copilot.copied") : t("copilot.copy")}
          </ActionPill>
          {onNewChat && (
            <ActionPill onClick={onNewChat}>{t("copilot.new_chat")}</ActionPill>
          )}
        </div>
      </div>
    </li>
  );
}

function ActionPill({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border px-2.5 py-1 text-[11.5px] font-semibold whitespace-nowrap transition-colors hover:border-[var(--copilot-accent-1)] hover:text-[var(--copilot-accent-1)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--copilot-accent-1)]"
      style={{ borderColor: "var(--copilot-control)", color: "var(--copilot-muted)" }}
    >
      {children}
    </button>
  );
}
