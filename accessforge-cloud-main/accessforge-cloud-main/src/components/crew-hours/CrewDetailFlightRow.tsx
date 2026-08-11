import { Badge } from "@/components/ui/badge";
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
        <Badge variant="outline">
          {flight.augmented_heavy === true
            ? t("crew.augmented.yes")
            : flight.augmented_heavy === false
              ? t("crew.augmented.no")
              : t("crew.augmented.unknown")}
        </Badge>
      </td>
    </tr>
  );
}
