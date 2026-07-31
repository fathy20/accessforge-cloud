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

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cmp_tcm_parity_"))
        self.tcm_pdf = self.tmpdir / "tcm.pdf"
        self.excel = self.tmpdir / "mpd-rsd.xlsx"
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)
        pdf = fitz.open()
        for text in (
            "TARGET TASK 27-001-00\nORIGINAL TARGET PAGE",
            "OTHER TASK 27-002-00\nORIGINAL OTHER PAGE",
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


if __name__ == "__main__":
    unittest.main()