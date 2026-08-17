# Open decisions — blockers and unresolved questions

Raised by the app2.py migration audit (2026-08-16). Nothing here has been decided or
silently resolved. Items 1 and 2 are **blockers**: they cannot be answered by anyone
on the software side.

Status values: **BLOCKED — external** · **OPEN — needs owner** · **OPEN — needs code archaeology**

---

## 1. `CHECK_RELATIONS` — A7, A9 and A11 do not include themselves

**Status: BLOCKED — external. Safety-relevant.**

**Exact question:** In `app2.py:121–140`, every check expands to a list that includes
itself, with three exceptions:

```python
"A7":  ["A1"],          # line 125 — no A7
"A9":  ["A1", "A3"],    # line 126 — no A9
"A11": ["A1"],          # line 127 — no A11
```

Compare `"A5": ["A1", "A5"]` (line 124) and `"A10": ["A1", "A2", "A5", "A10"]` (127).

Selecting **A7** therefore generates task cards for **A1 only** — no A7 cards are
produced at all. Same for A9 and A11.

**Is this intentional** (A7/A9/A11 genuinely have no unique tasks of their own and
are administrative aliases for lighter checks), **or is it a data-entry omission?**

**Why it cannot be decided internally:** this encodes an airworthiness maintenance
programme. If it is an omission, the tool has been silently failing to generate
required maintenance cards. Neither reading is inferable from the code — both are
internally consistent. No software engineer can determine which is correct without
the maintenance programme document.

**What it blocks:** CMP/TCM Task Cards (Phase 3 of the migration plan) should not be
ported until answered — porting it faithfully would reproduce the behaviour, and
"fixing" it without authority could inject cards that should not exist.

**Who must answer:** a maintenance engineer / the holder of the MPD or maintenance
programme. Cross-check against the source document, not against the code.

---

## 2. Tesseract OCR hosting

**Status: BLOCKED — external. Hosting + compliance.**

**Exact question:** Will the backend be deployed somewhere a Tesseract binary can be
installed, or must OCR go to a cloud API?

**Why it cannot be decided internally:** the repository contains **no backend
deployment configuration at all** — no Dockerfile, Procfile, fly.toml, render.yaml or
CI workflow. The only deploy artifact is Cloudflare Workers config for the *frontend*
(`.output/server/wrangler.json`). The target is therefore unknown from the repo alone
(**unverified**). The cloud option additionally requires a compliance judgement:
sending aviation maintenance documents to a third-party OCR service.

**Options:**

| Option | Trade-off |
|---|---|
| **A — self-hosted container** | `apt-get install tesseract-ocr`. Free, offline, no per-page cost, no third-party data exposure. ~80 MB image growth. Requires a container platform (Fly / Render / ECS / VM). |
| **B — cloud OCR** (Textract / Document AI / Azure) | Works on serverless. Per-page cost, network latency, and **maintenance documents leave our infrastructure**. |

**What it blocks:** Task Stamping, TCM Indexing, and CMP/TCM Tasks — the three
modules that call `pytesseract` (`app2.py:1827`, `app2.py:703–709` via `:832`).

**What it does NOT block:** Step 1 foundations, and Mail Merge — which touches no PDF
and no OCR. Those can proceed now.

**Who must answer:** whoever owns hosting, plus compliance sign-off if option B.

**Note:** deciding late is expensive. Choosing B after the OCR call sites are written
would force a rewrite in three modules.

---

## 3. Three conflicting task-code regexes

**Status: OPEN — needs owner.**

Four different patterns match "a task code", and they accept different shapes:

| Line | Pattern | Used by |
|---|---|---|
| 97 | `\b\d{2}-\d{2,3}-\d{2}(?:-\d{2})?\b` | `TASK_PATTERN` — TcmIndexer |
| 1936 | `(\d{2,3}-\d{3}-\d{2}-\d{2})` | `_stamp_process_single_pdf` |
| 2863 | `(\d{2}-\d{3}-\d{2})` | `_stamp_cmp_tcm_single_pdf` |
| 911 | `^(\d{2}-\d{2,3})-\d{2}$` | `find_related_subtasks` |

Line 1936 **requires** a 4th segment and allows a 3-digit first segment; line 97 makes
the 4th optional and fixes the first at 2 digits. A code such as `271-054-00-01`
matches 1936 but not 97.

**Question:** which is authoritative? Should all four converge on one pattern, or are
the differences deliberate per context?

**Blocks:** faithful porting of Task Stamping and TCM Indexing.

---

## 4. `2000FC` is defined but unreachable

**Status: OPEN — needs owner.**

`"2000FC": ["2000FC"]` exists in `CHECK_RELATIONS` (line 134) and is accepted by
`check_patterns` (line 3009), but is **absent from the dropdown** built at line 2528:

```python
default_checks = [f"A{i}" for i in range(1,12)] + ["120DY","240DY","12MO","16MO"] + [f"C{i}" for i in range(1,7)]
```

It becomes selectable only if column 24 of the loaded Excel happens to contain it
(the dropdown is later repopulated from the file by `_refresh_available_checks`).

**Question:** should 2000FC be in the default list, or is its omission deliberate?

---

## 5. `placeholder_index` skips index 12 and stops at 17

**Status: OPEN — needs owner.**

In `covering()` (`app2.py:573–592`) the map runs 0–11, **skips 12** (`M`), resumes at
13–17, and stops. Columns `M` and anything beyond `R` are never mapped to a Word
placeholder.

**Question:** is column M intentionally unused, and is R the true last column? If a
column is ever inserted into the source workbook, every index after it silently
shifts — the map is positional, not name-based.

---

## 6. Two different check-extraction rules — one live, one dead

**Status: OPEN — needs code archaeology.**

Two functions extract check codes from column 24, with **different rules**:

| Function | Line | Behaviour | Called? |
|---|---|---|---|
| `_extract_checks_from_excel` | 2962 | **Filters** against `check_patterns` and normalises | **Never called** |
| `_extract_available_checks_from_excel` | 3333 | Returns **all** values unfiltered | Live — used by `_refresh_available_checks` (3288) |

**Question:** which is correct? The dead one validates and normalises; the live one
passes anything through, so malformed or stray cell values reach the dropdown.

---

## 7. `MPD_PATTERN` is defined and never used

**Status: OPEN — needs code archaeology.**

`MPD_PATTERN` (line 98) is identical to `TASK_PATTERN` (line 97) except for the
missing `\b` anchors and the capture group. Grep finds **no usage** anywhere in the
file.

**Question:** dead code to drop, or was it meant to be used somewhere that now uses
`TASK_PATTERN` (or one of the ad-hoc regexes in §3)?

---

## 8. Cover Merge has no implementation

**Status: OPEN — needs owner.**

Cover Merge appears on the web Modules page, but in `app2.py` there is no
`_tab_cover_merge`, no sidebar entry, and no route. The only related code is
`_find_cover_for_task` (3555), which reads `self.covers_dir` — assigned exactly once
as `None` (line 979) and **never set**. It therefore always returns `None`, and the
cover-merge branch at 3525 is unreachable.

**Note:** `worker/handlers.py:409` defines a `cover_merge` handler in the existing web
backend. Its relationship to the desktop code is **unverified** — it may already be a
reimplementation.

**Question:** was Cover Merge dropped, or never finished? Does the existing
`worker/handlers.py` version supersede it?

---

## 9. Task Extractor calls three functions that do not exist

**Status: OPEN — needs owner. Not a migration question — a "what was this meant to do" question.**

`_run_extract` (1615) calls, on its unconditional main path:

| Call site | Function | Definitions in file |
|---|---|---|
| 1650 | `_find_related_tasks` | **0** |
| 1657 | `_extract_related_tasks_to_pdf` | **0** |
| 1724, 1747 | `_is_index_page` | **0** |

Task Extractor raises `AttributeError` on every run; the `except Exception` at 1709
masks it as "Extract failed".

**Question:** what is the definition of a "related task" for extraction purposes?
There is no working implementation to derive it from — the web version must be
specified from requirements.

---

## Summary

| # | Item | Status | Blocks |
|---|---|---|---|
| 1 | A7/A9/A11 self-exclusion | **BLOCKED — external** | CMP/TCM (Phase 3) |
| 2 | Tesseract hosting | **BLOCKED — external** | Stamping, Indexing, CMP/TCM |
| 3 | Conflicting task regexes | OPEN — owner | Stamping, Indexing |
| 4 | 2000FC unreachable | OPEN — owner | CMP/TCM (minor) |
| 5 | placeholder_index gap | OPEN — owner | Mail Merge (minor) |
| 6 | Dead vs live check extraction | OPEN — archaeology | CMP/TCM |
| 7 | MPD_PATTERN unused | OPEN — archaeology | none |
| 8 | Cover Merge undefined | OPEN — owner | Cover Merge |
| 9 | Task Extractor undefined functions | OPEN — owner | Task Extractor |

**Nothing here blocks Step 1 (foundations) or Mail Merge.**
