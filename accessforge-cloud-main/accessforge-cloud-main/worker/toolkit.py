"""Headless import of the original REDSEA toolkit (verbatim file).

Installs Tk/CTk stubs BEFORE importing redsea_toolkit so the desktop file is
importable on a server without a display server. The worker calls only the
pure (non-GUI) helpers from redsea_toolkit:

    covering, TcmIndexer, TASK_PATTERN, MPD_PATTERN, CHECK_RELATIONS, TAIL_MAP,
    expand_check, build_check_regexes, page_to_image, ocr_page_text,
    group_contiguous, walk_pdfs_in_dir, is_pdf, safe_make_dir, unique_path

These functions are exactly the ones the user requested be preserved
unchanged.
"""
from . import tk_stub
tk_stub.install()

# noqa: E402 — import order is intentional
from . import redsea_toolkit as rt  # type: ignore  # noqa: E402

# Re-export the toolkit primitives we use in handlers.
covering = rt.covering
TcmIndexer = rt.TcmIndexer
TASK_PATTERN = rt.TASK_PATTERN
MPD_PATTERN = rt.MPD_PATTERN
CHECK_RELATIONS = rt.CHECK_RELATIONS
# Fleet code -> tail number, used by task_stamping's cover-page auto-detection.
# Bound to the class attribute object itself (not a copy) for the same anti-drift
# reason as CHECK_RELATIONS: the fleet table lives in exactly one place.
TAIL_MAP = rt.RedseaApp.TAIL_MAP
expand_check = rt.expand_check
build_check_regexes = rt.build_check_regexes
page_to_image = rt.page_to_image
ocr_page_text = rt.ocr_page_text
group_contiguous = rt.group_contiguous
walk_pdfs_in_dir = rt.walk_pdfs_in_dir
is_pdf = rt.is_pdf
safe_make_dir = rt.safe_make_dir
unique_path = rt.unique_path


class _HeadlessLogContext:
    """Stand-in ``self`` for RedseaApp methods that only touch logging.

    ``_expand_tasks_with_subtasks`` reads ``self.tx_cmp_tcm_log`` and calls
    ``self._safe_log`` -- both GUI concerns -- but nothing else on ``self``.
    Supplying this context lets the worker call the real method unbound rather
    than re-typing its rules.
    """

    tx_cmp_tcm_log = None

    def _safe_log(self, *_args, **_kwargs):
        return None


def expand_tasks_with_subtasks(base_tasks, tcm_indexer) -> list:
    """Expose App2's real subtask expansion as a plain, GUI-free function.

    ``RedseaApp._expand_tasks_with_subtasks`` (app2.py:3082) appends a 4th
    two-digit segment ``-01``..``-10`` to each 3-segment base task and keeps the
    candidates the TCM index actually contains -- e.g. ``52-020-00`` yields
    ``52-020-00-01`` .. ``52-020-00-10``. This is NOT what
    ``TcmIndexer.find_related_subtasks`` does: that one strips the last segment
    and returns every sibling sharing the two-segment prefix (``52-020-05`` and
    friends), a different task family. ``find_related_subtasks`` has no caller
    anywhere in app2.py; only this method drives the desktop CMP/TCM button.

    Called unbound for the same anti-drift reason as ``normalize_check_code``:
    the rule lives in exactly one place.
    """

    return rt.RedseaApp._expand_tasks_with_subtasks(
        _HeadlessLogContext(), list(base_tasks or []), tcm_indexer
    )


def read_mpd_rsd_frame(excel_path):
    """Read an MPD RSD workbook the way App2 does when no sheet name is given.

    Mirrors the no-sheet-name branch shared by
    ``RedseaApp._extract_tasks_from_excel_mpd_rsd`` (app2.py:3181-3203) and
    ``RedseaApp._extract_available_checks_from_excel`` (app2.py:3367-3388):

      * ``.xlsb`` is a binary workbook -- openpyxl cannot open it at all, so it
        needs ``engine='pyxlsb'``. Its sheet is chosen by NAME: the first sheet
        whose upper-cased name contains ``MPD RSD``, falling back to the first
        sheet. MPD RSD deliveries are routinely ``.xlsb`` because the workbooks
        are far too large for the XML format, and they routinely carry cover /
        revision sheets in front of the data, so "sheet 0" is the wrong sheet
        more often than it is the right one.
      * every other format keeps App2's plain ``sheet_name=0``.

    Unlike App2 this closes the ``ExcelFile`` handle after reading the sheet
    names; the desktop app leaks it, which is harmless in a short-lived GUI
    process and not harmless in a long-lived worker.

    DUPLICATION NOTE: ``backend/main.py::_read_mpd_rsd_frame`` is the same
    App2 logic, written separately on purpose. The backend and the worker are
    separate deployables with separate requirements files, and a backend that
    imported from ``worker/`` would couple them. If App2's sheet-selection rule
    is ever restated, BOTH copies must change.
    """

    import pandas as pd  # local: keeps toolkit importable without pandas

    path_text = str(excel_path)
    if path_text.lower().endswith(".xlsb"):
        workbook = pd.ExcelFile(path_text, engine="pyxlsb")
        try:
            sheet_names = list(workbook.sheet_names)
        finally:
            workbook.close()
        if not sheet_names:
            return None
        target = next(
            (name for name in sheet_names if "MPD RSD" in str(name).upper()),
            sheet_names[0],
        )
        return pd.read_excel(path_text, sheet_name=target, engine="pyxlsb")
    return pd.read_excel(path_text, sheet_name=0)


def find_cmpiss03_section_row(df_str) -> int:
    """Row index of the ``CMPISS03 R1`` section marker, or ``-1`` if absent.

    App2 refuses to read a workbook that has no such row
    (``_extract_tasks_from_excel_mpd_rsd``, app2.py:3214-3238): it joins every
    row's stringified cells with a space and runs TWO scans over them --

      1. ``re.search(r'\\bCMPISS03\\s+R1\\b', row_text, re.IGNORECASE)``
      2. ``'CMPISS03 R1' in row_text.upper()``

    -- returning ``[]`` when neither hits. The second scan looks redundant but
    is not: it has no word boundaries, so ``XCMPISS03 R1`` and ``CMPISS03 R1X``
    pass it while failing the regex. Both are reproduced here rather than
    collapsed, because collapsing them would reject workbooks App2 accepts.

    The matched index is deliberately NOT used to slice or offset anything:
    App2 captures it, logs it, and then scans ``range(len(df))`` regardless.
    The marker is a format gate, not a range limiter.
    """

    import re as _re

    for idx, row in df_str.iterrows():
        row_text = " ".join(row.values)
        if _re.search(r"\bCMPISS03\s+R1\b", row_text, _re.IGNORECASE):
            return idx
    for idx, row in df_str.iterrows():
        row_text = " ".join(row.values)
        if "CMPISS03 R1" in row_text.upper():
            return idx
    return -1


def normalize_check_code(value) -> str:
    """Expose App2's check-code normalizer as a plain function.

    ``RedseaApp._normalize_check_code`` (redsea_toolkit.py L3123) never touches
    ``self``, so it is called unbound. Transcribing its transformation table
    here instead would create a second copy of a business rule that must not
    diverge -- exactly the drift pattern that produced the Heavy divergence.
    """

    return rt.RedseaApp._normalize_check_code(None, value)


__all__ = [
    "covering", "TcmIndexer", "TASK_PATTERN", "MPD_PATTERN", "CHECK_RELATIONS",
    "TAIL_MAP", "expand_check", "build_check_regexes", "page_to_image",
    "ocr_page_text", "group_contiguous", "walk_pdfs_in_dir", "is_pdf",
    "safe_make_dir", "unique_path", "normalize_check_code",
    "expand_tasks_with_subtasks", "read_mpd_rsd_frame",
    "find_cmpiss03_section_row",
]
