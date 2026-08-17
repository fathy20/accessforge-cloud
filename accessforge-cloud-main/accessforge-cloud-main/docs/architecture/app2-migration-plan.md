# app2.py → web migration plan

Depends on `app2-module-inventory.md` (what exists) and `backend-audit.md` (what it
lands on). Every item cites a real file/function.

**No code has been written.** This is the plan for approval.

---

## 4a. Per-module requirements

Pattern for all of them: follow `backend/copilot/` — `router.py` → `service.py` →
pure logic module, DI via `Depends`, Pydantic validation. **Do not add routes to
`main.py`**, which already carries 16 inline routes (see audit 3a).

### Task Extractor — REBUILD, no reference implementation

Desktop version is broken (`_run_extract` → three undefined methods, inventory §0.1).

- `POST /api/modules/task-extractor/jobs` → `{source_upload_ids[], task_code, combine}` → `202 {job_id}`
- `GET /api/modules/task-extractor/jobs/{id}` → status, progress, artifacts
- **Async job — mandatory.** Reuses `_scan_pages_for_code_parallel` (1713) logic.
- Storage: input PDFs + output artifacts in object storage.
- **UI must expose** what the desktop had but hid: `skip_first` and `combine` are
  real parameters whose checkboxes are commented out (1541–1542), so both are stuck
  at defaults. Surface them.
- **Blocked on:** the owner defining "related tasks" — the desktop implementation
  does not exist, so the rule is unknown. **Requires external confirmation.**

### Task Stamping — PORT, with one behaviour change

- `POST /api/modules/task-stamping/jobs` → `{upload_ids[], station?, date?}`
- **Async job — mandatory** (OCR fallback at 1822 is a blocking subprocess per page).
- Port near-verbatim: `_stamp_page_data` (1833), `_stamp_document` (2593), including
  the Boeing-card regex (§2.9) and both fallback coordinate tables (§2.11).
- **Behaviour change required:** the desktop overwrites source PDFs in place
  (`os.replace`, 1970/2017). On the web, inputs are immutable; emit new artifacts.
  Confirm this is acceptable to the users — it changes their workflow.
- Package Relations (1764–1820) becomes metadata on the job, not folders on disk.

### CMP / TCM Tasks — PORT, highest value

- `POST /api/modules/cmp-tcm/index-jobs` → build the TCM index
- `GET  /api/modules/cmp-tcm/checks?upload_id=` → column-24 values
- `POST /api/modules/cmp-tcm/generate-jobs` → `{excel_upload_id, check, aircraft}`
- **Async job — mandatory** (indexing OCRs every page of every PDF).
- Port verbatim: `CHECK_RELATIONS` (§2.2), `expand_check` (449),
  `_extract_tasks_from_excel_mpd_rsd` (3124), `_normalize_check_code` (3041),
  `_expand_tasks_with_subtasks` (3082), `TcmIndexer.scan_single_pdf` (815) and
  `find_best_occurrence_for_task` (888).
- **Index must move to the DB.** The pickle cache (765–813) is remote code execution
  — `pickle.load` on a file inside a user-supplied folder. Table:
  `tcm_index(tenant, pdf_key, task_code, start_page, end_page)`.
- **UI must expose** the sheet-name field (commented out, 2515) and the cancel
  control that `stop_requested` (783) already supports but no button ever sets.
- Resolve which check-extraction rule is authoritative — filtered (2962, dead) vs
  unfiltered (3333, live). **Question 5.**

### Mail Merge (Covering) — PORT, mostly clean

- `POST /api/modules/mail-merge/preview` → `{template_id, data_id, key}` (sync, fast)
- `POST /api/modules/mail-merge/generate` → single doc (sync)
- `POST /api/modules/mail-merge/batch-jobs` → all rows (**async**)
- Port verbatim: `placeholder_index` (§2.3) with its legacy aliases,
  `_mm_load_excel_ignoring_names` (3851), `_mm_manual_replace` (4064),
  `_mm_detect_merge_fields` (4212), the LTR wrapping at 4148.
- **Batch already exists and is unreachable** (`_mm_batch_generate_all` 4515, button
  commented out 3783–3792). Ship it — it is finished work sitting behind a comment.
- `covering()` (556) contributes `placeholder_index` only; its `input()` (603) and
  CSV-by-position reading are replaced by request parameters.

### Effectivity · Check Control · Utilization — GREENFIELD

All three are stubs (inventory §0.3). **No logic to migrate.** They need requirements
before design. Recommend deferring; do not let their presence on the Modules page
imply readiness.

### Cover Merge — UNDEFINED

No desktop implementation (inventory §0.2). **Requires external confirmation** before
any work.

### TCM Indexing — subsumed by CMP/TCM

Same `TcmIndexer`. Ship as one backend capability, optionally two UI surfaces.

---

## 4b. Dependency graph — from real coupling

Traced through the code, not assumed:

```
        MPD RSD Excel ──────────────┐
                                    ▼
  TCM PDFs ──► TcmIndexer ──► CMP/TCM Generate ──► task-card PDFs
   (815)        (768)          (3425)
                   │
                   └──► _expand_tasks_with_subtasks (3082)  [needs the index]

  RC Excel + RC.docx ──► Mail Merge (4099) ──► RC card .docx
                          [independent]

  Any PDFs ──► Task Stamping (1912) ──► stamped PDFs
                          [independent]

  Cover PDFs ──► _find_cover_for_task (3555) ──► CMP/TCM cover merge
                          [DEAD — covers_dir never set]
```

**Real couplings — only two:**

1. **CMP/TCM Generate → TcmIndexer.** Hard. `_generate_task_cards_indexed` calls
   `find_best_occurrence_for_task` (3508) and `_expand_tasks_with_subtasks` needs the
   index to validate `-01`..`-10` (3111). Indexing must ship first.
2. **CMP/TCM → Cover Merge.** Intended (3517–3532) but dead.

**Non-couplings, contrary to the brief's hypotheses:**

- **Cover Merge does not consume TCM Indexing output.** It matches cover PDFs by
  filename in `covers_dir` (3559–3564). No index involvement.
- **Mail Merge does not depend on Effectivity.** It reads its own Excel and matches
  on the `MPD` column (4129). No shared state, no shared file.

**Build order follows from this:** storage + jobs → TcmIndexer → CMP/TCM Generate.
Task Stamping and Mail Merge can proceed in parallel at any time.

---

## 4c. Server-side blocker: Tesseract

**Three modules call `pytesseract`:** Task Stamping (1822, 1925, 1935), TCM Indexing
(703–709 via 832), and CMP/TCM indirectly through the indexer.

The desktop assumes a local install: `TESSERACT_CMD = None` (91) relying on PATH.

**This is a hard blocker and cannot be resolved from the repo.** There is no
Dockerfile, no platform config, and no deployment target committed (audit 3c). Two
paths:

- **A — bundle the binary.** `apt-get install tesseract-ocr` in the image. Works on
  container platforms (Fly, Render, ECS, plain VM). Adds ~80 MB. Free, offline,
  fastest.
- **B — cloud OCR** (AWS Textract / Google Document AI / Azure). Required if the
  target is a serverless platform that cannot install binaries. Costs per page, adds
  a network hop, and **sends maintenance documents to a third party** — likely needs
  compliance sign-off in an aviation context.

**Decide before implementation starts.** Choosing B late would force a rewrite of the
OCR call sites in all three modules.

**Requires external confirmation:** the deployment target, and whether sending
maintenance PDFs to a third-party OCR service is permitted.

---

## 4d. Prioritised roadmap

Ordered by business value × inverse risk. Every item references real code.

### Phase 0 — Foundations (blocks everything)

| # | Item | Why first | Refs |
|---|---|---|---|
| 0.1 | **Decide the deployment target and the Tesseract path** | Blocks 3 modules; changes the design, not just config | §4c |
| 0.2 | **Durable job queue** | 0 queue libraries exist (audit 3c). Every heavy module needs it. `BackgroundTasks` dies with the process. | audit B8 |
| 0.3 | **Object storage + upload/download** | `storage.py` already has the governance layer (`sanitize_original_name` :202, `storage_basename` :149, `ArtifactType`); swap the filesystem behind it | audit 3c |
| 0.4 | **Print the resolved `.env` path at startup** | One line; the log already exists at `config.py:34` but fires before uvicorn configures logging | audit B4 |

### Phase 1 — Mail Merge (highest value ÷ lowest risk)

Fully working, no OCR, no index, no Tesseract dependency, and **batch generation is
already written** (4515) behind a commented-out button. Proves the job queue on a
low-risk module. Depends only on 0.2/0.3.

### Phase 2 — TCM Indexing

Prerequisite for CMP/TCM. Port `TcmIndexer` (768) with the pickle cache **replaced by
a DB table** — that cache is the single worst security defect found (arbitrary code
execution). Needs Tesseract (0.1).

### Phase 3 — CMP / TCM Task Cards

The core module and the largest single block of business logic (§2.2, §2.6–2.8).
Depends on Phase 2. Resolve questions 1, 2, 3 and 5 (inventory §3) **before** coding
— particularly the `A7`/`A9`/`A11` self-inclusion asymmetry, which silently omits
maintenance cards.

### Phase 4 — Task Stamping

Working logic, but needs Tesseract and a confirmed behaviour change (no in-place
overwrite). Medium risk because it edits compliance documents.

### Phase 5 — Task Extractor

Deliberately last despite being first on the Modules page: **its core is missing**
(§0.1). Requires a written specification of "related tasks" first.

### Deferred — Effectivity · Check Control · Utilization · Cover Merge

No logic exists. Do not schedule until requirements exist.

---

## Rules compliance

- **No code written.** Audit and plan only.
- **No business-rule constant modified, reformatted or "improved."** Six discrepancies
  are flagged as questions in inventory §3, unresolved.
- **Not touched:** `statistics/crew_hours/service.py`, `statistics/crew_hours/heavy.py`,
  `statistics/crew_hours/token_provider.py`, and all Wingman code — not modified and
  not audited.
- **No secret value printed.** B1/B2 reference `file:line` only.
- **Unverifiable items** listed under "Requires external confirmation" in both this
  document and the audit.
