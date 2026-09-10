import re
import shutil
import tempfile
import unittest
from pathlib import Path

import fitz
import pandas as pd

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _DesktopCmpContext:
    tx_cmp_tcm_log = None

    def __init__(self, toolkit):
        self._toolkit = toolkit

    def _safe_log(self, *_args):
        pass

    def _normalize_check_code(self, value):
        return self._toolkit.rt.RedseaApp._normalize_check_code(self, value)


class TestCmpTcmParity(unittest.TestCase):
    check_code = "A1"
    task_code = "27-001-00"
    # Related checks whose codes CONTAIN check_code as a prefix. Both must be
    # present: a substring match absorbs A10 *and* A11 when asked for A1.
    # Keyed by check code so the pairing cannot be read in the wrong order.
    related_checks = {"A10": "27-002-00", "A11": "27-003-00"}

    def _write_mpd_rsd_excel(self, path: Path, task_to_check: dict[str, str]) -> None:
        """Write an MPD RSD workbook: a CMPISS03 marker row, then one row per task.

        ``task_to_check`` maps a task code (column 0) to its check code
        (column 24). A dict rather than tuples because an earlier version of
        this helper took ``(task, check)`` pairs while the caller supplied
        ``(check, task)`` -- the rows were written swapped, the check column
        never contained A10/A11 at all, and the substring test passed
        vacuously.
        """

        columns = [f"COL_{index}" for index in range(25)]
        section = [""] * 25
        section[0] = "CMPISS03 R1"
        rows = [section]
        for task_code, check_code in task_to_check.items():
            row = [""] * 25
            row[0] = task_code
            row[24] = check_code
            rows.append(row)
        pd.DataFrame(rows, columns=columns).to_excel(path, index=False)

    def _all_rows(self) -> dict[str, str]:
        """Task -> check for the full fixture: the target check plus its prefixes."""

        rows = {self.task_code: self.check_code}
        for check_code, task_code in self.related_checks.items():
            rows[task_code] = check_code
        return rows

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cmp_tcm_parity_"))
        self.tcm_pdf = self.tmpdir / "tcm.pdf"
        self.excel = self.tmpdir / "mpd-rsd.xlsx"
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)
        pdf = fitz.open()
        # Every task referenced by any fixture row must exist in the TCM PDF.
        # If a wrongly-matched task were absent, find_best_occurrence_for_task
        # would skip it silently and the over-match would go undetected.
        for text in (
            "TARGET TASK 27-001-00\nORIGINAL TARGET PAGE",
            "OTHER TASK 27-002-00\nORIGINAL OTHER PAGE",
            "THIRD TASK 27-003-00\nORIGINAL THIRD PAGE",
        ):
            page = pdf.new_page(width=612, height=792)
            page.insert_text((72, 72), text, fontsize=12)
        pdf.save(self.tcm_pdf)
        pdf.close()

        columns = [f"COL_{index}" for index in range(25)]
        section = [""] * 25
        section[0] = "CMPISS03 R1"
        matching = [""] * 25
        matching[0] = self.task_code
        matching[24] = self.check_code
        pd.DataFrame([section, matching], columns=columns).to_excel(self.excel, index=False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_excel_task_selection_and_tcm_extraction_match_desktop(self):
        from worker import toolkit
        from worker.handlers import cmp_tcm

        desktop_tasks = toolkit.rt.RedseaApp._extract_tasks_from_excel_mpd_rsd(
            _DesktopCmpContext(toolkit), str(self.excel), self.check_code
        )
        self.assertEqual(desktop_tasks, [self.task_code])

        web_outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(self.excel)],
            self.workdir,
            lambda _progress, _message: None,
        )
        self.assertEqual(len(web_outputs), 1)
        web_output = Path(web_outputs[0])
        self.assertEqual(web_output.name, f"{self.task_code}.pdf")

        output = fitz.open(web_output)
        try:
            self.assertEqual(output.page_count, 1)
            self.assertEqual(output[0].rect, fitz.Rect(0, 0, 612, 792))
            self.assertIn(self.task_code, output[0].get_text())
            self.assertIn("ORIGINAL TARGET PAGE", output[0].get_text())
            self.assertNotIn("ORIGINAL OTHER PAGE", output[0].get_text())
        finally:
            output.close()


    def test_related_check_codes_are_not_matched_by_substring(self):
        """Asking for A1 must collect neither A10's nor A11's tasks.

        App2 matches the check in column 24 by EQUALITY -- first on the
        whitespace-stripped upper-cased cell, then on ``_normalize_check_code``
        of both sides (``app2.py:3247-3260``). It never does a containment test.
        A substring match makes every check code a prefix filter: A1 silently
        absorbs A10 and A11, producing task cards the operator did not ask for.

        This is a deliberate BEHAVIOUR CHANGE: a check whose code is a prefix of
        another now generates strictly fewer cards than before the fix. Cards
        generated by an earlier build may therefore differ.
        """

        from worker import toolkit
        from worker.handlers import cmp_tcm

        excel = self.tmpdir / "mpd-rsd-related.xlsx"
        self._write_mpd_rsd_excel(excel, self._all_rows())

        desktop_tasks = toolkit.rt.RedseaApp._extract_tasks_from_excel_mpd_rsd(
            _DesktopCmpContext(toolkit), str(excel), self.check_code
        )
        self.assertEqual(
            desktop_tasks,
            [self.task_code],
            "App2 itself must match neither A10 nor A11 when asked for A1",
        )

        web_outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(excel)],
            self.workdir,
            lambda _progress, _message: None,
        )
        produced = sorted(Path(path).name for path in web_outputs)
        self.assertEqual(
            produced,
            [f"{self.task_code}.pdf"],
            f"web handler must match App2 exactly; it produced {produced}",
        )
        for related_check, related_task in self.related_checks.items():
            self.assertNotIn(
                f"{related_task}.pdf",
                produced,
                f"{related_task} belongs to {related_check} and must not be generated for "
                f"{self.check_code}",
            )

    def test_each_related_check_still_finds_its_own_task(self):
        """The fix must narrow matching, not break it: A10 and A11 still work.

        The expected set is computed from App2 rather than hard-coded, because
        the selected check is expanded through ``CHECK_RELATIONS`` before any
        row is read (``app2.py:3471``). A10 expands to ``[A1, A2, A5, A10]``, so
        it legitimately also collects A1's task; A11 expands to ``[A1]`` -- it
        does not list itself -- so App2 generates A1's task for it and not its
        own. Hard-coding "one check, its own task" would pin a rule App2 does
        not have. What stays pinned here is the equality fix: no related check
        may absorb another related check's task by prefix.
        """

        from worker import toolkit
        from worker.handlers import cmp_tcm

        excel = self.tmpdir / "mpd-rsd-related.xlsx"
        self._write_mpd_rsd_excel(excel, self._all_rows())

        for related_check, related_task in self.related_checks.items():
            desktop_tasks = self._desktop_expected_tasks(toolkit, excel, related_check)
            workdir = self.tmpdir / f"web-work-{related_check}"
            (workdir / "out").mkdir(parents=True)
            web_outputs = cmp_tcm(
                {"input_refs": {"check": related_check}},
                [str(self.tcm_pdf), str(excel)],
                workdir,
                lambda _progress, _message: None,
            )
            produced = sorted(Path(path).name for path in web_outputs)
            self.assertEqual(
                produced,
                sorted(f"{task}.pdf" for task in desktop_tasks),
                f"check {related_check} must resolve exactly as App2 does",
            )
            for other_check, other_task in self.related_checks.items():
                if other_check == related_check:
                    continue
                self.assertNotIn(
                    f"{other_task}.pdf",
                    produced,
                    f"{other_task} belongs to {other_check}, which {related_check} "
                    f"does not include -- only a substring match could pull it in",
                )

    def _desktop_expected_tasks(self, toolkit, excel: Path, check_code: str) -> set[str]:
        """Tasks App2 itself would collect for ``check_code``.

        Mirrors ``_generate_task_cards_indexed`` (``app2.py:3471-3491``): expand
        the check, then run the real Excel extractor once per associated check.
        Subtask expansion is not applied -- these fixtures hold no 4-segment
        codes -- so this stays a pure check-hierarchy expectation.
        """

        context = _DesktopCmpContext(toolkit)
        expected: set[str] = set()
        for associated in toolkit.expand_check(check_code):
            expected.update(
                toolkit.rt.RedseaApp._extract_tasks_from_excel_mpd_rsd(
                    context, str(excel), associated
                )
            )
        return expected


class TestCmpTcmSectionMarkerGate(unittest.TestCase):
    """A workbook with no ``CMPISS03 R1`` row is not an MPD RSD sheet.

    ``_extract_tasks_from_excel_mpd_rsd`` scans every row's joined text for the
    section marker and returns ``[]`` when it is absent (``app2.py:3214-3238``).
    The web handler had no such gate: it went from ``read_excel`` straight to
    column 24, so any spreadsheet wide enough -- including the WRONG SHEET of
    the right workbook -- produced task cards that looked legitimate while App2
    would have produced none and said why.

    The marker is a FORMAT GATE, not a range limiter: App2 stores the matched
    row index, logs it, and then still scans ``range(len(df))``. Nothing here
    asserts that rows above the marker are skipped, because they are not.
    """

    check_code = "A1"
    task_code = "27-001-00"

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cmp_tcm_marker_"))
        self.tcm_pdf = self.tmpdir / "tcm.pdf"
        pdf = fitz.open()
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 72), f"TASK {self.task_code}\nPAGE FOR {self.task_code}", fontsize=12)
        pdf.save(self.tcm_pdf)
        pdf.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _workbook(self, name: str, marker_cells) -> Path:
        """A workbook whose only difference from a valid one is the marker row.

        ``marker_cells`` is ``None`` for "no marker row at all", otherwise a
        sequence of cell values placed at the start of the marker row. The data
        row is always a valid ``A1`` -> ``27-001-00`` pairing, so the ONLY thing
        that can change the outcome is the gate.
        """

        columns = [f"COL_{index}" for index in range(25)]
        rows = []
        if marker_cells is not None:
            section = [""] * 25
            for offset, value in enumerate(marker_cells):
                section[offset] = value
            rows.append(section)
        data = [""] * 25
        data[0] = self.task_code
        data[24] = self.check_code
        rows.append(data)
        path = self.tmpdir / name
        pd.DataFrame(rows, columns=columns).to_excel(path, index=False)
        return path

    def _run_web(self, excel: Path, label: str) -> list[str]:
        from worker.handlers import cmp_tcm

        workdir = self.tmpdir / f"web-work-{label}"
        (workdir / "out").mkdir(parents=True)
        outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(excel)],
            workdir,
            lambda _progress, _message: None,
        )
        return sorted(Path(path).name for path in outputs)

    def _run_desktop(self, excel: Path) -> list[str]:
        from worker import toolkit

        return toolkit.rt.RedseaApp._extract_tasks_from_excel_mpd_rsd(
            _DesktopCmpContext(toolkit), str(excel), self.check_code
        )

    def test_marker_present_still_produces_the_task_card(self):
        """Guards against the gate becoming a blanket refusal."""

        excel = self._workbook("with-marker.xlsx", ["CMPISS03 R1"])

        self.assertEqual(self._run_desktop(excel), [self.task_code])
        self.assertEqual(self._run_web(excel, "with-marker"), [f"{self.task_code}.pdf"])

    def test_workbook_without_the_marker_yields_nothing_on_both_sides(self):
        """The behaviour change: this workbook used to produce a task card.

        Every cell that matters is still there -- 25 columns, ``A1`` in column
        24, a task code in column 0, and a TCM PDF that contains it -- so before
        the gate the handler emitted ``27-001-00.pdf``. App2 emits nothing.
        """

        excel = self._workbook("no-marker.xlsx", None)

        self.assertEqual(
            self._run_desktop(excel),
            [],
            "App2 itself refuses a workbook with no CMPISS03 R1 row",
        )
        self.assertEqual(
            self._run_web(excel, "no-marker"),
            [],
            "the web handler must refuse exactly what App2 refuses",
        )

    def test_marker_spellings_accepted_and_rejected_match_the_desktop(self):
        """Cases derived from the two scans App2 actually runs, not invented.

        Scan 1 is ``re.search(r'\\bCMPISS03\\s+R1\\b', row_text, re.IGNORECASE)``
        over the row's cells joined by a single space, so it tolerates any case,
        any run of whitespace (including a tab or a newline inside one cell),
        the marker split across two adjacent cells (the join supplies the
        space), and surrounding words separated by whitespace.

        Scan 2 is a plain ``'CMPISS03 R1' in row_text.upper()``. It looks
        redundant and is not: with no word boundaries it accepts
        ``XCMPISS03 R1`` and ``CMPISS03 R1X``, which scan 1 rejects. Collapsing
        the two scans into one regex would reject workbooks App2 accepts, so
        both spellings are pinned here.
        """

        boundary_only = ("XCMPISS03 R1", "CMPISS03 R1X")
        accepted = {
            "canonical": ("CMPISS03 R1",),
            "lowercase": ("cmpiss03 r1",),
            "mixed_case": ("CmpIss03 r1",),
            "multi_space": ("CMPISS03   R1",),
            "tab_separated": ("CMPISS03\tR1",),
            "newline_separated": ("CMPISS03\nR1",),
            "split_across_two_cells": ("CMPISS03", "R1"),
            "leading_word_char": ("XCMPISS03 R1",),
            "trailing_word_char": ("CMPISS03 R1X",),
            "surrounded_by_words": ("REV CMPISS03 R1 SECTION",),
        }
        rejected = {
            "no_whitespace": ("CMPISS03R1",),
            "underscore_instead_of_space": ("CMPISS03_R1",),
            "wrong_revision": ("CMPISS03 R2",),
        }

        for label, cells in accepted.items():
            with self.subTest(marker=label):
                excel = self._workbook(f"accept-{label}.xlsx", cells)
                self.assertEqual(
                    self._run_desktop(excel),
                    [self.task_code],
                    f"App2 accepts {cells!r}",
                )
                self.assertEqual(self._run_web(excel, f"accept-{label}"), [f"{self.task_code}.pdf"])

        for label, cells in rejected.items():
            with self.subTest(marker=label):
                excel = self._workbook(f"reject-{label}.xlsx", cells)
                self.assertEqual(self._run_desktop(excel), [], f"App2 rejects {cells!r}")
                self.assertEqual(self._run_web(excel, f"reject-{label}"), [])

        for spelling in boundary_only:
            with self.subTest(marker=spelling, scan="regex-alone"):
                self.assertIsNone(
                    re.search(r"\bCMPISS03\s+R1\b", spelling, re.IGNORECASE),
                    f"{spelling!r} must fail the word-boundary regex -- it is accepted "
                    f"only by App2's second, literal scan",
                )


class TestCmpTcmXlsbWorkbooks(unittest.TestCase):
    """Binary ``.xlsb`` MPD RSD workbooks, and the sheet App2 picks inside them.

    ``tests/fixtures/mpd_rsd_sample.xlsb`` is a GENUINE binary workbook saved by
    Excel 16.0 as ``xlExcel12`` (``Workbook.SaveAs(..., FileFormat=50)``): an
    OPC/ZIP container whose parts are ``xl/workbook.bin`` and
    ``xl/worksheets/sheet*.bin``. pyxlsb is read-only, so it cannot be
    regenerated from Python alone -- rebuild it with Excel if it ever needs to
    change.

    It has two sheets, in this order:
        1. ``Cover``   -- a decoy: marker row + ``A1`` -> ``27-002-00``
        2. ``MPD RSD`` -- the real one: marker row + ``A1`` -> ``27-001-00``

    Reading "sheet 0", which is what the web handler did for every workbook,
    would silently produce the decoy's task. App2 instead picks the first sheet
    whose upper-cased name contains ``MPD RSD`` (app2.py:3184-3200).
    """

    check_code = "A1"
    expected_task = "27-001-00"
    decoy_task = "27-002-00"
    fixture = FIXTURES / "mpd_rsd_sample.xlsb"

    def setUp(self):
        self.assertTrue(self.fixture.is_file(), f"missing fixture {self.fixture}")
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cmp_tcm_xlsb_"))
        self.tcm_pdf = self.tmpdir / "tcm.pdf"
        # Both tasks are in the index: if the decoy sheet were read, the handler
        # would happily emit 27-002-00.pdf rather than skipping a missing task.
        pdf = fitz.open()
        for code in (self.expected_task, self.decoy_task):
            page = pdf.new_page(width=612, height=792)
            page.insert_text((72, 72), f"TASK {code}\nPAGE FOR {code}", fontsize=12)
        pdf.save(self.tcm_pdf)
        pdf.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_fixture_is_a_real_binary_workbook(self):
        """Pins the container format the storage allowlist relies on."""

        import zipfile

        with self.fixture.open("rb") as handle:
            self.assertEqual(handle.read(4), b"PK\x03\x04", "an .xlsb is an OPC/ZIP package")
        with zipfile.ZipFile(self.fixture) as package:
            names = package.namelist()
        self.assertIn("xl/workbook.bin", names, f"not a BIFF12 workbook: {names}")

    def test_toolkit_reader_prefers_the_mpd_rsd_sheet(self):
        from worker.toolkit import read_mpd_rsd_frame

        frame = read_mpd_rsd_frame(str(self.fixture))
        self.assertIsNotNone(frame)
        column_zero = [str(value) for value in frame.iloc[:, 0]]
        self.assertIn(self.expected_task, column_zero)
        self.assertNotIn(
            self.decoy_task,
            column_zero,
            "the first sheet is a decoy; the MPD RSD sheet must win",
        )

    def test_xlsb_is_read_end_to_end_and_matches_the_desktop(self):
        from worker import toolkit
        from worker.handlers import cmp_tcm

        desktop_tasks = toolkit.rt.RedseaApp._extract_tasks_from_excel_mpd_rsd(
            _DesktopCmpContext(toolkit), str(self.fixture), self.check_code
        )
        self.assertEqual(
            desktop_tasks,
            [self.expected_task],
            "App2 reads the .xlsb with pyxlsb and picks the MPD RSD sheet",
        )

        workdir = self.tmpdir / "web-work"
        (workdir / "out").mkdir(parents=True)
        outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(self.fixture)],
            workdir,
            lambda _progress, _message: None,
        )
        produced = sorted(Path(path).name for path in outputs)
        self.assertEqual(
            produced,
            [f"{self.expected_task}.pdf"],
            f"the .xlsb must resolve exactly as App2 does; got {produced}",
        )
        self.assertNotIn(f"{self.decoy_task}.pdf", produced)

    def test_xlsb_counts_as_an_excel_input_not_an_ignored_file(self):
        """A .xlsb used to fall outside ``excels`` and produce only a TCM index.

        With no recognised Excel the handler takes its "no Excel provided" path
        and writes ``tcm_index.json`` -- a job that "succeeded" with the wrong
        artifact and no error. This asserts the file-type split now sees it.
        """

        from worker.handlers import cmp_tcm

        workdir = self.tmpdir / "web-work-split"
        (workdir / "out").mkdir(parents=True)
        outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(self.fixture)],
            workdir,
            lambda _progress, _message: None,
        )
        self.assertNotIn(
            "tcm_index.json",
            [Path(path).name for path in outputs],
            "the .xlsb was treated as 'no Excel provided'",
        )


class TestCmpTcmSubtaskExpansion(unittest.TestCase):
    """Subtasks are numbered children of the FULL base code, not prefix siblings.

    App2's CMP/TCM button calls ``_expand_tasks_with_subtasks``
    (``app2.py:3082``): for a 3-segment base task it appends a 4th two-digit
    segment ``-01``..``-10`` to the whole code and keeps whichever the TCM index
    contains. The web handler used ``TcmIndexer.find_related_subtasks``
    (``app2.py:904``) instead, which strips the last segment and returns every
    code sharing the two-segment prefix -- ``52-020-05`` is such a sibling and is
    a different task, not a subtask of ``52-020-00``. That method has no caller
    anywhere in app2.py; it was convenient, not correct.
    """

    check_code = "A1"
    base_task = "52-020-00"
    subtasks = ("52-020-00-01", "52-020-00-03")
    # Shares only the two-segment prefix "52-020-". find_related_subtasks
    # matches it; the -01..-10 rule cannot.
    prefix_sibling = "52-020-05"

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cmp_tcm_subtasks_"))
        self.tcm_pdf = self.tmpdir / "tcm.pdf"
        self.excel = self.tmpdir / "mpd-rsd.xlsx"
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)

        # One code per page: TASK_PATTERN is greedy on the optional 4th segment,
        # so a page holding "52-020-00-01" never indexes a bare "52-020-00".
        pdf = fitz.open()
        for code in (self.base_task, *self.subtasks, self.prefix_sibling):
            page = pdf.new_page(width=612, height=792)
            page.insert_text((72, 72), f"TASK {code}\nPAGE FOR {code}", fontsize=12)
        pdf.save(self.tcm_pdf)
        pdf.close()

        columns = [f"COL_{index}" for index in range(25)]
        section = [""] * 25
        section[0] = "CMPISS03 R1"
        row = [""] * 25
        row[0] = self.base_task
        row[24] = self.check_code
        pd.DataFrame([section, row], columns=columns).to_excel(self.excel, index=False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_numeric_suffix_subtasks_are_expanded_and_siblings_are_not(self):
        from worker.handlers import cmp_tcm

        web_outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(self.excel)],
            self.workdir,
            lambda _progress, _message: None,
        )
        produced = sorted(Path(path).name for path in web_outputs)

        self.assertEqual(
            produced,
            sorted(f"{code}.pdf" for code in (self.base_task, *self.subtasks)),
            f"expected the base task plus its -01/-03 children only; got {produced}",
        )
        self.assertNotIn(
            f"{self.prefix_sibling}.pdf",
            produced,
            f"{self.prefix_sibling} shares only the two-segment prefix of "
            f"{self.base_task}; find_related_subtasks' semantics, not App2's",
        )

    def test_expansion_matches_the_desktop_method_exactly(self):
        from worker import toolkit
        from worker.handlers import cmp_tcm

        tcm_dir = self.tmpdir / "desktop-tcm"
        tcm_dir.mkdir()
        shutil.copy2(self.tcm_pdf, tcm_dir / self.tcm_pdf.name)
        indexer = toolkit.TcmIndexer(str(tcm_dir), threads=1, cache=False)
        indexer.build_index()

        desktop_expanded = toolkit.rt.RedseaApp._expand_tasks_with_subtasks(
            _DesktopCmpContext(toolkit), [self.base_task], indexer
        )
        self.assertEqual(
            sorted(desktop_expanded),
            sorted([self.base_task, *self.subtasks]),
            "App2 itself expands to the -01/-03 children and nothing else",
        )

        web_outputs = cmp_tcm(
            {"input_refs": {"check": self.check_code}},
            [str(self.tcm_pdf), str(self.excel)],
            self.workdir,
            lambda _progress, _message: None,
        )
        self.assertEqual(
            sorted(Path(path).name for path in web_outputs),
            sorted(f"{code}.pdf" for code in desktop_expanded),
        )


class TestCmpTcmCheckHierarchy(unittest.TestCase):
    """A selected check pulls the tasks of every check it includes.

    ``CHECK_RELATIONS["C4"] == ["C1", "C2", "C4"]`` and
    ``_generate_task_cards_indexed`` expands the selection *before* reading the
    Excel (``app2.py:3471``), so a C4 job must also emit the tasks tagged C1 and
    C2. The relation is one-directional -- ``CHECK_RELATIONS["C1"] == ["C1"]`` --
    so C1 must not reach back for C4's tasks.
    """

    # task code -> check code in column 24.
    rows = {
        "32-010-00": "C1",
        "32-020-00": "C2",
        "32-030-00": "C4",
        "32-040-00": "C3",  # C3 is NOT part of C4's expansion.
    }

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cmp_tcm_hierarchy_"))
        self.tcm_pdf = self.tmpdir / "tcm.pdf"
        self.excel = self.tmpdir / "mpd-rsd.xlsx"

        pdf = fitz.open()
        for task_code in self.rows:
            page = pdf.new_page(width=612, height=792)
            page.insert_text((72, 72), f"TASK {task_code}\nPAGE FOR {task_code}", fontsize=12)
        pdf.save(self.tcm_pdf)
        pdf.close()

        columns = [f"COL_{index}" for index in range(25)]
        section = [""] * 25
        section[0] = "CMPISS03 R1"
        table = [section]
        for task_code, check_code in self.rows.items():
            row = [""] * 25
            row[0] = task_code
            row[24] = check_code
            table.append(row)
        pd.DataFrame(table, columns=columns).to_excel(self.excel, index=False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, check_code: str) -> list[str]:
        from worker.handlers import cmp_tcm

        workdir = self.tmpdir / f"web-work-{check_code}"
        (workdir / "out").mkdir(parents=True)
        outputs = cmp_tcm(
            {"input_refs": {"check": check_code}},
            [str(self.tcm_pdf), str(self.excel)],
            workdir,
            lambda _progress, _message: None,
        )
        return sorted(Path(path).name for path in outputs)

    def test_check_relations_asymmetry_is_real(self):
        from worker.toolkit import CHECK_RELATIONS, expand_check

        self.assertEqual(CHECK_RELATIONS["C4"], ["C1", "C2", "C4"])
        self.assertEqual(CHECK_RELATIONS["C1"], ["C1"])
        self.assertEqual(expand_check("C4"), ["C1", "C2", "C4"])
        self.assertEqual(expand_check("C1"), ["C1"])

    def test_selected_check_pulls_every_included_check(self):
        produced = self._run("C4")
        self.assertEqual(
            produced,
            ["32-010-00.pdf", "32-020-00.pdf", "32-030-00.pdf"],
            f"C4 includes C1 and C2, so all three tasks must be generated; got {produced}",
        )
        self.assertNotIn(
            "32-040-00.pdf",
            produced,
            "C3 is not part of C4's expansion",
        )

    def test_expansion_is_one_directional(self):
        produced = self._run("C1")
        self.assertEqual(
            produced,
            ["32-010-00.pdf"],
            f"C1 expands to itself only; got {produced}",
        )

    def test_tasks_shared_by_two_associated_checks_are_emitted_once(self):
        """One PDF per task, not per (check, task) pair.

        The desktop writes the same task once per check folder; the flat web
        output has no folders, so the task set is deduped across the expansion.
        Nothing is lost -- the per-folder copies are byte-identical.
        """

        from worker.handlers import cmp_tcm

        excel = self.tmpdir / "mpd-rsd-shared.xlsx"
        columns = [f"COL_{index}" for index in range(25)]
        section = [""] * 25
        section[0] = "CMPISS03 R1"
        table = [section]
        # The same task tagged for two checks inside C4's expansion.
        for check_code in ("C1", "C2"):
            row = [""] * 25
            row[0] = "32-010-00"
            row[24] = check_code
            table.append(row)
        pd.DataFrame(table, columns=columns).to_excel(excel, index=False)

        workdir = self.tmpdir / "web-work-shared"
        (workdir / "out").mkdir(parents=True)
        outputs = cmp_tcm(
            {"input_refs": {"check": "C4"}},
            [str(self.tcm_pdf), str(excel)],
            workdir,
            lambda _progress, _message: None,
        )
        self.assertEqual([Path(path).name for path in outputs], ["32-010-00.pdf"])


if __name__ == "__main__":
    unittest.main()