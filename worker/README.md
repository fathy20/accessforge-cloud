# REDSEA Worker

External Python worker. It connects to the web app via the public HMAC
endpoints (`/api/public/hooks/worker-poll` and `/worker-callback`) and runs
the **exact** processing logic from the original desktop toolkit.

## What's in here

| File | Role |
|---|---|
| `redsea_toolkit.py` | **The original desktop file — preserved verbatim** (per request "متغيرش في كود فيها"). |
| `tk_stub.py`        | Stubs `tkinter` / `customtkinter` so the toolkit imports headless. |
| `toolkit.py`        | Re-exports the toolkit's pure helpers (`covering`, `TcmIndexer`, `TASK_PATTERN`, `CHECK_RELATIONS`, `build_check_regexes`, `ocr_page_text`, …). |
| `handlers.py`       | One handler per `module_key`, each calling the toolkit primitives. |
| `storage.py`        | Supabase Storage download/upload wrapper. |
| `main.py`           | Poll → run → callback loop. |
| `requirements.txt`  | Python deps. |

## Module → handler map

All 8 modules from the desktop app are wired and use the toolkit primitives:

| `module_key`     | Toolkit primitive used                  | Desktop reference |
|------------------|-----------------------------------------|-------------------|
| `task_extractor` | `TASK_PATTERN` + `ocr_page_text`        | `_run_extract` L1615 |
| `task_stamping`  | PyMuPDF overlay (same layout)           | `_stamp_page_data` L1833 |
| `effectivity`    | pandas Excel/CSV normaliser             | `_load_excel_generic` L2148 |
| `check_control`  | `CHECK_RELATIONS` + `expand_check`      | `_load_check_csv` L2272 |
| `utilization`    | sha256/md5/blake2 per row               | `hash_function_*` L2453 |
| `cmp_tcm`        | `TcmIndexer` (verbatim class)           | L768 |
| `cover_merge`    | PyMuPDF `insert_pdf`                    | `_find_cover_for_task` L3555 |
| `mail_merge`     | python-docx `{{TAG}}` / `«TAG»` replace | `_mm_replace_merge_fields` L4659 |

## Local run

```bash
cd worker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Tesseract OCR system binary required for task_extractor scanned-PDF fallback

export REDSEA_BASE_URL="https://project--0d19a868-5f9d-4bb7-931b-bb0c1f72c7c5.lovable.app"
export WORKER_HMAC_SECRET="…"               # same value as in Lovable Cloud
export SUPABASE_URL="…"
export SUPABASE_SERVICE_ROLE_KEY="…"
export WORKER_ID="worker-1"

python -m worker.main
```

## Deploy

Any container host (Railway / Fly / Render / your own VM). One process per
worker; scale horizontally by running more processes — `worker-poll` claims
jobs atomically so two workers never pick the same job.

Required env vars: `REDSEA_BASE_URL`, `WORKER_HMAC_SECRET`, `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY`. Optional: `WORKER_ID`, `POLL_IDLE_SECONDS`,
`UPLOADS_BUCKET` (default `uploads`), `OUTPUTS_BUCKET` (default `outputs`).

## Extending

Per-module input options (e.g. tail/station/date for stamping, target check
for check_control) come through `job.input_refs` — the web `ModuleRunner`
already supports `extraInput`. To add a field, set `extraInput={ tail: "…" }`
on the module page and read `job["input_refs"]["tail"]` in the handler.
