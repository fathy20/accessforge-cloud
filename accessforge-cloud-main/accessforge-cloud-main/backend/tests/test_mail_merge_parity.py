import re
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from docx import Document


# Unicode LTR-embedding pair app2.py wraps dash-digit codes in so an RTL (Arabic)
# rendering context does not display 53-844-00 as 00-844-53.
LRE = "\u202A"
PDF = "\u202C"


def desktop_context(row: dict) -> dict:
    """Rebuild _mm_generate_document's context block (app2.py:4139-4155) verbatim.

    Every parity assertion below compares the web handler against a context built
    exactly the way the desktop "Generate Document" button builds it: LTR-embedded
    dash-digit codes plus a normalized-key alias per column.
    """
    context: dict[str, str] = {}
    for col, value in row.items():
        val_str = str(value).strip() if pd.notnull(value) and value != "" else ""
        if re.search(r"\d+-\d+", val_str):
            val_str = f"{LRE}{val_str}{PDF}"
        context[col] = val_str
        normalized = re.sub(r"[^A-Z0-9_]", "", str(col).upper())
        if normalized != str(col).upper():
            context[normalized] = val_str
    return context


class TestMailMergeParity(unittest.TestCase):
    mpd = "27-001-00"
    title = "Deterministic RC card"

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="mail_merge_parity_"))
        self.template = self.tmpdir / "template.docx"
        self.data = self.tmpdir / "data.xlsx"
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)

        document = Document()
        document.add_paragraph("RC title: «TITLE»")
        document.add_paragraph("Unrelated template content")
        document.save(self.template)
        pd.DataFrame([{"MPD": self.mpd, "TITLE": self.title}]).to_excel(self.data, index=False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_one_row_guillemet_rendering_matches_desktop(self):
        from worker import toolkit
        from worker.handlers import mail_merge

        desktop = Document(self.template)
        toolkit.rt.RedseaApp._mm_manual_replace(object(), desktop, {"TITLE": self.title})
        desktop_text = [paragraph.text for paragraph in desktop.paragraphs]

        web_outputs = mail_merge({}, [str(self.template), str(self.data)], self.workdir, lambda *_args: None)
        self.assertEqual(len(web_outputs), 1)
        web_output = Path(web_outputs[0])
        self.assertEqual(web_output.name, f"RC_Card_{self.mpd}.docx")

        web = Document(web_output)
        self.assertEqual([paragraph.text for paragraph in web.paragraphs], desktop_text)
        self.assertEqual(web.paragraphs[0].text, f"RC title: {self.title}")
        self.assertEqual(web.paragraphs[1].text, "Unrelated template content")

        self.assertNotIn("«TITLE»", web.paragraphs[0].text)

    # ── helpers for the run-splitting / context-building parity cases ────────

    def _save_template(self, document):
        document.save(self.template)

    def _write_rows(self, rows):
        pd.DataFrame(rows).to_excel(self.data, index=False)

    def _run_web(self):
        from worker.handlers import mail_merge

        outputs = mail_merge({}, [str(self.template), str(self.data)], self.workdir, lambda *_args: None)
        self.assertEqual(len(outputs), 1)
        return [paragraph.text for paragraph in Document(outputs[0]).paragraphs]

    def _run_desktop(self, row):
        """Run the real desktop replacement over an identical copy of the fixture."""
        from worker import toolkit

        desktop = Document(self.template)
        toolkit.rt.RedseaApp._mm_manual_replace(object(), desktop, desktop_context(row))
        return [paragraph.text for paragraph in desktop.paragraphs]

    # ── the three gaps ───────────────────────────────────────────────────────

    def test_placeholder_split_across_runs_matches_desktop(self):
        """A «TITLE» Word splits over three runs must still merge.

        _mm_manual_replace looks at paragraph.text (all runs concatenated), so the
        desktop replaces this. A run-by-run web handler sees only "«TIT", "LE»" and
        matches neither, silently shipping the placeholder into the output.
        """
        document = Document()
        paragraph = document.add_paragraph()
        paragraph.add_run("RC title: «TIT")
        paragraph.add_run("LE")
        paragraph.add_run("»")
        document.add_paragraph("Unrelated template content")
        self._save_template(document)

        # Guard the fixture itself: if python-docx ever coalesced these runs the
        # test would silently stop exercising the bug.
        self.assertGreater(len(Document(self.template).paragraphs[0].runs), 1)

        row = {"MPD": self.mpd, "TITLE": self.title}
        self._write_rows([row])

        desktop_text = self._run_desktop(row)
        self.assertEqual(desktop_text[0], f"RC title: {self.title}")

        self.assertEqual(self._run_web(), desktop_text)

    def test_split_placeholder_in_table_cell_matches_desktop(self):
        document = Document()
        table = document.add_table(rows=1, cols=1)
        cell_paragraph = table.cell(0, 0).paragraphs[0]
        cell_paragraph.add_run("Title: «TIT")
        cell_paragraph.add_run("LE»")
        self._save_template(document)

        row = {"MPD": self.mpd, "TITLE": self.title}
        self._write_rows([row])

        from worker import toolkit
        from worker.handlers import mail_merge

        desktop = Document(self.template)
        toolkit.rt.RedseaApp._mm_manual_replace(object(), desktop, desktop_context(row))
        desktop_cell = desktop.tables[0].cell(0, 0).text

        outputs = mail_merge({}, [str(self.template), str(self.data)], self.workdir, lambda *_args: None)
        web_cell = Document(outputs[0]).tables[0].cell(0, 0).text

        self.assertEqual(desktop_cell, f"Title: {self.title}")
        self.assertEqual(web_cell, desktop_cell)

    def test_spaced_guillemet_variants_match_desktop(self):
        """All four spacing variants _mm_manual_replace accepts must merge."""
        document = Document()
        document.add_paragraph("A: « TITLE »")
        document.add_paragraph("B: «TITLE »")
        document.add_paragraph("C: « TITLE»")
        document.add_paragraph("D: «TITLE»")
        self._save_template(document)

        row = {"MPD": self.mpd, "TITLE": self.title}
        self._write_rows([row])

        desktop_text = self._run_desktop(row)
        self.assertEqual(
            desktop_text,
            [f"{prefix}: {self.title}" for prefix in ("A", "B", "C", "D")],
        )
        self.assertEqual(self._run_web(), desktop_text)

    def test_dash_digit_value_is_ltr_embedded_like_desktop(self):
        """53-844-00 must arrive wrapped in U+202A…U+202C (app2.py:4146-4148)."""
        document = Document()
        document.add_paragraph("Task: «TASK»")
        self._save_template(document)

        task = "53-844-00"
        row = {"MPD": self.mpd, "TASK": task}
        self._write_rows([row])

        expected = f"Task: {LRE}{task}{PDF}"
        self.assertEqual(self._run_desktop(row)[0], expected)

        web_text = self._run_web()
        self.assertEqual(web_text[0], expected)
        self.assertIn(LRE, web_text[0])
        self.assertIn(PDF, web_text[0])

    def test_non_code_value_is_not_ltr_embedded(self):
        """The wrap is conditional on \\d+-\\d+ — plain prose must stay untouched."""
        document = Document()
        document.add_paragraph("Title: «TITLE»")
        self._save_template(document)

        row = {"MPD": self.mpd, "TITLE": "Left-hand inspection"}
        self._write_rows([row])

        web_text = self._run_web()
        self.assertEqual(web_text, self._run_desktop(row))
        self.assertEqual(web_text[0], "Title: Left-hand inspection")
        self.assertNotIn(LRE, web_text[0])

    def test_normalized_key_alias_matches_desktop(self):
        """A column named "MPD Item" is also reachable as «MPDITEM» (app2.py:4153)."""
        document = Document()
        document.add_paragraph("Item: «MPDITEM»")
        document.add_paragraph("Also: «MPD Item»")
        self._save_template(document)

        row = {"MPD": self.mpd, "MPD Item": "320900"}
        self._write_rows([row])

        desktop_text = self._run_desktop(row)
        self.assertEqual(desktop_text, ["Item: 320900", "Also: 320900"])
        self.assertEqual(self._run_web(), desktop_text)


if __name__ == "__main__":
    unittest.main()
