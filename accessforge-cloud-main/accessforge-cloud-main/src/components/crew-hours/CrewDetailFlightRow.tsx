import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";
import { displayAircraft, displayUtcTime, displayValue } from "./format";
import { isLocallyResolvedHeavy, localResolutionMessage } from "./messages";
import { PositionTokenBadge } from "./PositionTokenBadge";
import type { CrewMemberSummary, FlightItem, HeavyTraceStep } from "./types";

function formatTraceInput(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => (item === null ? "—" : String(item))).join(", ");
  }
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function HeavyTrace({ trace }: { trace: HeavyTraceStep[] }) {
  return (
    <ol className="mt-1 space-y-1 border-t border-border/40 pt-1">
      {trace.map((step, index) => (
        <li key={`${step.step}-${index}`} className="font-mono text-[10px] leading-snug">
          <span className="font-semibold">{step.step}</span>: {step.outcome}
          {step.inputs && Object.keys(step.inputs).length > 0 && (
            <span className="block pl-3 text-muted-foreground">
              {Object.entries(step.inputs)
                .map(([key, value]) => `${key}=${formatTraceInput(value)}`)
                .join("  ")}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

export function CrewDetailFlightRow({
  crew,
  flight,
}: {
  crew: CrewMemberSummary;
  flight: FlightItem;
}) {
  const { t } = useI18n();
  const augmentedLabel =
    flight.augmented_heavy === true
      ? t("crew.augmented.yes")
      : flight.augmented_heavy === false
        ? t("crew.augmented.no")
        : t("crew.augmented.unknown");
  // The trace is the durable answer to "why does this row say that?" — every
  // leg carries one, so a wrong verdict is read, not guessed at from a
  // screenshot.
  const trace = flight.heavy_trace ?? [];
  const hasProvenance = Boolean(
    flight.heavy_source ||
    flight.heavy_reason ||
    (flight.leon_heavy !== undefined && flight.leon_heavy !== null) ||
    (flight.derived_heavy !== undefined && flight.derived_heavy !== null) ||
    flight.heavy_conflict ||
    flight.unknown_resolved ||
    trace.length > 0,
  );
  // The verdict was absent from LEON's augmented data and resolved by the
  // local rotation rule — flagged with a red badge so the provenance is
  // visible at a glance, not only inside the tooltip.
  const locallyResolved = isLocallyResolvedHeavy(flight);
  const leonLabel =
    flight.leon_heavy === true
      ? t("crew.augmented.yes")
      : flight.leon_heavy === false
        ? t("crew.augmented.no")
        : t("crew.augmented.unknown");
  const derivedLabel =
    flight.derived_heavy === true
      ? t("crew.augmented.yes")
      : flight.derived_heavy === false
        ? t("crew.augmented.no")
        : t("crew.augmented.unknown");

  return (
    <tr className="hover:bg-muted/10">
      <td className="whitespace-nowrap px-4 py-2.5 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span>{displayValue(crew.position_type)}</span>
          <PositionTokenBadge position={flight.position} />
        </div>
      </td>
      <td className="px-4 py-2.5" />
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayValue(flight.flight_date)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-xs">
        {displayAircraft(flight.aircraft_reg, flight.aircraft_type)}
      </td>
      <td
        className="whitespace-nowrap px-4 py-2.5 font-mono text-xs font-medium"
        title={flight.flight_nid}
      >
        {displayValue(flight.flight_number)}
      </td>
      <td className="px-4 py-2.5">
        <Badge variant="outline" className="font-mono">
          {displayValue(flight.departure_airport)}
        </Badge>
      </td>
      <td className="px-4 py-2.5">
        <Badge variant="outline" className="font-mono">
          {displayValue(flight.arrival_airport)}
        </Badge>
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayUtcTime(flight.start_time_utc)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayUtcTime(flight.end_time_utc)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs">
        {displayValue(flight.block_time)}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-xs">
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              className="inline-flex items-center gap-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              aria-label={`${t("crew.table.augmented_heavy")}: ${augmentedLabel}`}
            >
              <Badge variant="outline">{augmentedLabel}</Badge>
              {flight.heavy_conflict && (
                <span
                  role="img"
                  aria-label={t("crew.heavy.conflict")}
                  data-testid="heavy-conflict-marker"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-destructive/15 text-[10px] font-bold text-destructive"
                >
                  !
                </span>
              )}
              {locallyResolved && (
                <span
                  role="img"
                  aria-label={localResolutionMessage(t)}
                  data-testid="local-resolution-marker"
                  className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground"
                >
                  !
                </span>
              )}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {hasProvenance ? (
              <div className="space-y-1">
                {flight.heavy_source && (
                  <p>
                    {t("crew.heavy.source")}: {flight.heavy_source}
                  </p>
                )}
                {flight.heavy_reason && (
                  <p>
                    {t("crew.heavy.reason")}: {flight.heavy_reason}
                  </p>
                )}
                {flight.leon_heavy !== undefined && flight.leon_heavy !== null && (
                  <p>
                    {t("crew.heavy.leon")}: {leonLabel}
                  </p>
                )}
                {flight.derived_heavy !== undefined && flight.derived_heavy !== null && (
                  <p>
                    {t("crew.heavy.derived")}: {derivedLabel}
                  </p>
                )}
                {/* Shown whenever STEP 4 ran, badge or not: the reason is
                    diagnostic, while the badge is a claim about the verdict. */}
                {flight.unknown_resolution_reason && (
                  <p>
                    {t("crew.heavy.unknown_resolution")}: {flight.unknown_resolution_reason}
                  </p>
                )}
                {locallyResolved && <p>{localResolutionMessage(t)}</p>}
                {(flight.is_training_position || flight.is_training_function) && (
                  <p>
                    {t("crew.heavy.training")}:{" "}
                    {[
                      flight.is_training_position ? t("crew.heavy.training_position") : null,
                      flight.is_training_function ? t("crew.heavy.training_function") : null,
                    ]
                      .filter(Boolean)
                      .join(" + ")}
                  </p>
                )}
                {flight.heavy_conflict && <p>{t("crew.heavy.conflict")}</p>}
                {trace.length > 0 && (
                  <details data-testid="heavy-trace" className="max-w-md">
                    <summary className="cursor-pointer text-xs">
                      {t("crew.heavy.trace")}
                    </summary>
                    <HeavyTrace trace={trace} />
                  </details>
                )}
              </div>
            ) : (
              <p>{t("crew.heavy.unavailable")}</p>
            )}
          </TooltipContent>
        </Tooltip>
      </td>
    </tr>
  );
}
