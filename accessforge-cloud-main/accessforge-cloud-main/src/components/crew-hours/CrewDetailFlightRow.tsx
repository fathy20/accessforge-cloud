import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";
import { displayAircraft, displayUtcTime, displayValue } from "./format";
import { PositionTokenBadge } from "./PositionTokenBadge";
import type { CrewMemberSummary, FlightItem } from "./types";

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
  const hasProvenance = Boolean(
    flight.heavy_source ||
    flight.heavy_reason ||
    (flight.leon_heavy !== undefined && flight.leon_heavy !== null) ||
    (flight.derived_heavy !== undefined && flight.derived_heavy !== null) ||
    flight.heavy_conflict ||
    flight.unknown_resolved,
  );
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
                {flight.unknown_resolved && flight.unknown_resolution_reason && (
                  <p>
                    {t("crew.heavy.unknown_resolution")}: {flight.unknown_resolution_reason}
                  </p>
                )}
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
