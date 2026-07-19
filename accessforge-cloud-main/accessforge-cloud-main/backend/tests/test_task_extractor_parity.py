import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _ImmediateThread:
    def __init__(self, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


class _DesktopExtractorContext:
    tx_task_log = None

    def __init__(self, toolkit, source_dir, output_dir, task_code):
        self.selected_pdf_folder = str(source_dir)
        self.output_dir = str(output_dir)
        self.task_entry = _Value(task_code)
        self.skip_first_var = _Value(False)
        self.combine_var = _Value(True)
        self._toolkit = toolkit

    def _safe_log(self, *_args):
        pass

    def _safe_show_error(self, *_args):
        raise AssertionError("Desktop extraction reported an error")

    def _safe_show_info(self, *_args):
        pass

    def _is_index_page(self, text):
        return self._toolkit.rt.RedseaApp._is_index_page(self, text)

    def _scan_pages_for_code_parallel(self, doc, code, max_workers=3):
        return self._toolkit.rt.RedseaApp._scan_pages_for_code_parallel(self, doc, code, max_workers)

    def _find_related_tasks(self, code, pdf_path=None):
        return self._toolkit.rt.RedseaApp._find_related_tasks(self, code, pdf_path)


class TestTaskExtractorParity(unittest.TestCase):
    task_code = "27-001-00"

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="task_extractor_parity_"))
        self.source_dir = self.tmpdir / "source"
        self.desktop_dir = self.tmpdir / "desktop"
        self.web_workdir = self.tmpdir / "web-work"
        self.source_dir.mkdir()
        self.desktop_dir.mkdir()
        (self.web_workdir / "out").mkdir(parents=True)
        self.source = self.source_dir / "27_tasks.pdf"

        doc = fitz.open()
        for text in (
            "ORIGINAL PAGE ONE\nTASK 27-001-00",
            "ORIGINAL PAGE TWO\nTASK 27-002-00",
            "ORIGINAL PAGE THREE\nUNRELATED CONTENT",
        ):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), text, fontsize=12)
        doc.save(self.source)
        doc.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_machine_readable_task_extraction_matches_desktop(self):
        from worker import toolkit
        from worker.handlers import task_extractor

        desktop = _DesktopExtractorContext(toolkit, self.source_dir, self.desktop_dir, self.task_code)
        with mock.patch.object(toolkit.rt.threading, "Thread", _ImmediateThread):
            toolkit.rt.RedseaApp._run_extract(desktop)

        desktop_output = self.desktop_dir / f"{self.task_code}_extracted.pdf"
        self.assertTrue(desktop_output.exists())

        web_outputs = task_extractor(
            {"input_refs": {"task_code": self.task_code}},
            [str(self.source)],
            self.web_workdir,
            lambda _progress, _message: None,
        )
        self.assertEqual(len(web_outputs), 1)
        web_output = Path(web_outputs[0])
        self.assertEqual(web_output.name, desktop_output.name)

        desktop_doc = fitz.open(desktop_output)
        web_doc = fitz.open(web_output)
        try:
            self.assertEqual(desktop_doc.page_count, 1)
            self.assertEqual(desktop_doc.page_count, web_doc.page_count)
            self.assertEqual(desktop_doc[0].rect, web_doc[0].rect)
            self.assertEqual(desktop_doc[0].get_text(), web_doc[0].get_text())
            self.assertIn(self.task_code, web_doc[0].get_text())
            self.assertIn("ORIGINAL PAGE ONE", web_doc[0].get_text())
            self.assertNotIn("ORIGINAL PAGE TWO", web_doc[0].get_text())
        finally:
            desktop_doc.close()
            web_doc.close()


if __name__ == "__main__":
    unittest.main()