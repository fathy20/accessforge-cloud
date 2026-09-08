"""Back-test the shadow FDP model against the live Crew Hours report.

For each requested month this pulls the same report the UI shows (LEON MCP
rows + FTL index + flight-list context), then compares, leg by leg, the
regulatory FDP assessment (``FlightItem.fdp_shadow``) with what the product
currently displays (``effective_heavy``) and credits (``duty_credit``). It
writes every leg, the disagreements, and a summary — the evidence the owner
rulings R1–R7 in docs/architecture/heavy-fdp-regulatory-model-plan-2026-09-03.md
need. Crew are identified by code only.

``classification`` and ``credit_vs_fdp`` compare a Red Sea business verdict
against a regulatory model. **Disagreement is the expected state, not an
error signal**: Heavy is decided by the owner's rulings, LEON's
``crewAugmentation`` and the approved precedence table, while the shadow model
reports only whether a duty is longer than the base two-pilot table limit.
Augmentation does not imply an overrun (49 of 779 augmented June duties, the
median about 5 h under the limit) and an overrun does not imply Heavy (split
duty, commander's discretion, the cabin +1:00 and the positioning-landings
exclusion are lawful without extra crew). Read the columns as a diagnostic;
nothing produced here may move a verdict, a credit, an export cell or a total.

Usage (reads LEON_* from the environment / .env, exactly like the app):

    python -m backend.statistics.crew_hours.tools.fdp_backtest \
        --months 2026-06 2026-07 --out ../../refrance_output/fdp_backtest

Read-only against LEON; touches no database table.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import backend.config  # noqa: F401  (loads .env files the way the app does)

from ..leon_client import get_crew_hours_leon_client
from ..service import LiveCrewHoursService

FIELDS = [
    "month", "flight_date", "flight_number", "route", "crew_code", "position",
    "start_utc", "end_utc", "leon_heavy", "effective_heavy", "heavy_source",
    "heavy_reason", "unknown_resolved", "duty_credit", "credit_source",
    "fdp_planned", "fdp_limit", "fdp_margin", "fdp_band", "fdp_sectors",
    "fdp_table", "fdp_needs_augmentation", "classification", "credit_vs_fdp",
]


def month_range(year_month: str) -> tuple[str, str]:
    year, month = (int(part) for part in year_month.split("-"))
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def classify(effective: bool | None, needs: bool | None) -> str:
    if needs is None:
        return "no_shadow"
    if effective is None:
        return "verdict_unknown"
    if effective == needs:
        return "agree"
    return "shadow_heavy_verdict_no" if needs else "shadow_no_verdict_heavy"


def credit_vs_fdp(credit: bool | None, needs: bool | None) -> str:
    if credit is None or needs is None:
        return "n/a"
    if credit == needs:
        return "agree"
    return "fdp_heavy_not_credited" if needs else "credited_fdp_not_heavy"


def collect(service: LiveCrewHoursService, year_month: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from_date, to_date = month_range(year_month)
    response = service.get_crew_hours_report(from_date, to_date, "All", None)
    rows: list[dict[str, Any]] = []
    for member in response.crew_members:
        code = member.person_code or member.crew_id
        for flight in member.flights:
            shadow = flight.fdp_shadow
            needs = shadow.needs_augmentation if shadow else None
            rows.append({
                "month": year_month,
                "flight_date": flight.flight_date,
                "flight_number": flight.flight_number,
                "route": f"{flight.departure_airport or '?'}-{flight.arrival_airport or '?'}",
                "crew_code": code,
                "position": flight.position,
                "start_utc": flight.start_time_utc,
                "end_utc": flight.end_time_utc,
                "leon_heavy": flight.leon_heavy,
                "effective_heavy": flight.effective_heavy,
                "heavy_source": flight.heavy_source,
                "heavy_reason": flight.heavy_reason,
                "unknown_resolved": flight.unknown_resolved,
                "duty_credit": flight.duty_credit,
                "credit_source": flight.credit_source,
                "fdp_planned": shadow.planned if shadow else None,
                "fdp_limit": shadow.limit if shadow else None,
                "fdp_margin": shadow.margin if shadow else None,
                "fdp_band": shadow.band if shadow else None,
                "fdp_sectors": shadow.sectors if shadow else None,
                "fdp_table": shadow.table if shadow else None,
                "fdp_needs_augmentation": needs,
                "classification": classify(flight.effective_heavy, needs),
                "credit_vs_fdp": credit_vs_fdp(flight.duty_credit, needs),
            })
    meta = {
        "month": year_month,
        "from": from_date,
        "to": to_date,
        "total_crew": response.total_crew,
        "total_flights": response.total_flights,
        "records_count": response.records_count,
        "join_health": response.join_health,
        "augmented_lookup": f"{response.augmented_lookup_hits}/{response.augmented_lookup_attempts}",
        "crew_context": f"{response.crew_context_hits}/{response.crew_context_attempts}",
        "cabin_trainee_detection": response.cabin_trainee_detection,
        "member_flight_rows": len(rows),
    }
    return rows, meta


def summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_class = Counter(row["classification"] for row in rows)
    by_credit = Counter(row["credit_vs_fdp"] for row in rows)
    disagreements = [row for row in rows if row["classification"].startswith("shadow_")]
    by_reason: dict[str, Counter] = defaultdict(Counter)
    for row in disagreements:
        by_reason[row["classification"]][row["heavy_reason"] or "-"] += 1
    by_route: dict[str, Counter] = defaultdict(Counter)
    for row in disagreements:
        by_route[row["classification"]][row["route"]] += 1
    # Distinct duties in disagreement (by crew + duty legs is not exposed; use crew+date+class).
    return {
        "rows": len(rows),
        "by_classification": dict(by_class),
        "credit_vs_fdp": dict(by_credit),
        "disagreement_by_heavy_reason": {k: dict(v) for k, v in by_reason.items()},
        "disagreement_by_route": {k: dict(v.most_common(15)) for k, v in by_route.items()},
        "distinct_flights_in_disagreement": len({(r["flight_date"], r["flight_number"]) for r in disagreements}),
        "distinct_crew_in_disagreement": len({r["crew_code"] for r in disagreements}),
    }


def write_outputs(out: Path, rows: list[dict[str, Any]], metas: list[dict[str, Any]]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "all_legs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    disagreements = [row for row in rows if row["classification"].startswith("shadow_")]
    with (out / "disagreements.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(disagreements)
    summary = {
        "months": metas,
        "overall": summarise(rows),
        "per_month": {meta["month"]: summarise([r for r in rows if r["month"] == meta["month"]]) for meta in metas},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# FDP shadow back-test", ""]
    for meta in metas:
        lines.append(
            f"- **{meta['month']}**: {meta['total_flights']} flights, {meta['total_crew']} crew, "
            f"{meta['member_flight_rows']} member-legs, join_health {meta['join_health']}, "
            f"augmented {meta['augmented_lookup']}, crew_context {meta['crew_context']}"
        )
    lines += ["", "## Verdict vs shadow (member-legs)", ""]
    for key, value in sorted(summary["overall"]["by_classification"].items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Credit vs shadow (member-legs)", ""]
    for key, value in sorted(summary["overall"]["credit_vs_fdp"].items()):
        lines.append(f"- {key}: {value}")
    lines += ["", "## Disagreements by current heavy_reason", ""]
    for cls, reasons in summary["overall"]["disagreement_by_heavy_reason"].items():
        lines.append(f"- {cls}:")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - {reason}: {count}")
    lines += ["", "## Disagreements by route (top 15)", ""]
    for cls, routes in summary["overall"]["disagreement_by_route"].items():
        lines.append(f"- {cls}:")
        for route, count in routes.items():
            lines.append(f"  - {route}: {count}")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--months", nargs="+", required=True, help="YYYY-MM ...")
    parser.add_argument("--out", required=True, help="Output directory")
    args = parser.parse_args(argv)

    service = LiveCrewHoursService(get_crew_hours_leon_client())
    rows: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    for year_month in args.months:
        print(f"Fetching {year_month} ...", file=sys.stderr, flush=True)
        month_rows, meta = collect(service, year_month)
        print(f"  {meta}", file=sys.stderr, flush=True)
        rows.extend(month_rows)
        metas.append(meta)

    summary = write_outputs(Path(args.out), rows, metas)
    print(json.dumps(summary["overall"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
