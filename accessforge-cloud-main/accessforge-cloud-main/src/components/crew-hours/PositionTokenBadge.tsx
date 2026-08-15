import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";
import { displayValue } from "./format";
import { isPositioningToken } from "./filters";

export function PositionTokenBadge({ position }: { position: string | null }) {
  const { t } = useI18n();
  const token = displayValue(position);
  if (token === "—") {
    return <span className="text-xs text-muted-foreground">—</span>;
  }

  const isPositioning = isPositioningToken(position);
  const badge = (
    <Badge
      variant={isPositioning ? "outline" : "secondary"}
      className={`px-1.5 py-0 text-[10px] font-mono ${
        isPositioning
          ? "border-warning/40 bg-warning/15 text-warning-foreground"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {token}
    </Badge>
  );

  if (!isPositioning) {
    return badge;
  }

  const positioningCue = t("crew.positioning.cue");
  const positioningDescription = t("crew.positioning.description");

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          tabIndex={0}
          className="inline-flex items-center gap-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          aria-label={positioningDescription}
        >
          {badge}
          <span className="text-[10px] font-medium text-warning-foreground">{positioningCue}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p className="text-xs">{positioningDescription}</p>
      </TooltipContent>
    </Tooltip>
  );
}
