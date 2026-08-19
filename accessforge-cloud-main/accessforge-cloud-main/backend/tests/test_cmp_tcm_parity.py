import shutil
import tempfile
import unittest
from pathlib import Path

import fitz
import pandas as pd


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
        """The fix must narrow matching, not break it: A10 and A11 still work."""

        from worker.handlers import cmp_tcm

        excel = self.tmpdir / "mpd-rsd-related.xlsx"
        self._write_mpd_rsd_excel(excel, self._all_rows())

        for related_check, related_task in self.related_checks.items():
            workdir = self.tmpdir / f"web-work-{related_check}"
            (workdir / "out").mkdir(parents=True)
            web_outputs = cmp_tcm(
                {"input_refs": {"check": related_check}},
                [str(self.tcm_pdf), str(excel)],
                workdir,
                lambda _progress, _message: None,
            )
            self.assertEqual(
                sorted(Path(path).name for path in web_outputs),
                [f"{related_task}.pdf"],
                f"check {related_check} must still resolve to its own task",
            )


if __name__ == "__main__":
    unittest.main()