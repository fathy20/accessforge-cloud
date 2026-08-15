import { useI18n } from "@/lib/i18n";
import { CopilotCitationCard } from "./CopilotCitationCard";
import type { CopilotMessage } from "./types";

export function CopilotMessageItem({ message }: { message: CopilotMessage }) {
  const { t } = useI18n();

  if (message.role === "user") {
    return (
      <li className="flex justify-end">
        <p className="max-w-[85%] rounded-md rounded-ee-sm border border-border bg-card px-3 py-2 text-body text-fg-primary">
          <span className="sr-only">{t("copilot.role.you")}: </span>
          {message.text}
        </p>
      </li>
    );
  }

  if (message.role === "error") {
    // Same plain voice as the product's own "Report source unavailable" state:
    // name what is missing, do not soften it.
    return (
      <li className="flex justify-start">
        <div className="max-w-[92%] rounded-md border border-status-danger-border bg-status-danger-background px-3 py-2">
          <p className="text-body text-status-danger-foreground">
            <span className="sr-only">{t("copilot.role.copilot")}: </span>
            {message.text}
          </p>
        </div>
      </li>
    );
  }

  return (
    <li className="flex justify-start">
      <div className="max-w-[92%]">
        <p className="text-body text-fg-primary">
          <span className="sr-only">{t("copilot.role.copilot")}: </span>
          {message.text}
        </p>
        {message.citation && <CopilotCitationCard citation={message.citation} />}
      </div>
    </li>
  );
}
