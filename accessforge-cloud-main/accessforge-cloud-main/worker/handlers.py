"""Per-module handlers — call the EXACT toolkit primitives from
redsea_toolkit.py (preserved verbatim per user request).

Each handler signature:
    handle(job, input_files: list[str], workdir: Path, log) -> list[str]
        job          : full job row dict
        input_files  : local paths to downloaded uploads, in selection order
        workdir      : Path with subdirs in/, out/
        log          : callable(progress:int, message:str)
        returns      : list of local file paths written under workdir/out/
"""
from __future__ import annotations
import os, re, json, shutil
from pathlib import Path
from typing import Callable

import fitz  # PyMuPDF
import pandas as pd

from .toolkit import (
    TcmIndexer, TASK_PATTERN, MPD_PATTERN, CHECK_RELATIONS, TAIL_MAP,
    build_check_regexes, ocr_page_text, group_contiguous, expand_check,
    normalize_check_code, expand_tasks_with_subtasks, unique_path,
    read_mpd_rsd_frame, find_cmpiss03_section_row,
)

Log = Callable[[int, str], None]


# ─── task_extractor ──────────────────────────────────────────────────────────
# Mirrors RedseaApp._run_extract (redsea_toolkit.py L1615) — full logic:
# 1. Find PDF by first-two-digits of the task code
# 2. Search for related subtasks in that PDF
# 3. Extract related tasks to separate PDFs
# 4. Fallback: extract pages containing the base task code
def task_extractor(job, input_files, workdir: Path, log: Log) -> list[str]:
    payload = job.get("input_refs") or {}
    code = str(payload.get("task_code") or "").strip()

    # ── Legacy mode: no task_code → scan all PDFs for all codes (original web behavior)
    if not code:
        rows: list[dict] = []
        for idx, pdf in enumerate(input_files, 1):
            log(int(5 + 80 * idx / max(1, len(input_files))), f"scan {os.path.basename(pdf)}")
            try:
                doc = fitz.open(pdf)
            except Exception as e:
                log(0, f"open failed {pdf}: {e}"); continue
            try:
                for page_no, page in enumerate(doc, 1):
                    text = page.get_text("text") or ""
                    if not text.strip():
                        text = ocr_page_text(page)
                    for found_code in set(TASK_PATTERN.findall(text)):
                        rows.append({"file": os.path.basename(pdf), "page": page_no, "code": found_code})
            finally:
                doc.close()
        out_xlsx = workdir / "out" / "tasks.xlsx"
        out_json = workdir / "out" / "tasks.json"
        pd.DataFrame(rows).to_excel(out_xlsx, index=False)
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        log(95, f"extracted {len(rows)} task occurrences")
        return [str(out_xlsx), str(out_json)]

    # ── Full mode: task_code provided → mirror _run_extract logic from app2.py
    first_two_digits = code.split('-')[0] if '-' in code else code[:2]
    log(10, f"Looking for PDF files starting with: {first_two_digits}")

    # Find matching PDF among uploaded files
    matching = [p for p in input_files if os.path.basename(p).startswith(first_two_digits)]
    if not matching:
        log(20, f"No PDF starting with '{first_two_digits}' among uploads, scanning all...")
        matching = input_files  # fallback: scan all uploaded PDFs

    pdf_path = matching[0]
    log(15, f"Using PDF: {os.path.basename(pdf_path)}")

    out_dir = workdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[str] = []

    # Step 1: Search for related subtasks
    log(20, f"Searching for related tasks to '{code}'...")
    m = re.match(r"^(\d{2}-\d{2,3})-\d{2}$", code.strip())
    related_tasks: list[str] = []
    if m:
        prefix = m.group(1) + "-"
        try:
            doc = fitz.open(pdf_path)
            found = set()
            for page in doc:
                text = page.get_text("text") or ""
                if not text.strip():
                    text = ocr_page_text(page)
                for m2 in TASK_PATTERN.finditer(text):
                    cand = m2.group(0)
                    if cand.startswith(prefix) and cand != code:
                        found.add(cand)
            related_tasks = sorted(found)
            doc.close()
        except Exception as e:
            log(25, f"Error scanning for related tasks: {e}")

    if related_tasks:
        log(30, f"Found {len(related_tasks)} related tasks: {', '.join(related_tasks)}")
        all_codes = [code] + related_tasks
        try:
            doc = fitz.open(pdf_path)
            for i, c in enumerate(all_codes):
                # Scan pages for this code (simple string match, skip index pages)
                page_matches = []
                for pn in range(doc.page_count):
                    text = doc[pn].get_text("text") or ""
                    upper = text.upper()
                    is_index = False
                    if any(mk in upper for mk in ("INDEX", "TABLE OF CONTENTS", "LIST OF EFFECTIVE PAGES")):
                        if len(TASK_PATTERN.findall(text)) > 10:
                            is_index = True
                    if c in text and not is_index:
                        page_matches.append(pn)
                if not page_matches:
                    continue
                out_doc = fitz.open()
                for run in group_contiguous(page_matches):
                    out_doc.insert_pdf(doc, from_page=run[0], to_page=run[-1])
                out_name = f"{c.replace('/', '_')}_related.pdf"
                out_path = out_dir / out_name
                out_doc.save(out_path, deflate=True)
                out_doc.close()
                outputs.append(str(out_path))
                log(30 + int(50 * (i + 1) / len(all_codes)), f"Extracted: {out_name}")
            doc.close()
        except Exception as e:
            log(50, f"Error extracting related tasks: {e}")

        if outputs:
            log(90, f"Successfully extracted {len(outputs)} related task PDF(s)")
            return outputs

    # Step 2: Fallback — extract base task pages only
    log(60, f"Searching for base task '{code}' in {os.path.basename(pdf_path)}...")
    try:
        doc = fitz.open(pdf_path)
        page_matches = []
        for pn in range(doc.page_count):
            text = doc[pn].get_text("text") or ""
            upper = text.upper()
            is_index = False
            if any(mk in upper for mk in ("INDEX", "TABLE OF CONTENTS", "LIST OF EFFECTIVE PAGES")):
                if len(TASK_PATTERN.findall(text)) > 10:
                    is_index = True
            if code in text and not is_index:
                page_matches.append(pn)

        if not page_matches:
            log(80, f"No matching pages found for '{code}'")
            # Still output an empty result file
            out_json = out_dir / "no_results.json"
            out_json.write_text(json.dumps({"task_code": code, "message": "No pages found"}, indent=2), encoding="utf-8")
            doc.close()
            return [str(out_json)]

        log(75, f"Found {len(page_matches)} pages with '{code}'")
        out_doc = fitz.open()
        for run in group_contiguous(page_matches):
            out_doc.insert_pdf(doc, from_page=run[0], to_page=run[-1])
        out_name = f"{code.replace('/', '_')}_extracted.pdf"
        out_path = out_dir / out_name
        out_doc.save(out_path, deflate=True)
        out_doc.close()
        doc.close()
        outputs.append(str(out_path))
        log(90, f"Extracted base task: {out_name}")
    except Exception as e:
        log(80, f"Error extracting base task: {e}")

    log(95, f"done — {len(outputs)} file(s)")
    return outputs


# ─── task_stamping ───────────────────────────────────────────────────────────
# Mirrors RedseaApp._stamp_page_data (redsea_toolkit.py L1915) — overlays Tail,
# Airline Card No (RC number derived from BOEING CARD NO), Station, and Date.

# The 4-segment task code `_stamp_process_single_pdf` (redsea_toolkit.py L2019)
# splits a document on, transcribed verbatim from the desktop source.
STAMP_TASK_PATTERN = re.compile(r"(\d{2,3}-\d{3}-\d{2}-\d{2})")
# Desktop scans page indices 0..4 for the fleet code (`if i > 4: break`, L2006).
STAMP_COVER_SCAN_PAGES = 5


def _stamp_page_text(page) -> str:
    """`page.get_text() or self._stamp_extract_text_with_ocr(page)` (L2007/L2017).

    Desktop's OCR helper and the worker's `ocr_page_text` differ only in DPI and
    in swallowing errors as "" — both return a plain string, so detection behaves
    the same on a scanned page with no text layer.
    """
    try:
        return page.get_text() or ocr_page_text(page) or ""
    except Exception:
        return ""


def _stamp_document(doc, tail: str, station: str, date: str, log: Log, label: str,
                    progress: int) -> None:
    """Line-for-line port of `_stamp_page_data` (redsea_toolkit.py L1915).

    Extracted from the old inline loop so the whole-document path and each
    per-task extract stamp through exactly the same code.
    """
    for page_num, page in enumerate(doc):
        try:
            airline_card_no = "RC"
            found_number = False

            # --- Method 1: Location-based text search ---
            search_terms = ["BOEING CARD NO.", "BOEING CARD NO"]
            search_instances = []
            for term in search_terms:
                search_instances = page.search_for(term)
                if search_instances:
                    break

            if search_instances:
                label_rect = search_instances[0]
                search_area = fitz.Rect(label_rect.x1 - 5, label_rect.y0 - 5, label_rect.x1 + 300, label_rect.y1 + 5)
                extracted_text = page.get_text("text", clip=search_area).strip()

                if extracted_text:
                    boeing_match = re.search(r'([\d-]+)', extracted_text)
                    if boeing_match:
                        full_boeing_no = boeing_match.group(1).strip()
                        parts = full_boeing_no.split('-')
                        if len(parts) >= 3:
                            airline_card_no = f"RC{parts[0]}-{parts[1]}-{parts[2]}"
                            found_number = True
                        elif len(parts) >= 2:
                            airline_card_no = f"RC{parts[0]}-{parts[1]}"
                            found_number = True

            # --- Method 2: Fallback to full page text search ---
            if not found_number:
                page_text = page.get_text()
                boeing_match = re.search(r"BOEING\s+CARD\s+NO\.?\s*([\d-]+)", page_text, re.IGNORECASE)
                if boeing_match:
                    full_boeing_no = boeing_match.group(1).strip()
                    parts = full_boeing_no.split('-')
                    if len(parts) >= 3:
                        airline_card_no = f"RC{parts[0]}-{parts[1]}-{parts[2]}"
                    elif len(parts) >= 2:
                        airline_card_no = f"RC{parts[0]}-{parts[1]}"

            # --- Stamping ---
            items_to_stamp = [
                ("TAIL NUMBER", tail),
                ("AIRLINE CARD NO", airline_card_no),
                ("STATION", station),
                ("DATE", date)
            ]
            for stamp_label, value in items_to_stamp:
                if not value: continue
                instances = page.search_for(stamp_label)
                for inst in instances:
                    page.insert_text((inst.x0, inst.y1 + 10), value, fontsize=10, color=(0, 0, 0))
        except Exception as e:
            log(progress, f"Error stamping page {page_num+1} of {label}: {e}")


def _stamp_detect_plane_code(doc, log: Log, progress: int) -> str | None:
    """Cover-page fleet code, exactly as `_stamp_process_single_pdf` L2005-2013.

    First `TAIL_MAP` key found on pages 0..4 wins, in TAIL_MAP's own key order.
    """
    for i, page in enumerate(doc):
        if i >= STAMP_COVER_SCAN_PAGES:
            break
        text = _stamp_page_text(page)
        for code in TAIL_MAP.keys():
            if code in text:
                log(progress, f"Detected plane code from cover: {code} -> {TAIL_MAP[code]}")
                return code
    return None


def _stamp_group_pages_by_task(doc, log: Log, progress: int) -> dict:
    """Task code -> page indices, exactly as `_stamp_process_single_pdf` L2016-2022.

    `re.search`, not `finditer`: only the FIRST 4-segment code on a page counts,
    so a page listing two codes belongs to one task. Grouping is by membership
    with no contiguity requirement (pages 0 and 2 can share a task), and a page
    carrying no code at all joins no task and is dropped from every extract.
    """
    tasks: dict[str, list[int]] = {}
    for i, page in enumerate(doc):
        match = STAMP_TASK_PATTERN.search(_stamp_page_text(page))
        if match:
            tasks.setdefault(match.group(1), []).append(i)
    if tasks:
        log(progress, f"Found {len(tasks)} unique task(s): {', '.join(tasks)}")
    return tasks


def task_stamping(job, input_files, workdir: Path, log: Log) -> list[str]:
    # PORTED FROM DESKTOP, WITH ONE DELIBERATE, OWNER-APPROVED FIX.
    #
    # This now implements desktop's real button flow (`_stamp_start_process` ->
    # `_stamp_process_folder` -> `_stamp_process_single_pdf`, app2.py:1912 /
    # redsea_toolkit.py:1994): cover-page tail auto-detection through `TAIL_MAP`,
    # plus splitting a multi-task PDF into one stamped file per detected task code.
    #
    # THE FIX (do not "restore" desktop's behaviour here): desktop's per-task loop
    # writes every task's extract to the SAME reused path
    # (`temp_file = os.path.join(output_folder, f"temp_{basename}")`, L1997) and
    # runs `os.replace(temp_file, input_file)` inside the loop (L1970/L2052), so in
    # a file with N tasks only the LAST one survives on disk and the other N-1
    # extracts are silently destroyed. That is an unintentional data-loss defect in
    # app2.py itself, not a product rule — no other code path avoids it. Worse, on
    # Windows (the desktop app's own platform) that `os.replace` targets a file
    # `doc` still holds open, so it raises `[WinError 5] Access is denied`, the
    # outer `except` swallows it, and the button writes NOTHING while leaving an
    # orphan `temp_<name>.pdf` behind — verified in this repo, and pinned by
    # `TestTaskStampingAutoDetectAndSplit`. Here each task is written to its own
    # `STAMPED_{task}_{basename}.pdf` (further de-duplicated through
    # `unique_path`), so all N survive and no input is ever rewritten in place.
    #
    # TWO OTHER DELIBERATE DEVIATIONS, both owner-approved:
    #  1. Manual tail wins. The shipped frontend
    #     (src/routes/_authenticated/modules/task-stamping.tsx) has a real Tail
    #     Number field; a non-empty `tail` in the payload is an explicit user
    #     choice and overrides auto-detection for the whole job. `TAIL_MAP`
    #     auto-detection only runs when the payload leaves `tail` empty.
    #  2. An undetected tail suppresses only the TAIL NUMBER field. Desktop skips
    #     `_stamp_page_data` altogether when no plane code is found (L1958-1959),
    #     losing the card number, station and date too; the sibling CMP/TCM stamper
    #     instead defaults to the FIRST TAIL_MAP entry (L2965), i.e. stamps SU-RSA
    #     onto an unidentified aircraft. Neither is acceptable, so the effective
    #     tail simply stays empty and `_stamp_document`'s existing `if not value:
    #     continue` leaves that one label alone — never a placeholder.
    #
    # Finally, desktop's `_stamp_process_single_pdf` returns without writing
    # anything when a document contains no task codes at all (L1942-1945). The web
    # port keeps its pre-existing behaviour instead — stamp the whole document as a
    # single output — because "no recognisable task code" is a normal document
    # shape here, not an error, and silently returning zero files would look like a
    # failed job.
    payload = job.get("input_refs") or {}
    # Empty tail/station/date must stay empty: _stamp_page_data skips falsy values
    # (`if not value: continue`), so a placeholder default here would stamp the literal
    # word "TAIL"/"STATION" onto pages the desktop app leaves alone.
    manual_tail = str(payload.get("tail") or job.get("metadata", {}).get("tail") or "")
    station = str(payload.get("station") or "")
    date = str(payload.get("date") or "")
    outputs: list[str] = []

    out_dir = workdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, pdf in enumerate(input_files, 1):
        progress = int(10 + 85 * i / max(1, len(input_files)))
        basename = os.path.basename(pdf)
        try:
            doc = fitz.open(pdf)
        except Exception as e:
            log(0, f"Error opening {pdf}: {e}"); continue

        try:
            # (a) Resolve the tail for this file: manual input wins outright.
            tail = manual_tail
            if not tail:
                plane_code = _stamp_detect_plane_code(doc, log, progress)
                if plane_code:
                    tail = TAIL_MAP.get(plane_code, "")
                else:
                    log(progress, f"No plane code on the first {STAMP_COVER_SCAN_PAGES} pages of "
                            f"{basename}; TAIL NUMBER will be left unstamped")

            # (b) Group pages by the 4-segment task code.
            tasks = _stamp_group_pages_by_task(doc, log, progress)

            # (d) No task codes anywhere → stamp the whole document as one unit.
            if not tasks:
                _stamp_document(doc, tail, station, date, log, basename, progress)
                out = Path(unique_path(str(out_dir / f"STAMPED_{basename}")))
                doc.save(out, deflate=True)
                outputs.append(str(out))
                log(progress, f"stamped {out.name}")
                continue

            # (c) One surviving output file per detected task.
            for task_code, page_indices in tasks.items():
                task_doc = fitz.open()
                try:
                    for pno in page_indices:
                        task_doc.insert_pdf(doc, from_page=pno, to_page=pno)
                    _stamp_document(task_doc, tail, station, date, log, f"{basename} [{task_code}]",
                                    progress)
                    safe_task = re.sub(r"[^A-Za-z0-9._-]", "_", task_code)
                    out = Path(unique_path(str(out_dir / f"STAMPED_{safe_task}_{basename}")))
                    task_doc.save(out, deflate=True)
                finally:
                    task_doc.close()
                outputs.append(str(out))
                log(progress, f"stamped {out.name} ({len(page_indices)} page(s))")
        finally:
            doc.close()

    return outputs


# ─── effectivity ─────────────────────────────────────────────────────────────
# Mirrors RedseaApp._load_excel_generic (L2148) — reads Excel/CSV, normalises
# headers, writes back as a clean Excel.
def effectivity(job, input_files, workdir: Path, log: Log) -> list[str]:
    payload = job.get("input_refs") or {}
    if payload.get("data_source") == "db":
        log(50, "Database source is selected. (Pending DB Migrations implementation)")
        raise NotImplementedError("Database source for Effectivity is not yet implemented.")
        
    out_files: list[str] = []
    for src in input_files:
        df = pd.read_excel(src) if src.lower().endswith((".xlsx", ".xls")) else pd.read_csv(src)
        df.columns = [str(c).strip() for c in df.columns]
        dst = workdir / "out" / f"EFFECTIVITY_{Path(src).stem}.xlsx"
        df.to_excel(dst, index=False); out_files.append(str(dst))
        log(80, f"normalised {dst.name} ({len(df)} rows)")
    return out_files


# ─── check_control ───────────────────────────────────────────────────────────
# Mirrors RedseaApp._load_check_csv (L2272) + CHECK_RELATIONS expansion.
def check_control(job, input_files, workdir: Path, log: Log) -> list[str]:
    payload = job.get("input_refs") or {}
    if payload.get("data_source") == "db":
        log(50, "Database source is selected. (Pending DB Migrations implementation)")
        raise NotImplementedError("Database source for Check Control is not yet implemented.")
        
    target_check = str(payload.get("check") or "").upper().strip() or "A1"
    included = expand_check(target_check)
    rows = []
    for src in input_files:
        df = pd.read_csv(src) if src.lower().endswith(".csv") else pd.read_excel(src)
        for _, r in df.iterrows():
            code = str(r.get("CHECK") or r.iloc[0]).strip().upper()
            if code in included:
                rows.append({**r.to_dict(), "_matched": target_check})
    out = workdir / "out" / f"CHECKS_{target_check}.xlsx"
    pd.DataFrame(rows).to_excel(out, index=False)
    log(90, f"{target_check} → {len(rows)} rows (expanded: {','.join(included)})")
    return [str(out)]


# ─── utilization ─────────────────────────────────────────────────────────────
# Mirrors RedseaApp hash_function_* (L2453+) — appends sha256/md5 per row.
def utilization(job, input_files, workdir: Path, log: Log) -> list[str]:
    payload = job.get("input_refs") or {}
    if payload.get("data_source") == "db":
        log(50, "Database source is selected. (Pending DB Migrations implementation)")
        raise NotImplementedError("Database source for Utilization is not yet implemented.")
        
    import hashlib
    out_files: list[str] = []
    for src in input_files:
        df = pd.read_excel(src) if src.lower().endswith((".xlsx", ".xls")) else pd.read_csv(src)
        # Join the ORIGINAL columns once, before either hash column is added.
        # Assigning df["_sha256"] mutates df in place, so a second
        # df.astype(str).agg(...) call afterwards would join "x|y|<sha256 hex>"
        # instead of "x|y" -- the two digests would stop being hashes of the
        # same row, which defeats the point of having both.
        if df.empty:
            # On pandas 2.2 `agg("|".join, axis=1)` over a zero-row frame returns
            # a DataFrame rather than a Series, and assigning it to a single
            # column raises "Cannot set a DataFrame with multiple columns".
            # An empty sheet is a legitimate input, so emit it with the hash
            # columns present and no rows instead of failing the job.
            df["_sha256"] = []
            df["_md5"] = []
        else:
            joined = df.astype(str).agg("|".join, axis=1)
            df["_sha256"] = joined.map(lambda s: hashlib.sha256(s.encode()).hexdigest())
            df["_md5"] = joined.map(lambda s: hashlib.md5(s.encode()).hexdigest())
        dst = workdir / "out" / f"UTIL_{Path(src).stem}.xlsx"
        df.to_excel(dst, index=False); out_files.append(str(dst))
        log(85, f"hashed {dst.name}")
    return out_files


def cmp_tcm(job, input_files, workdir: Path, log: Log) -> list[str]:
    payload = job.get("input_refs") or {}
    check_code = str(payload.get("check") or "").upper().strip()

    pdfs = [p for p in input_files if p.lower().endswith(".pdf")]
    # `.xlsb` belongs here: App2's own file picker offers "*.xlsx;*.xls;*.xlsb"
    # (app2.py:2999) and real MPD RSD deliveries are frequently binary
    # workbooks. Omitting it left a selected .xlsb invisible to this handler,
    # which then took the "no Excel provided" path and emitted only a TCM index.
    excels = [p for p in input_files if p.lower().endswith((".xlsx", ".xls", ".xlsb", ".csv"))]

    tcm_dir = workdir / "in" / "tcm"
    tcm_dir.mkdir(parents=True, exist_ok=True)
    for p in pdfs:
        shutil.copy2(p, tcm_dir / os.path.basename(p))

    log(10, f"Building TCM index from {len(pdfs)} PDFs...")
    indexer = TcmIndexer(str(tcm_dir), threads=4, cache=True)
    indexer.build_index(progress_callback=lambda m: log(50, m.strip()))
    
    out_files = []
    
    # If no excel/check provided, just return the index JSON
    if not excels or not check_code:
        out = workdir / "out" / "tcm_index.json"
        out.write_text(json.dumps(indexer.index, ensure_ascii=False, indent=2), encoding="utf-8")
        log(95, f"indexed {len(indexer.index)} PDFs (no Excel provided)")
        return [str(out)]

    log(60, f"Extracting tasks for check {check_code} from Excel...")
    excel_path = excels[0]
    try:
        # `.csv` has no App2 equivalent -- the desktop extractor only ever reads
        # Excel -- so it keeps the web handler's own reader. Everything App2 does
        # read goes through the shared toolkit helper, which is where the
        # `.xlsb` engine and MPD-RSD-sheet selection live.
        if excel_path.lower().endswith(".csv"):
            df = pd.read_csv(excel_path)
        else:
            df = read_mpd_rsd_frame(excel_path)
    except Exception as e:
        # Raise, do not `return []`. An unreadable workbook is a failure, not a
        # result: the runner treats an empty return as success and marks the job
        # `done, progress=100, 0 files`, which is indistinguishable from "this
        # check legitimately has no task cards". Worse, `Job.logs` is write-only
        # -- `_job_payload` never returns it and nothing reads it -- so the
        # message above would never reach the operator. `error_message` IS
        # surfaced, so failing loudly is the only way they learn the file was
        # corrupt. (The desktop shows the same text in a visible log pane.)
        raise ValueError(
            f"Could not read {os.path.basename(excel_path)} as a workbook: {e}"
        ) from e
    if df is None:
        raise ValueError(
            f"Could not read any sheet from {os.path.basename(excel_path)}."
        )

    df_str = df.astype(str)

    # CMPISS03 R1 section marker -- App2's format gate (app2.py:3214-3238).
    # A workbook (or the wrong sheet of the right workbook) that never mentions
    # CMPISS03 R1 is not an MPD RSD sheet, and the desktop returns [] and says
    # so. Without this gate the web handler went straight to column 24 of
    # whatever it was handed: any spreadsheet with 25+ columns whose 25th column
    # happened to hold the selected check code produced task cards that looked
    # legitimate. The marker only validates the format -- App2 captures the row
    # index and then still scans every row -- so nothing below is sliced by it.
    #
    # `.csv` is exempt. The gate mirrors a rule App2 applies while reading an
    # Excel workbook; App2's extractor never reads CSV at all, so there is no
    # desktop behaviour to match, and holding a web-only input format to an
    # App2-only format marker just rejects CSVs that used to work.
    is_csv = excel_path.lower().endswith(".csv")
    if not is_csv and find_cmpiss03_section_row(df_str) < 0:
        log(60, f"CMPISS03 R1 section not found in {os.path.basename(excel_path)}; "
                f"this is not an MPD RSD sheet. No task cards generated.")
        return []

    # The selected check is expanded into every associated check BEFORE any row
    # is read, exactly as the desktop does (app2.py:3471 `associated =
    # expand_check(selected)`, then a loop pulling tasks per associated check).
    # CHECK_RELATIONS["C4"] == ["C1", "C2", "C4"], so a C4 job must also collect
    # the rows tagged C1 and C2. Matching only the literal selected code -- what
    # this handler did before -- silently dropped every task contributed by a
    # lower associated check. The relation is one-directional: C1 expands to
    # ["C1"] alone and must NOT pull C4's tasks.
    associated_checks = expand_check(check_code) or [check_code]
    log(62, f"Check {check_code} -> associated: {', '.join(associated_checks)}")

    # Column 24 holds the check code, column 0 the task code.
    #
    # App2 matches the check by EQUALITY on two tiers (app2.py:3247-3260, and
    # redsea_toolkit.py:3330-3341): first the whitespace-stripped, upper-cased
    # cell against the same form of the target, then _normalize_check_code of
    # both sides. It is never a containment test. A substring match turns every
    # check code into a prefix filter -- asking for "A1" silently absorbs "A10"
    # and "A11", emitting task cards the operator never requested. The same
    # two-tier equality now runs once per associated check; `any` over the
    # associated set is equivalent to the desktop's per-check loop.
    targets = [
        (re.sub(r"\s+", "", chk).upper(), normalize_check_code(chk))
        for chk in associated_checks
    ]
    # A set, so a task claimed by two associated checks is collected once.
    #
    # The desktop writes one PDF per (check, task) pair because it owns a
    # filesystem tree: out_dir/C1/52-020-00.pdf and out_dir/C4/52-020-00.pdf
    # (app2.py:3500). Those two files are byte-identical -- same task, same
    # index hit, same page range -- the folder is presentation, not content.
    # The web job model has no folder concept (every handler here returns a flat
    # list of files), so per-check copies would either collide on the same
    # out/<task>.pdf name -- one overwriting the other -- or need synthetic
    # names like C4__52-020-00.pdf that no desktop output ever had. Deduping the
    # task set instead loses nothing: the deliverable is one PDF per task, and
    # every task the desktop would have produced under any associated check is
    # still produced exactly once.
    tasks = set()
    if df_str.shape[1] > 24:
        for idx in range(len(df_str)):
            cell_raw = str(df_str.iloc[idx, 24]).strip()
            cell_stripped = re.sub(r"\s+", "", cell_raw).upper()
            cell_normalized = normalize_check_code(cell_raw)
            matches = any(
                cell_stripped == target_stripped or cell_normalized == target_normalized
                for target_stripped, target_normalized in targets
            )
            if not matches:
                continue
            task = str(df_str.iloc[idx, 0]).strip()
            if task and task != "nan":
                tasks.add(task)

    # Subtask expansion, App2's actual rule (app2.py:3082
    # _expand_tasks_with_subtasks): for a 3-segment base task, append a 4th
    # segment -01..-10 to the FULL code and keep the ones the index contains.
    # This handler previously called TcmIndexer.find_related_subtasks, which
    # instead drops the last segment and returns every sibling under the
    # two-segment prefix (27-054-00 -> 27-054-*) -- a different task family, and
    # dead code in app2.py with no caller at all.
    sorted_tasks = expand_tasks_with_subtasks(sorted(tasks), indexer)
    log(70, f"Found {len(sorted_tasks)} tasks/subtasks for {check_code}")

    # For each task, extract from TCM
    for i, task in enumerate(sorted_tasks):
        log(70 + int(20 * i / max(1, len(sorted_tasks))), f"Extracting {task}")
        pdf_path, run = indexer.find_best_occurrence_for_task(task)
        if not pdf_path or not run:
            # App2 says so out loud (app2.py:3510). Without this the operator
            # sees "Found 7 tasks" then "Generated 4 task PDFs" and nothing
            # accounts for the missing three.
            log(70 + int(20 * i / max(1, len(sorted_tasks))),
                f"{task}: not found in index")
            continue

        start, end = run[0], run[1] if isinstance(run, (list,tuple)) and len(run)>=2 else (run[0], run[-1])
        src = None
        out_doc = None
        try:
            src = fitz.open(pdf_path)
            out_doc = fitz.open()
            out_doc.insert_pdf(src, from_page=start, to_page=end)

            out_pdf = workdir / "out" / f"{task}.pdf"
            out_doc.save(out_pdf, deflate=True)
            out_files.append(str(out_pdf))
        except Exception as e:
            log(70 + int(20 * i / max(1, len(sorted_tasks))), f"Failed to extract {task}: {e}")
        finally:
            # Closed in a finally, as app2.py:3542-3544 does: a failure inside
            # insert_pdf/save would otherwise leak both handles for the lifetime
            # of the worker process, once per failing task.
            for handle in (out_doc, src):
                if handle is not None:
                    try:
                        handle.close()
                    except Exception:
                        pass

    log(95, f"Generated {len(out_files)} task PDFs")
    return out_files


# ─── cover_merge ─────────────────────────────────────────────────────────────
# Mirrors the cover-onto-task-card concatenation logic. First file = cover,
# remaining = task cards; produces one merged PDF.
def cover_merge(job, input_files, workdir: Path, log: Log) -> list[str]:
    if len(input_files) < 2:
        raise ValueError("cover_merge requires at least 2 PDFs (cover + task card)")
    merged = fitz.open()
    for i, pdf in enumerate(input_files):
        src = fitz.open(pdf)
        merged.insert_pdf(src); src.close()
        log(int(10 + 80 * (i + 1) / len(input_files)), f"merged {os.path.basename(pdf)}")
    out = workdir / "out" / "MERGED.pdf"
    merged.save(out, deflate=True); merged.close()
    return [str(out)]


# ─── mail_merge (Covering) ───────────────────────────────────────────────────
# Mirrors RedseaApp._mm_generate_document (L4099) context building +
# RedseaApp._mm_manual_replace (L4064), the real "Generate Document" flow.
# (It previously mirrored _mm_replace_merge_fields at L4659, which has no caller
# anywhere in app2.py -- dead code, same trap as find_related_subtasks/cmp_tcm.)
# First file = .docx template, second = .xlsx data; produces one .docx per row.


def _mm_build_context(row) -> dict:
    """app2.py:4139-4155 -- the desktop's per-row context, verbatim.

    Two things happen to every column value before it is usable as a
    replacement, and both are load-bearing:

    1. Dash-separated numeric codes are wrapped in Unicode LTR embedding marks
       (U+202A ... U+202C) so an RTL/Arabic rendering context does not display
       53-844-00 as 00-844-53. This app's UI is bilingual, so it is live.
    2. Each column also gets a normalized-key alias with everything outside
       [A-Z0-9_] stripped, so a column named "MPD Item" answers to «MPDITEM».
    """
    context: dict[str, str] = {}
    for col, value in row.items():
        val_str = str(value).strip() if pd.notnull(value) and value != "" else ""
        if re.search(r"\d+-\d+", val_str):
            val_str = f"\u202A{val_str}\u202C"
        context[str(col)] = val_str
        normalized = re.sub(r"[^A-Z0-9_]", "", str(col).upper())
        if normalized != str(col).upper():
            context[normalized] = val_str
    return context


def _mm_manual_replace(doc, context: dict) -> None:
    """app2.py:4064-4097 -- paragraph-level placeholder replacement.

    Deliberately works on paragraph.text, not run by run. Word routinely splits
    one visible «TITLE» across several XML runs (autocorrect, spell-check
    boundaries, copy/paste), and a run-level scan matches none of the fragments,
    silently leaving the placeholder in the output. Reading the whole paragraph
    is what makes those documents merge.

    Assigning paragraph.text collapses the paragraph into a single run, dropping
    per-run formatting inside it. That is the desktop's own accepted tradeoff and
    therefore the parity target -- do not "improve" it here.
    """

    def replace_text(text: str) -> str:
        for key, value in context.items():
            if value is None:
                value = ""
            # Four guillemet spacing variants (app2.py:4075), plus the <<KEY>>
            # and {{KEY}} tolerance the web handler has always carried.
            patterns = [
                f"«{key}»", f"« {key} »", f"«{key} »", f"« {key}»",
                f"<<{key}>>", f"{{{{{key}}}}}",
            ]
            for p in patterns:
                if p in text:
                    text = text.replace(p, str(value))
        return text

    def process_paragraph(paragraph) -> None:
        if not any(marker in paragraph.text for marker in ("«", "<<", "{{")):
            return
        new_text = replace_text(paragraph.text)
        if new_text != paragraph.text:
            paragraph.text = new_text

    for p in doc.paragraphs:
        process_paragraph(p)

    for table in doc.tables:
        for trow in table.rows:
            for cell in trow.cells:
                for p in cell.paragraphs:
                    process_paragraph(p)


def mail_merge(job, input_files, workdir: Path, log: Log) -> list[str]:
    from docx import Document
    template = next((p for p in input_files if p.lower().endswith(".docx")), None)
    data = next((p for p in input_files if p.lower().endswith((".xlsx", ".xls", ".csv"))), None)
    if not (template and data):
        raise ValueError("mail_merge needs one .docx template + one .xlsx/.csv data file")
    df = pd.read_excel(data) if data.lower().endswith((".xlsx", ".xls")) else pd.read_csv(data)
    out_files: list[str] = []
    for idx, row in df.iterrows():
        doc = Document(template)
        ctx = _mm_build_context(row)
        _mm_manual_replace(doc, ctx)
        # Filename uses the raw cell value: on the desktop the name comes from the
        # MPD the user typed, never from the LTR-wrapped context value, so the
        # embedding marks must not leak into the output filename.
        raw = {str(k): ("" if pd.isna(v) else str(v).strip()) for k, v in row.items()}
        mpd = (raw.get("MPD") or raw.get("RC_NUM") or f"row{idx+1}").strip() or f"row{idx+1}"
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", mpd)
        # Two rows may legitimately share an MPD. Without a unique name the
        # second doc.save() overwrites the first, the job still reports both
        # paths, and the operator downloads two identical copies of the LAST row
        # never knowing the earlier one existed. The desktop's batch loop guards
        # exactly this with its own `while os.path.exists(...)` counter
        # (app2.py:4604-4609); `unique_path` is this repo's equivalent.
        out = Path(unique_path(str(workdir / "out" / f"RC_Card_{safe}.docx")))
        doc.save(out); out_files.append(str(out))
        log(int(10 + 85 * (idx + 1) / len(df)), f"generated {out.name}")
    return out_files


REGISTRY = {
    "task_extractor": task_extractor,
    "task_stamping":  task_stamping,
    "effectivity":    effectivity,
    "check_control":  check_control,
    "utilization":    utilization,
    "cmp_tcm":        cmp_tcm,
    "cover_merge":    cover_merge,
    "mail_merge":     mail_merge,
}
