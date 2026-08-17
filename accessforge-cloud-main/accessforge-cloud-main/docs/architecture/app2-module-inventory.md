# app2.py — module inventory and line classification

Source: `E:/work/REDSEA/web/last_V01/app2.py` — **4,944 lines**, 226,445 bytes.
Read in full, in five sequential chunks (1–1000, 1000–2000, 2000–3000, 3000–4000,
4000–4944). Every claim below cites a line number.

---

## 0. Headline findings, before the inventory

Three findings change the migration plan and should be read first.

### 0.1 Task Extractor is broken at runtime — CRITICAL

`_run_extract` (line 1615) calls three methods that **are never defined anywhere in
the file**:

| Called at | Method | Definition |
|---|---|---|
| 1650 | `self._find_related_tasks(code, pdf_path=pdf_path)` | **none** |
| 1657 | `self._extract_related_tasks_to_pdf(...)` | **none** |
| 1724, 1747 | `self._is_index_page(text)` | **none** |

Verified by grep across the whole file: the only occurrences are the call sites.
Line 1650 executes on the primary path, so **Task Extractor raises `AttributeError`
on every run**. The `except Exception` at 1709 converts it into a "Extract failed"
dialog, which is why it presents as a vague failure rather than a crash.

**Consequence:** there is no working reference implementation to port. The web
version must be specified from requirements, not transcribed.

### 0.2 Cover Merge does not exist as a module

There is no `_tab_cover_merge`, no sidebar entry, and no navigation route. The only
cover code is `_find_cover_for_task` (3555). It reads `self.covers_dir`, which is
assigned exactly once — `self.covers_dir = None` (979) — and **never set anywhere
else**. So `_find_cover_for_task` always returns `None` at line 3557, and the cover
merge branch at 3525 is unreachable.

Cover Merge appears on the web Modules page but has **no desktop implementation to
migrate**. Status: unverified whether this is intended future work or a dropped
feature. Requires confirmation.

### 0.3 Four of the ten listed modules are stubs

`_tab_effectivity` (2122), `_tab_check_control` (2247), `_tab_utilization` (2303),
and their loaders (`_load_excel_generic` 2148, `_load_check_csv` 2272,
`_load_util_csv` 2328, `_save_util_csv` 2359, `_util_add` 2409,
`_util_delete_selected` 2430, `_export_effectivity` 2223, `_pick_chapters_folder`
2175, `_log_effectivity` 2198) all display an "UNDER DEVELOPMENT" messagebox and
return. The original bodies are commented out or deleted.

`_load_util_csv` contains `return` at 2351 followed by dead code at 2353–2358.
`_load_check_csv` shows the dialog then **still runs** its thread (2295–2300),
referencing `self.tree_check` which is never created — a second latent
`AttributeError`.

**Consequence:** Effectivity, Check Control and Utilization have **no business logic
to preserve**. They are greenfield.

---

## 1. Module inventory

### 1.1 Task Extractor — BROKEN (see 0.1)

- **UI:** `_tab_task_extractor` (1525)
- **Actions:** "📁 Source Folder…" → `_pick_pdf_folder` (1567) · "📂 Output Folder…" →
  `_pick_output_folder` (1602) · "🚀 Run Extract" → `_run_extract` (1615) ·
  "📋 Copy Log" → `_copy_task_log` (1557)
- **Chain:** folder of PDFs → filename prefix match on first two digits of the task
  code (1627, 1633) → `_find_related_tasks` **[undefined]** → fallback
  `_scan_pages_for_code_parallel` (1713) → `group_contiguous` → `fitz.insert_pdf` →
  `{code}_extracted.pdf` or `{code}_p{n}_{i}.pdf`
- **Deps:** PyMuPDF
- **Threading:** `ThreadPoolExecutor(max_workers=TASK_EXTRACTOR_THREADS)` (1673),
  constant = 3 (117)
- **Shared state:** `self.selected_pdf_folder`, `self.output_dir`,
  `self.skip_first_var`, `self.combine_var`

Note: the two checkboxes that drive `skip_first_var` and `combine_var` are commented
out (1541–1542), so both keep their constructor defaults — `False` and `True` (1540).

### 1.2 Task Stamping — WORKING

- **UI:** `_tab_task_stamping` (2045)
- **Actions:** "Select Input Folder..." → `_stamp_browse_input_folder` (2089) ·
  "Select Output Folder..." → `_stamp_browse_output_folder` (2094) ·
  "Start Processing" → `_stamp_start_process` (2099) · "Create A10 Package
  Structure" → `_create_package_structure("A10")` (2058)
- **Chain:** `_stamp_process_folder` (1977) → `walk_pdfs_in_dir` → per file
  `_stamp_process_single_pdf` (1912) → detect tail code in first 5 pages (1923–1931)
  → find tasks by regex (1936) → split one PDF per task → `_stamp_page_data` (1833)
  → **overwrite the input file in place** via `os.replace` (1970, 2017)
- **Deps:** PyMuPDF, pytesseract, Pillow
- **OCR:** `_stamp_extract_text_with_ocr` (1822) — synchronous, per page
- **Destructive:** writes over the user's source PDFs. Also writes a probe file
  `test_write_permission` into the input folder (1984–1988).

### 1.3 CMP / TCM Tasks (Indexed) — WORKING, the core module

- **UI:** `_tab_cmp_tcm_tasks` (2511)
- **Actions:** "📊 MPD RSD Excel…" → `_pick_mpd_rsd_excel` (2916) · "📁 TCM Folder…" →
  `_pick_tcm_dir` (2925) · "📂 Output Folder…" → `_pick_output_folder_cmp_tcm` (2938)
  · "🔧 Rebuild TCM Index" → `_rebuild_tcm_index` (2945) · "🔄 Refresh" →
  `_refresh_available_checks` (3288) · "🚀 Generate Task Cards" →
  `_generate_task_cards_indexed` (3425) · "📋 Copy Log" → `_copy_log` (2560)
- **Chain:** Excel MPD RSD → `_extract_tasks_from_excel_mpd_rsd` (3124) locates the
  `CMPISS03 R1` marker row, matches the check in **column 24**, reads task codes from
  **column 0** → `_expand_tasks_with_subtasks` (3082) probes `-01`..`-10` against the
  index → `expand_check` (449) fans the check out to related checks →
  `TcmIndexer.find_best_occurrence_for_task` (888) → optional cover merge
  **[dead, see 0.2]** → one PDF per task under `{out}/{check}/`
- **Deps:** PyMuPDF, pandas, openpyxl/pyxlsb, pytesseract (via indexer OCR)
- **Also present:** `_extract_all_tasks` (2570) is a stub that logs "not implemented"
  (2586); its button is commented out (2551). `_extract_checks_from_excel` (2962) is
  defined but **never called** — `_refresh_available_checks` uses
  `_extract_available_checks_from_excel` (3333) instead. The two apply *different*
  rules: 2962 filters against `check_patterns`, 3333 returns column 24 unfiltered.

### 1.4 TCM Indexing — WORKING (class `TcmIndexer`, 768)

- `scan_single_pdf` (815) — text layer, OCR fallback per page (832), `TASK_PATTERN`
  findall, contiguous page runs
- `build_index` (847) — `ThreadPoolExecutor`, default 4 threads (774), 8 when
  constructed at 3460
- `find_best_occurrence_for_task` (888) — longest contiguous run wins
- `find_related_subtasks` (904) — prefix match on first two numeric segments
- **Cache:** `.tcm_index.pkl` preferred, `.tcm_index.json` fallback (765–766,
  785–813), written **into the scanned TCM folder**
- **Cancellation:** cooperative via `self.stop_requested` (783) — no UI ever sets it

### 1.5 Mail Merge (Covering) — WORKING

- **UI:** `_tab_mail_merge` (3571)
- **Actions:** "📄 Word Template…" → `_mm_select_word_template` (3892) · "📊 Excel
  Data…" → `_mm_select_excel_file` (3912) · "🔗 Configure Field Mapping" →
  `_mm_show_field_mapping` (4248) · "🔍 Preview Data" → `_mm_preview_data` (4019) ·
  "🚀 Generate Document" → `_mm_generate_document` (4099)
- **Chain:** `.docx` template + `.xlsx`/`.csv` → match on the `MPD` column (4129) →
  build context with LTR wrapping (4146–4148) → `MailMerge.merge` → write temp →
  reopen with python-docx → `_mm_manual_replace` (4064) → save
- **Deps:** docx-mailmerge, python-docx, pandas, openpyxl
- **Excel repair path:** `_mm_load_excel_ignoring_names` (3851) rewrites the xlsx zip
  to strip `definedNames` from `xl/workbook.xml` — a real workaround for corrupt
  files, worth preserving
- **Dead code:** `_mm_batch_generate_all` (4515) and `_mm_batch_process` (4720) are
  fully implemented but **unreachable** — the button is commented out (3783–3792).
  `_mm_replace_merge_fields` (4659) is defined and never called.

### 1.6 Standalone `covering()` (556) — CLI, not wired to any button

Reads a **CSV** by positional index, prompts on **stdin** (603), renders via
`docxtpl` (570). Not referenced by the GUI. Its `placeholder_index` is the
authoritative Excel-column → Word-placeholder map and must survive.

### 1.7 Undocumented modules (not on the web Modules page)

| Module | Lines | Status |
|---|---|---|
| `MiniLauncherManager` | 144–447 | Working desktop launcher — discard |
| Package Relations (A10 folder tree) | 1764–1820 | Working; creates folders on disk |
| `hash_function_md5` / `_sha256` / `_blake2` | 2453, 2472, 2491 | Stubs, dialogs only |
| `parse_arguments` CLI (`--full`, `--mini`, `--module`) | 4876 | Working |

---

## 2. Encoded business knowledge — VERBATIM

Copied exactly. Not reformatted, not corrected.

### 2.1 Task regexes (97–98)

```python
TASK_PATTERN = re.compile(r"\b\d{2}-\d{2,3}-\d{2}(?:-\d{2})?\b")
MPD_PATTERN = re.compile(r"(\d{2}-\d{2,3}-\d{2}(?:-\d{2})?)")
```

### 2.2 `CHECK_RELATIONS` (121–140)

```python
CHECK_RELATIONS = {
    # A-Check relationships (Letter checks)
    "A1": ["A1"], "A2": ["A1", "A2"], "A3": ["A1", "A3"], 
    "A4": ["A1", "A2", "A4"], "A5": ["A1", "A5"], 
    "A6": ["A1", "A2", "A3", "A6"], "A7": ["A1"], 
    "A8": ["A1", "A2", "A4", "A8"], "A9": ["A1", "A3"], 
    "A10": ["A1", "A2", "A5", "A10"], "A11": ["A1"],
    
    # Calendar-based checks (time intervals)
    "120DY": ["120DY"],  # 120 day check
    "240DY": ["120DY", "240DY"],  # 240 day check (includes 120 day)
    "12MO": ["120DY", "12MO"],  # 12 month check
    "16MO": ["120DY", "240DY", "12MO", "16MO"],  # 16 month check (major)
    "2000FC": ["2000FC"],  # 2000 flight cycle check
    
    # C-Check relationships (heavy maintenance)
    "C1": ["C1"], "C2": ["C1", "C2"], "C3": ["C1", "C3"], 
    "C4": ["C1", "C2", "C4"], "C5": ["C1", "C5"], 
    "C6": ["C1", "C2", "C3", "C6"]
}
```

### 2.3 `placeholder_index` (573–592) — Excel column → Word placeholder

```python
    placeholder_index = {
        # Index : (Excel Col, Word Placeholder)
        0:  ('A/SEQ', 'SEQ'),           # Routine TASK Card & RELATED TASK
        1:  ('B/MPD', 'MPD'),           # RC. #
        2:  ('C/DATE', 'DATE'),         # RC. DATE:
        3:  ('D/TITLE', 'TITLE'),       # TITLE
        4:  ('E/MHR', 'MHR'),           # EST MHRS
        5:  ('F/WO', 'WO'),            # W/O
        6:  ('G/AC', 'AC_REG'),        # A/C REG.
        7:  ('H/ACSN', 'AC_MSN'),      # A/C MSN:
        8:  ('I/ZONE', 'ZONE'),        # AREA/ZONE:
        9:  ('J/ACCESS', 'ACCESS'),     # ACCESS PANELS:
        10: ('K/CYC', 'CYCLE'),        # NO cycle
        11: ('L/FHS', 'HOURS'),        # TOTAL HOURS:
        13: ('N/SOURC', 'SOURCE'),     # SOURCE
        14: ('O/CRIT', 'CRITICAL'),    # CRITICAL TASK
        15: ('P/RII', 'RII'),          # RII TASK
        16: ('Q/OTHER', 'OTHER'),      # OTHER
        17: ('R/CMP', 'CMP')           # CMP APPROVAL#
    }
```

Legacy alias fan-out (661–672): `MPD→RC_NUM`, `DATE→RC_DATE`, `MHR→EST_MHRS`,
`AC_REG→{AC_REG, AC}`, `AC_MSN→{AC_MSN, ACSN}`.

### 2.4 `TAIL_MAP` (1756–1761)

```python
    TAIL_MAP = {
        "BTR": "SU-RSA",
        "ILF": "SU-RSB",
        "GUN": "SU-RSC",
        "GOT": "SU-RSD"
    }
```

### 2.5 `PACKAGE_RELATIONS` (1764–1766)

```python
    PACKAGE_RELATIONS = {
        "A10": ["A2", "A4", "A8", "A10"]
    }
```

### 2.6 Check-code validation patterns (3004–3010)

```python
            check_patterns = [
                r'^A([1-9]|1[0-1])$',  # A1-A11
                r'^C[1-6]$',           # C1-C6
                r'^(120|240)\s*DY$',   # 120DY, 240DY
                r'^(12|16)\s*MO$',     # 12MO, 16MO
                r'^2000\s*FC$'         # 2000FC
            ]
```

### 2.7 Check-code normalisation (3061–3074)

```python
        transformations = [
            # Days: 120 DY, 120 DAYS -> 120DY
            (r'(\d+)\s*(DY|DAYS?)', r'\1DY'),
            # Months: 12 MO, 12 MONTHS -> 12MO  
            (r'(\d+)\s*(MO|MONTHS?)', r'\1MO'),
            # Flight Cycles: 2000 FC, 2000 CYCLES -> 2000FC
            (r'(\d+)\s*(FC|CYCLES?)', r'\1FC'),
            # Hours: 1000 HR, 1000 HOURS -> 1000HR
            (r'(\d+)\s*(HR|HOURS?)', r'\1HR'),
            # General: A 1, C 2 -> A1, C2
            (r'([A-Z])\s+(\d+)', r'\1\2'),
            # إزالة المسافات الزائدة
            (r'\s+', ''),
        ]
```

### 2.8 Excel layout constants (CMP/TCM)

- Section marker regex (3220): `r'\bCMPISS03\s+R1\b'`, IGNORECASE
- Check column: `check_column = 24` (3242, and 2969 as default)
- Task column: `mpd_item_col = 0` (3270)
- Sheet preference: any sheet whose upper-case name contains `'MPD RSD'` (3191, 3376)
- Column-24 guard: `if df.shape[1] <= 24` (3398)

### 2.9 Boeing card-number extraction (1884, 2653)

```python
boeing_match = re.search(r"BOEING\s+CARD\s+NO\.?\s*([\d-]+)", page_text, re.IGNORECASE)
```
Search labels (1849, 2614): `["BOEING CARD NO.", "BOEING CARD NO"]`.
Airline card number is built as `RC{p0}-{p1}-{p2}` when ≥3 parts, else `RC{p0}-{p1}`
when ≥2, else the literal `"RC"` (1870–1873, 1890–1892).

### 2.10 Three *different* task regexes — FLAGGED, NOT CHANGED

| Line | Regex | Used by |
|---|---|---|
| 97 | `\b\d{2}-\d{2,3}-\d{2}(?:-\d{2})?\b` | `TASK_PATTERN`, TcmIndexer |
| 1936 | `(\d{2,3}-\d{3}-\d{2}-\d{2})` | `_stamp_process_single_pdf` |
| 2863 | `(\d{2}-\d{3}-\d{2})` | `_stamp_cmp_tcm_single_pdf` |
| 911 | `^(\d{2}-\d{2,3})-\d{2}$` | `find_related_subtasks` |

These accept different code shapes. 1936 requires a 4th segment and allows a 3-digit
first segment; 97 makes the 4th optional and fixes the first at 2 digits. **Question
for the owner — do not resolve unilaterally.**

### 2.11 Fallback stamp coordinates (2755–2760, 2772–2777)

```python
                                standard_positions = [
                                    (160, 220, 400, 260, tail_number),      # TAIL NUMBER position
                                    (160, 160, 400, 200, airline_card_no),  # CARD NO position
                                    (160, 280, 400, 320, station_value),    # STATION position
                                    (160, 100, 400, 140, date_value)        # DATE position
                                ]
```
```python
                        fallback_positions = [
                            (50, 130, 400, 170, "TAIL", tail_number),
                            (50, 150, 400, 190, "CARD", airline_card_no),
                            (50, 170, 400, 210, "STA", station_value),
                            (50, 190, 400, 230, "DATE", date_value)
                        ]
```

### 2.12 Other constants

- `TASK_EXTRACTOR_THREADS = 3` (117)
- Index filenames (765–766): `.tcm_index.json`, `.tcm_index.pkl`
- Default check list (2528): `[f"A{i}" for i in range(1,12)] + ["120DY","240DY","12MO","16MO"] + [f"C{i}" for i in range(1,7)]` — **omits `2000FC`**, which `CHECK_RELATIONS` defines
- Aircraft list (2535): `["SU-RSA","SU-RSB","SU-RSC","SU-RSD"]`
- Subtask probe range (3109): `range(1, 11)` → `-01`..`-10`
- LTR wrapping (4148, 4587): `f"\u202A{val_str}\u202C"` applied when `re.search(r'\d+-\d+', val_str)`
- Merge-field patterns (4219–4224): `«F»`, `<<F>>`, `{{F}}`, `{merge F}`
- `build_check_regexes` (712–762) — full variant table for `DY`/`MO` forms

---

## 3. Questions for the owner — flagged, not corrected

Per the rules, none of these were changed.

1. **`CHECK_RELATIONS` self-inclusion asymmetry (123–127).** Every entry lists itself
   *except* three: `"A7": ["A1"]`, `"A9": ["A1", "A3"]`, `"A11": ["A1"]`. Running A7
   therefore generates cards for A1 only — no A7 cards. Compare `"A5": ["A1", "A5"]`.
   Intentional (A7/A9/A11 have no unique tasks) or a typo? A single missing entry here
   silently omits maintenance cards.
2. **`2000FC` unreachable (2528).** Defined in `CHECK_RELATIONS` and accepted by
   `check_patterns`, but absent from the default dropdown. Reachable only if column 24
   happens to contain it.
3. **Three task regexes (§2.10).** Which is authoritative?
4. **`placeholder_index` skips index 12** (`M`) and stops at 17 (`R`). Deliberate gap?
5. **Two different check-extraction rules** — filtered (2962) vs unfiltered (3333).
   The filtered one is dead code. Which is correct?
6. **Cover Merge** — dropped, or unbuilt? (§0.2)

---

## 4. Line classification

Bucketed to cover all 4,944 lines. Percentages are of total.

### A — PORTABLE BUSINESS LOGIC (~735 lines, 15%)

| Lines | Item |
|---|---|
| 95–98 | `TASK_PATTERN`, `MPD_PATTERN` |
| 119–140 | `CHECK_RELATIONS` |
| 449–460 | `expand_check` |
| 512–553 | `safe_make_dir`, `is_pdf`, `walk_pdfs_in_dir`, `unique_path`, `group_contiguous` |
| 556–693 | `covering()` — logic only; the `input()` at 603 is bucket C |
| 695–709 | `page_to_image`, `ocr_page_text` |
| 711–762 | `build_check_regexes` |
| 815–845 | `TcmIndexer.scan_single_pdf` |
| 888–922 | `find_best_occurrence_for_task`, `find_related_subtasks` |
| 1756–1766 | `TAIL_MAP`, `PACKAGE_RELATIONS` |
| 1833–1911 | `_stamp_page_data` — extraction and stamping rules |
| 2593–2792 | `_stamp_document` — label search, fallbacks, coordinates |
| 2962–3122 | `_extract_checks_from_excel`, `_normalize_check_code`, `_expand_tasks_with_subtasks` |
| 3124–3286 | `_extract_tasks_from_excel_mpd_rsd` |
| 3333–3423 | `_extract_available_checks_from_excel` |
| 3851–3890 | `_mm_load_excel_ignoring_names` |
| 4064–4097 | `_mm_manual_replace` |
| 4212–4246 | `_mm_detect_merge_fields` |
| 4659–4718 | `_mm_replace_merge_fields` |

### B — DESKTOP-ONLY, DISCARD (~2,750 lines, 56%)

| Lines | Item |
|---|---|
| 71–74 | tkinter / customtkinter imports |
| 79–86 | window geometry, asset paths |
| 100–111 | colour scheme |
| 142–447 | `MiniLauncherManager` — windows, hover, alpha animation, colour maps |
| 462–510 | `load_background_image`, `load_logo_image` |
| 925–1235 | `RedseaApp.__init__`, asset loading, mini/full mode, zoom, fullscreen, centring |
| 1237–1245 | `_safe_log`, `_safe_show_error`, `_safe_show_info` |
| 1247–1429 | sidebar, nav buttons, tooltips, About, exit |
| 1431–1522 | main shell, canvas background, `show_tab` |
| 1525–1613 | Task Extractor widgets and file dialogs |
| 2045–2117 | Task Stamping widgets |
| 2122–2450 | Stub tabs and stub loaders (Effectivity, Check Control, Utilization) |
| 2453–2508 | Hash-function stubs |
| 2511–2568 | CMP/TCM widgets |
| 3571–3849 | Mail Merge widgets |
| 4248–4513 | Field-mapping dialog (its *mapping rules* are bucket A) |
| 4845–4872 | `df_to_tree` |
| 4876–4944 | argparse and `mainloop` |

### C — ARCHITECTURALLY BROKEN FOR WEB (~1,460 lines, 29%)

Each entry states why it fails under multi-user web conditions and its replacement.

| Lines | Item | Why it breaks | Replacement |
|---|---|---|---|
| 113–117 | `MINI_LAUNCHER_MODE`, `TARGET_MODULE`, `APP_INSTANCE` | Module-level mutable globals. One worker serves many users; concurrent requests overwrite each other's target module. Classic cross-user leak. | Per-request state; routing in the SPA |
| 765–813 | `.tcm_index.pkl` / `.json` cache | **`pickle.load` on a file inside a user-supplied folder is arbitrary code execution.** Also local-disk state invisible to other instances. | DB table `tcm_index(user/tenant, pdf, task, start, end)`; never pickle |
| 774, 847–886 | `ThreadPoolExecutor` indexing | Blocks the worker for minutes; no cancellation across processes; `stop_requested` is per-object | Durable job queue, worker pool, job row with cancel flag |
| 815–845 | Per-page OCR in the scan loop | `pytesseract` is a blocking subprocess per page; freezes the request thread | Same job queue; OCR as a job step |
| 1615–1711 | `_run_extract` `threading.Thread` | Fire-and-forget thread, no persistence, lost on restart; writes to `self.*` | Background job with a persisted record |
| 1567–1613, 2089–2097, 2916–2943, 3892–3930, 4166, 4534, 4740 | `filedialog.*` | Server has no user filesystem or dialogs | Upload endpoints + object storage keys |
| 603 | `input()` in `covering()` | Blocks the process forever on a server | Request parameter |
| 1912–1975, 1977–2043 | In-place overwrite via `os.replace` | Mutates the user's source; on a server there is no "user's folder", and concurrent jobs race on the same path | Write new artifacts to object storage, never mutate inputs |
| 1984–1988 | `test_write_permission` probe file | Writes into an input directory; meaningless on object storage | Drop |
| 1811, 1785–1793 | `os.makedirs` next to `__file__` | Containers have read-only/ephemeral app dirs; not shared between instances | Storage prefixes |
| 2570–2590, 4515–4657, 4720–4841 | Unreachable/dead implementations | Dead code migrates as dead weight | Do not port; re-specify batch as a job |
| 3425–3553 | `_generate_task_cards_indexed` | Reads `self.indexer`, `self.tcm_dir`, `self.out_cmp_tcm`, `self.mpd_rsd_excel` — instance state doubling as session state | Job payload carrying explicit storage keys |
| 3555–3569 | `_find_cover_for_task` | Depends on `covers_dir`, never set (§0.2) | Re-specify |
| 1237–1245 + every `_safe_log` call | Progress by writing into a Tk widget | No widget on a server | Job progress rows + SSE/polling |
| 91–93 | `TESSERACT_CMD` local binary | Requires a Tesseract binary in the image (§4c of the plan) | Confirm base image, else cloud OCR |

**Coverage:** A ≈ 735 + B ≈ 2,750 + C ≈ 1,460 = **4,945** ≈ the file's 4,944 lines
(±1 from boundary rounding; several regions are counted once though they mix
categories — noted inline).
