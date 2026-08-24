import shutil
import tempfile
import unittest
from pathlib import Path

import fitz


class TestCoverMerge(unittest.TestCase):
    """`cover_merge` has no app2.py equivalent -- ``_find_cover_for_task``
    (app2.py:3555) is the only cover-related code in the desktop app, and it
    is dead: ``self.covers_dir`` is set to ``None`` at init and never assigned
    by any picker in `_tab_cmp_tcm_tasks`, so the cover-merge step inside
    `_generate_task_cards_indexed` never actually attaches a cover in
    practice. `cover_merge` is a standalone web feature (plain PDF
    concatenation, first file treated as the cover) with no desktop parity
    target -- these tests pin its own documented contract instead.
    """

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cover_merge_"))
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_pdf(self, name: str, texts: list[str]) -> Path:
        path = self.tmpdir / name
        doc = fitz.open()
        for text in texts:
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 72), text, fontsize=12)
        doc.save(path)
        doc.close()
        return path

    def test_cover_and_card_are_merged_in_order(self):
        from worker.handlers import cover_merge

        cover = self._make_pdf("cover.pdf", ["COVER PAGE"])
        card = self._make_pdf("card.pdf", ["CARD PAGE ONE", "CARD PAGE TWO"])

        outputs = cover_merge(
            {}, [str(cover), str(card)], self.workdir, lambda *_args: None
        )
        self.assertEqual(len(outputs), 1)
        merged = fitz.open(outputs[0])
        try:
            self.assertEqual(merged.page_count, 3)
            self.assertIn("COVER PAGE", merged[0].get_text())
            self.assertIn("CARD PAGE ONE", merged[1].get_text())
            self.assertIn("CARD PAGE TWO", merged[2].get_text())
        finally:
            merged.close()

    def test_merge_order_follows_input_order_not_filename(self):
        """Ordering is purely positional -- whichever file is first in
        ``input_files`` becomes the cover, regardless of name. The frontend
        (`cover-merge.tsx`) has no explicit cover-designation control, so the
        selection order the caller provides is authoritative; this test pins
        that so a future "helpful" sort-by-name change doesn't silently swap
        the cover to the back.
        """

        from worker.handlers import cover_merge

        # Name that would sort BEFORE "aaa_cover.pdf" alphabetically, to prove
        # the handler does not resort by filename.
        first = self._make_pdf("zzz_should_be_first.pdf", ["FIRST IN LIST"])
        second = self._make_pdf("aaa_should_be_second.pdf", ["SECOND IN LIST"])

        outputs = cover_merge(
            {}, [str(first), str(second)], self.workdir, lambda *_args: None
        )
        merged = fitz.open(outputs[0])
        try:
            self.assertEqual(merged.page_count, 2)
            self.assertIn("FIRST IN LIST", merged[0].get_text())
            self.assertIn("SECOND IN LIST", merged[1].get_text())
        finally:
            merged.close()

    def test_more_than_two_files_all_merge_in_order(self):
        from worker.handlers import cover_merge

        paths = [self._make_pdf(f"p{i}.pdf", [f"PAGE {i}"]) for i in range(4)]

        outputs = cover_merge(
            {}, [str(p) for p in paths], self.workdir, lambda *_args: None
        )
        merged = fitz.open(outputs[0])
        try:
            self.assertEqual(merged.page_count, 4)
            for i in range(4):
                self.assertIn(f"PAGE {i}", merged[i].get_text())
        finally:
            merged.close()

    def test_fewer_than_two_files_raises(self):
        from worker.handlers import cover_merge

        only = self._make_pdf("only.pdf", ["ONLY PAGE"])
        with self.assertRaisesRegex(ValueError, "at least 2 PDFs"):
            cover_merge({}, [str(only)], self.workdir, lambda *_args: None)

    def test_zero_files_raises_from_the_guard_not_from_pymupdf(self):
        """The message matters, not just the exception type.

        A bare `assertRaises(ValueError)` here passes even with the guard
        removed, because PyMuPDF then raises its own ValueError ("cannot save
        with zero pages") further down. That pins PyMuPDF's behaviour rather
        than this handler's contract, so match the guard's own wording.
        """

        from worker.handlers import cover_merge

        with self.assertRaisesRegex(ValueError, "at least 2 PDFs"):
            cover_merge({}, [], self.workdir, lambda *_args: None)


if __name__ == "__main__":
    unittest.main()
