import shutil
import tempfile
import unittest
from pathlib import Path

import fitz


class _DesktopStampContext:
    tx_stamp_log = None

    def _safe_log(self, *_args):
        pass


class TestTaskStampingParity(unittest.TestCase):
    tail = "SU-GAA"
    station = "CAI"
    date = "2026-07-19"
    stamp_values = (tail, "RC123-456-789", station, date)

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="task_stamping_parity_"))
        self.source = self.tmpdir / "source.pdf"
        self.desktop_output = self.tmpdir / "desktop.pdf"
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)

        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 72), "ORIGINAL CONTENT", fontsize=12)
        page.insert_text((72, 120), "BOEING CARD NO. 123-456-789", fontsize=12)
        page.insert_text((72, 180), "TAIL NUMBER", fontsize=12)
        page.insert_text((72, 240), "AIRLINE CARD NO", fontsize=12)
        page.insert_text((72, 300), "STATION", fontsize=12)
        page.insert_text((72, 360), "DATE", fontsize=12)
        doc.save(self.source)
        doc.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _text_positions(pdf_path, expected_text):
        doc = fitz.open(pdf_path)
        try:
            found = {}
            for page_number, page in enumerate(doc):
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines", []):
                        for span in line["spans"]:
                            if span["text"] in expected_text:
                                found.setdefault(span["text"], []).append(
                                    (page_number, *span["origin"])
                                )
            return found
        finally:
            doc.close()

    def test_core_page_stamping_matches_desktop(self):
        from worker import toolkit
        from worker.handlers import task_stamping

        desktop_doc = fitz.open(self.source)
        toolkit.rt.RedseaApp._stamp_page_data(
            _DesktopStampContext(), desktop_doc, self.tail, self.station, self.date
        )
        desktop_doc.save(self.desktop_output, deflate=True)
        desktop_doc.close()

        web_outputs = task_stamping(
            {"input_refs": {"tail": self.tail, "station": self.station, "date": self.date}},
            [str(self.source)],
            self.workdir,
            lambda _progress, _message: None,
        )
        self.assertEqual(len(web_outputs), 1)
        web_output = Path(web_outputs[0])

        source_doc, desktop_doc, web_doc = map(fitz.open, (self.source, self.desktop_output, web_output))
        try:
            self.assertEqual(desktop_doc.page_count, web_doc.page_count)
            self.assertEqual(source_doc.page_count, web_doc.page_count)
            self.assertEqual(source_doc[0].rect, desktop_doc[0].rect)
            self.assertIn("ORIGINAL CONTENT", desktop_doc[0].get_text())
            self.assertIn("ORIGINAL CONTENT", web_doc[0].get_text())
        finally:
            source_doc.close()
            desktop_doc.close()
            web_doc.close()

        desktop_positions = self._text_positions(self.desktop_output, self.stamp_values)
        web_positions = self._text_positions(web_output, self.stamp_values)
        self.assertEqual(set(desktop_positions), set(self.stamp_values))
        self.assertEqual(desktop_positions.keys(), web_positions.keys())
        for stamp in self.stamp_values:
            desktop_page, desktop_x, desktop_y = desktop_positions[stamp][0]
            web_page, web_x, web_y = web_positions[stamp][0]
            self.assertEqual(desktop_page, web_page)
            self.assertEqual(len(desktop_positions[stamp]), 1)
            self.assertAlmostEqual(desktop_x, web_x, delta=0.01)
            self.assertAlmostEqual(desktop_y, web_y, delta=0.01)


if __name__ == "__main__":
    unittest.main()