# API — Crew Hours (statistics)

Router: `backend/statistics/crew_hours/router.py`, mounted under
`/api/statistics` (`backend/statistics/router.py`). Permissions come from the
grants system (DB-backed), not roles.

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/api/statistics/crew-hours/report` | `crew_hours.view` | Month report, `CrewHoursReportResponse` |
| GET | `/api/statistics/crew-hours/report/export` | `crew_hours.view` + `crew_hours.export` | Export download |
| POST | `/api/statistics/crew-hours` | — | Returns 501 (reserved) |

## Response metadata that carries verdict provenance (`schemas.py`)

- `heavy_source` — where the Heavy verdict came from (`LEON`, `LOCAL_RULE`, …).
- `heavy_conflict` — True when an airport absolute (EVN/SVX) overrode a
  disagreeing LEON value.
- `unknown_resolved` — True only for legs decided by the STEP 4 rotation
  resolver; together with `heavy_source=LOCAL_RULE` this drives the red badge
  ("Not found in LEON augmented data — resolved by local rotation rule",
  EN + AR).
- `join_health` — "OK" or "DEGRADED" (hit rate < 50% against a non-empty
  index); plus `augmented_lookup_hits/attempts`, `crew_context_hits/attempts`.
  The join key itself is confirmed (`unique_id == flightNid == trNid`); these
  counters are a regression tripwire.
- `cabin_trainee_detection` — "unavailable" when LEON rejected the
  `workSchedule { function }` selection (the current production state): cabin
  trainees are NOT being excluded and the consumer must not assume they are.

Rules behind these fields: `../business-logic/crew-hours-heavy.md`;
settled disputes: `../development/closed-questions.md`.
