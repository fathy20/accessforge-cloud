import inspect
import re
import shutil
import tempfile
import types
import unittest
from pathlib import Path

import fitz


# The two literals `_stamp_process_single_pdf` (app2.py:1912 /
# redsea_toolkit.py:1994) drives its detection with. Transcribed here on purpose
# so `test_desktop_detection_source_is_unchanged` can assert they still appear
# verbatim in the preserved desktop source — if the desktop rules ever change,
# that guard fails instead of the port silently drifting.
DESKTOP_TASK_PATTERN = r"(\d{2,3}-\d{3}-\d{2}-\d{2})"
DESKTOP_COVER_SCAN_LIMIT = "if i > 4: break"


class _DesktopStampContext:
    tx_stamp_log = None

    def _safe_log(self, *_args):
        pass


class _DesktopSplitContext(_DesktopStampContext):
    """Stand-in ``self`` for ``_stamp_process_single_pdf``.

    That method reaches for ``self.TAIL_MAP``, ``self._stamp_extract_text_with_ocr``
    and ``self._stamp_page_data`` on top of the logging attributes, and it swallows
    every exception into ``_safe_log`` — so a missing attribute would silently
    produce an unstamped file instead of an error. Bind the real class members so
    the ground-truth run is genuinely the desktop's.
    """

    def __init__(self):
        from worker import toolkit

        real = toolkit.rt.RedseaApp
        self.TAIL_MAP = real.TAIL_MAP
        self._stamp_extract_text_with_ocr = types.MethodType(
            real._stamp_extract_text_with_ocr, self
        )
        self._stamp_page_data = types.MethodType(real._stamp_page_data, self)


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


def _all_spans(pdf_path):
    """Every span in the document as (page, text, x, y) — the full stamp inventory.

    Desktop and web must agree on this list exactly; it catches both a missing
    stamp and an extra one (e.g. a placeholder stamped where desktop skips).
    """
    doc = fitz.open(pdf_path)
    try:
        spans = []
        for page_number, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        spans.append(
                            (
                                page_number,
                                span["text"],
                                round(span["origin"][0], 2),
                                round(span["origin"][1], 2),
                            )
                        )
        return sorted(spans)
    finally:
        doc.close()


def _run_desktop(source, destination, tail, station, date):
    """Ground truth: RedseaApp._stamp_page_data against a copy of the fixture."""
    from worker import toolkit

    doc = fitz.open(source)
    toolkit.rt.RedseaApp._stamp_page_data(_DesktopStampContext(), doc, tail, station, date)
    doc.save(destination, deflate=True)
    doc.close()
    return Path(destination)


def _run_desktop_single_pdf(source, work_folder, station, date):
    """Ground truth: RedseaApp._stamp_process_single_pdf over a copy of the fixture.

    The desktop method rewrites its *input* in place, so the fixture is copied into
    ``work_folder`` first and the copy is what gets stamped.

    Where the FIRST task's extract lands is platform-dependent, because the method
    calls ``os.replace(temp_file, input_file)`` while ``doc`` still holds an open
    handle on ``input_file``:
      * POSIX — the rename succeeds and the extract becomes the input copy.
      * Windows — the rename raises ``[WinError 5] Access is denied``, the outer
        ``except`` swallows it, and the extract is stranded under ``temp_<name>``
        while the input copy stays untouched. (Verified in this repo; it means the
        desktop task-stamping button writes nothing at all on Windows.)
    Returns (the file holding the first task's extract, every pdf left behind).
    """
    from worker import toolkit

    work_folder.mkdir(parents=True, exist_ok=True)
    target = work_folder / Path(source).name
    shutil.copyfile(source, target)
    toolkit.rt.RedseaApp._stamp_process_single_pdf(
        _DesktopSplitContext(), str(target), str(work_folder), station, date
    )
    orphan = work_folder / f"temp_{target.name}"
    produced = orphan if orphan.exists() else target
    return produced, sorted(work_folder.glob("*.pdf"))


def _run_web(source, workdir, tail, station, date):
    """The web port: worker.handlers.task_stamping against the same fixture."""
    from worker.handlers import task_stamping

    (workdir / "out").mkdir(parents=True, exist_ok=True)
    outputs = task_stamping(
        {"input_refs": {"tail": tail, "station": station, "date": date}},
        [str(source)],
        workdir,
        lambda _progress, _message: None,
    )
    if len(outputs) != 1:
        raise AssertionError(f"expected exactly one web output, got {outputs!r}")
    return Path(outputs[0])


def _run_web_multi(source, workdir, station, date, tail=None):
    """task_stamping with the tail key omitted entirely unless one is supplied.

    Omission (not an empty string) is what the auto-detection path must react to
    in production: the frontend only sends a `tail` value the user actually typed.
    """
    from worker.handlers import task_stamping

    (workdir / "out").mkdir(parents=True, exist_ok=True)
    payload = {"station": station, "date": date}
    if tail is not None:
        payload["tail"] = tail
    outputs = task_stamping(
        {"input_refs": payload},
        [str(source)],
        workdir,
        lambda _progress, _message: None,
    )
    return [Path(p) for p in outputs]


def _stamped_texts(pdf_path):
    """Every span's text in one output, for presence/absence assertions."""
    return [span[1] for span in _all_spans(pdf_path)]


def _page_texts(pdf_path):
    doc = fitz.open(pdf_path)
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()


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
        return _text_positions(pdf_path, expected_text)

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


class TestTaskStampingBranchParity(unittest.TestCase):
    """Branches of _stamp_page_data the happy-path parity test never reaches.

    Every case runs the desktop method and the web handler over identical
    fixtures and compares the resulting span inventory exactly, so a stamp the
    web port adds or drops relative to desktop fails the test.
    """

    tail = "SU-GAA"
    station = "CAI"
    date = "2026-07-19"

    # Labels the stamper looks for; every fixture page carries all four unless a
    # case is specifically about their absence.
    LABEL_LINES = [
        (180, "TAIL NUMBER"),
        (240, "AIRLINE CARD NO"),
        (300, "STATION"),
        (360, "DATE"),
    ]

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="task_stamping_branch_"))
        self.counter = 0

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _build_pdf(self, pages, name="source.pdf"):
        """pages: list of page specs, each a list of (y, text) lines."""
        path = self.tmpdir / name
        doc = fitz.open()
        for lines in pages:
            page = doc.new_page(width=612, height=792)
            for y, text in lines:
                page.insert_text((72, y), text, fontsize=12)
        doc.save(path)
        doc.close()
        return path

    def _compare(self, source, tail=None, station=None, date=None):
        """Run both implementations over `source`; assert identical output."""
        self.counter += 1
        tail = self.tail if tail is None else tail
        station = self.station if station is None else station
        date = self.date if date is None else date

        desktop_output = self.tmpdir / f"desktop_{self.counter}.pdf"
        workdir = self.tmpdir / f"web_{self.counter}"
        _run_desktop(source, desktop_output, tail, station, date)
        web_output = _run_web(source, workdir, tail, station, date)

        desktop_spans = _all_spans(desktop_output)
        web_spans = _all_spans(web_output)
        self.assertEqual(desktop_spans, web_spans)
        return desktop_output, web_output, desktop_spans

    @staticmethod
    def _stamped_values(spans, source_spans):
        """Spans present in the output but not in the untouched source."""
        remaining = list(source_spans)
        added = []
        for span in spans:
            if span in remaining:
                remaining.remove(span)
            else:
                added.append(span)
        return [span[1] for span in added]

    # ── Case 1: Method 2 (full-page regex) fallback ──────────────────────────
    def test_method_two_regex_fallback_matches_desktop(self):
        """Tab-separated label: search_for misses it, the \\s+ regex still hits.

        PyMuPDF's search_for matches the literal glyph run, so a horizontal tab
        between the words defeats both "BOEING CARD NO." and "BOEING CARD NO".
        get_text() returns the tabs verbatim, and Method 2's r"BOEING\\s+CARD\\s+
        NO\\.?\\s*([\\d-]+)" matches them via \\s+ — a genuine Method 1 miss /
        Method 2 hit on a real fitz.Page, no stubbing needed.
        """
        source = self._build_pdf(
            [[(120, "BOEING\tCARD\tNO. 987-654-321")] + self.LABEL_LINES]
        )

        # Prove the divergence is real before asserting on it.
        probe = fitz.open(source)
        try:
            page = probe[0]
            self.assertEqual(page.search_for("BOEING CARD NO."), [])
            self.assertEqual(page.search_for("BOEING CARD NO"), [])
            self.assertRegex(page.get_text(), r"BOEING\s+CARD\s+NO\.?\s*[\d-]+")
        finally:
            probe.close()

        desktop_output, web_output, _ = self._compare(source)

        for output in (desktop_output, web_output):
            positions = _text_positions(output, ("RC987-654-321",))
            self.assertEqual(
                list(positions), ["RC987-654-321"], f"{output.name} missed the Method 2 value"
            )
            self.assertEqual(len(positions["RC987-654-321"]), 1)
        self.assertEqual(
            _text_positions(desktop_output, ("RC987-654-321",)),
            _text_positions(web_output, ("RC987-654-321",)),
        )

    def test_method_two_fallback_when_label_area_holds_no_digits(self):
        """Method 1 finds the label but the 300pt strip beside it has no number.

        found_number stays False, so Method 2 re-scans the whole page and picks
        up the number printed further down.
        """
        source = self._build_pdf(
            [
                [
                    (120, "BOEING CARD NO."),
                    (150, "BOEING CARD NO. 555-666-777"),
                ]
                + self.LABEL_LINES
            ]
        )
        desktop_output, web_output, spans = self._compare(source)
        self.assertIn("RC555-666-777", [span[1] for span in spans])
        self.assertEqual(
            _text_positions(desktop_output, ("RC555-666-777",)),
            _text_positions(web_output, ("RC555-666-777",)),
        )

    # ── Case 2: neither method finds a card number ───────────────────────────
    def test_no_boeing_card_no_stamps_literal_rc(self):
        source = self._build_pdf([[(72, "ORIGINAL CONTENT")] + self.LABEL_LINES])

        probe = fitz.open(source)
        try:
            self.assertEqual(probe[0].search_for("BOEING CARD NO"), [])
            self.assertIsNone(
                re.search(r"BOEING\s+CARD\s+NO\.?\s*([\d-]+)", probe[0].get_text(), re.IGNORECASE)
            )
        finally:
            probe.close()

        desktop_output, web_output, spans = self._compare(source)
        stamped = [span[1] for span in spans if span[1] == "RC"]
        self.assertEqual(stamped, ["RC"], "both methods failed; card number must be the literal 'RC'")
        self.assertEqual(
            _text_positions(desktop_output, ("RC",)), _text_positions(web_output, ("RC",))
        )

    # ── Case 3: no labels at all — the page must be left untouched ───────────
    def test_page_without_any_labels_is_left_untouched(self):
        source = self._build_pdf(
            [[(72, "ORIGINAL CONTENT"), (110, "Nothing here matches a stamp label.")]]
        )
        source_spans = _all_spans(source)

        desktop_output, web_output, spans = self._compare(source)
        self.assertEqual(spans, source_spans, "desktop must not touch a page with no labels")
        self.assertEqual(_all_spans(web_output), source_spans)

        source_doc, desktop_doc, web_doc = map(fitz.open, (source, desktop_output, web_output))
        try:
            self.assertEqual(source_doc[0].get_text(), desktop_doc[0].get_text())
            self.assertEqual(source_doc[0].get_text(), web_doc[0].get_text())
            self.assertEqual(source_doc[0].rect, web_doc[0].rect)
        finally:
            source_doc.close()
            desktop_doc.close()
            web_doc.close()

    # ── Case 4: multi-page, per-page card numbers must not leak ──────────────
    def test_multipage_card_numbers_stay_page_independent(self):
        source = self._build_pdf(
            [
                [(120, "BOEING CARD NO. 111-222-333")] + self.LABEL_LINES,
                [(72, "SECOND PAGE, NO CARD NUMBER")] + self.LABEL_LINES,
            ]
        )
        desktop_output, web_output, spans = self._compare(source)

        by_page = {0: set(), 1: set()}
        for page_number, text, _x, _y in spans:
            by_page[page_number].add(text)

        # Page 1 hit Method 1; page 2 found nothing and must fall back to "RC".
        self.assertIn("RC111-222-333", by_page[0])
        self.assertNotIn("RC", by_page[0], "page 1 must not also carry the 'RC' fallback")
        self.assertIn("RC", by_page[1])
        self.assertNotIn(
            "RC111-222-333", by_page[1], "page 1's card number must not leak onto page 2"
        )
        self.assertEqual(
            _text_positions(desktop_output, ("RC111-222-333", "RC")),
            _text_positions(web_output, ("RC111-222-333", "RC")),
        )

    def test_multipage_distinct_card_numbers_match_desktop(self):
        source = self._build_pdf(
            [
                [(120, "BOEING CARD NO. 111-222-333")] + self.LABEL_LINES,
                [(120, "BOEING CARD NO. 444-555-666")] + self.LABEL_LINES,
            ]
        )
        desktop_output, web_output, spans = self._compare(source)

        by_page = {0: set(), 1: set()}
        for page_number, text, _x, _y in spans:
            by_page[page_number].add(text)
        self.assertIn("RC111-222-333", by_page[0])
        self.assertNotIn("RC444-555-666", by_page[0])
        self.assertIn("RC444-555-666", by_page[1])
        self.assertNotIn("RC111-222-333", by_page[1])
        self.assertEqual(
            _text_positions(desktop_output, ("RC111-222-333", "RC444-555-666")),
            _text_positions(web_output, ("RC111-222-333", "RC444-555-666")),
        )

    # ── Case 5: empty optional fields are skipped, never stamped blank ───────
    def test_empty_station_is_skipped_not_stamped(self):
        source = self._build_pdf([[(120, "BOEING CARD NO. 123-456-789")] + self.LABEL_LINES])
        source_spans = _all_spans(source)

        desktop_output, web_output, spans = self._compare(source, station="")

        added = self._stamped_values(spans, source_spans)
        self.assertEqual(sorted(added), sorted([self.tail, "RC123-456-789", self.date]))
        self.assertNotIn("STATION", added, "an empty station must not be stamped as a placeholder")
        # The word STATION appears exactly once: the original label.
        self.assertEqual(
            len([span for span in spans if span[1] == "STATION"]),
            1,
            "the STATION label must be the only 'STATION' text on the page",
        )
        self.assertEqual(_all_spans(desktop_output), _all_spans(web_output))

    def test_empty_date_is_skipped_not_stamped(self):
        source = self._build_pdf([[(120, "BOEING CARD NO. 123-456-789")] + self.LABEL_LINES])
        source_spans = _all_spans(source)

        _desktop_output, _web_output, spans = self._compare(source, date="")

        added = self._stamped_values(spans, source_spans)
        self.assertEqual(sorted(added), sorted([self.tail, "RC123-456-789", self.station]))
        self.assertEqual(len([span for span in spans if span[1] == "DATE"]), 1)

    def test_empty_station_and_date_together_are_skipped(self):
        source = self._build_pdf([[(120, "BOEING CARD NO. 123-456-789")] + self.LABEL_LINES])
        source_spans = _all_spans(source)

        _desktop_output, _web_output, spans = self._compare(source, station="", date="")

        added = self._stamped_values(spans, source_spans)
        self.assertEqual(sorted(added), sorted([self.tail, "RC123-456-789"]))

    def test_empty_tail_is_skipped_not_stamped(self):
        source = self._build_pdf([[(120, "BOEING CARD NO. 123-456-789")] + self.LABEL_LINES])
        source_spans = _all_spans(source)

        _desktop_output, _web_output, spans = self._compare(source, tail="")

        added = self._stamped_values(spans, source_spans)
        self.assertEqual(sorted(added), sorted(["RC123-456-789", self.station, self.date]))
        self.assertNotIn("TAIL", added, "an empty tail must not be stamped as a placeholder")


class TestTaskStampingAutoDetectAndSplit(unittest.TestCase):
    """The `_stamp_process_single_pdf` half of the desktop flow (app2.py:1912).

    Cover-page tail auto-detection via TAIL_MAP, per-task splitting, and the one
    deliberate deviation: every detected task survives as its own output file
    instead of each iteration overwriting the last (desktop reuses a single
    `temp_{basename}` path and `os.replace`s it onto the input inside the loop).
    """

    station = "CAI"
    date = "2026-08-24"

    LABEL_LINES = [
        (180, "TAIL NUMBER"),
        (240, "AIRLINE CARD NO"),
        (300, "STATION"),
        (360, "DATE"),
    ]

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="task_stamping_split_"))
        self.counter = 0

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ── fixtures ─────────────────────────────────────────────────────────────
    def _build_pdf(self, pages, name="source.pdf"):
        """pages: list of page specs, each a list of (y, text) lines."""
        path = self.tmpdir / name
        doc = fitz.open()
        for lines in pages:
            page = doc.new_page(width=612, height=792)
            for y, text in lines:
                page.insert_text((72, y), text, fontsize=12)
        doc.save(path)
        doc.close()
        return path

    def _task_page(self, task_code, card_no="123-456-789", extra=()):
        lines = [(90, f"TASK {task_code}")]
        lines.extend(extra)
        lines.append((120, f"BOEING CARD NO. {card_no}"))
        lines.extend(self.LABEL_LINES)
        return lines

    def _web(self, source, tail=None):
        self.counter += 1
        return _run_web_multi(
            source,
            self.tmpdir / f"web_{self.counter}",
            self.station,
            self.date,
            tail=tail,
        )

    def _desktop(self, source):
        self.counter += 1
        return _run_desktop_single_pdf(
            source, self.tmpdir / f"desktop_{self.counter}", self.station, self.date
        )

    def _desktop_expected_extract(self, source, page_indices, tail, name):
        """What desktop *would* produce for one task if its loop did not overwrite.

        Rebuilds the task's sub-document exactly the way `_stamp_process_single_pdf`
        does (`insert_pdf(from_page=pno, to_page=pno)` per page) and stamps it with
        the real `_stamp_page_data`, so the comparison is against desktop code, not
        a transcription of it.
        """
        from worker import toolkit

        src = fitz.open(source)
        new_doc = fitz.open()
        for pno in page_indices:
            new_doc.insert_pdf(src, from_page=pno, to_page=pno)
        src.close()
        toolkit.rt.RedseaApp._stamp_page_data(
            _DesktopStampContext(), new_doc, tail, self.station, self.date
        )
        dest = self.tmpdir / name
        new_doc.save(dest, deflate=True)
        new_doc.close()
        return dest

    # ── anti-drift guards ────────────────────────────────────────────────────
    def test_desktop_detection_source_is_unchanged(self):
        """The regex and the 5-page cover window still read as transcribed here."""
        from worker import toolkit

        source = inspect.getsource(toolkit.rt.RedseaApp._stamp_process_single_pdf)
        self.assertIn(DESKTOP_TASK_PATTERN, source)
        self.assertIn(DESKTOP_COVER_SCAN_LIMIT, source)

    def test_toolkit_exports_the_desktop_tail_map_object_itself(self):
        """`toolkit.TAIL_MAP` must be the desktop dict, never a re-typed copy."""
        from worker import toolkit

        self.assertIn("TAIL_MAP", toolkit.__all__)
        self.assertIs(toolkit.TAIL_MAP, toolkit.rt.RedseaApp.TAIL_MAP)

    # ── cover-page tail auto-detection ───────────────────────────────────────
    def test_cover_plane_code_auto_detects_tail_via_tail_map(self):
        from worker import toolkit

        expected_tail = toolkit.TAIL_MAP["BTR"]
        source = self._build_pdf(
            [self._task_page("32-100-01-01", extra=[(60, "AIRCRAFT REG: BTR")])]
        )

        outputs = self._web(source)
        self.assertEqual(len(outputs), 1)
        self.assertIn(expected_tail, _stamped_texts(outputs[0]))

        # Ground truth: the real desktop method on a single-task file is correct
        # (its overwrite defect only bites from the second task onward).
        desktop_output, _files = self._desktop(source)
        self.assertEqual(_all_spans(desktop_output), _all_spans(outputs[0]))

    def test_manual_tail_overrides_cover_auto_detection(self):
        from worker import toolkit

        source = self._build_pdf(
            [self._task_page("32-100-01-01", extra=[(60, "AIRCRAFT REG: BTR")])]
        )

        outputs = self._web(source, tail="SU-MANUAL")
        self.assertEqual(len(outputs), 1)
        texts = _stamped_texts(outputs[0])
        self.assertIn("SU-MANUAL", texts)
        self.assertNotIn(
            toolkit.TAIL_MAP["BTR"],
            texts,
            "a tail typed by the user must win over the cover-page code",
        )

    def test_second_plane_code_maps_to_its_own_tail(self):
        """Not just BTR: every TAIL_MAP key resolves through the shared dict."""
        from worker import toolkit

        for code in ("ILF", "GUN", "GOT"):
            with self.subTest(code=code):
                source = self._build_pdf(
                    [self._task_page("32-100-01-01", extra=[(60, f"AIRCRAFT REG: {code}")])],
                    name=f"source_{code}.pdf",
                )
                outputs = self._web(source)
                self.assertEqual(len(outputs), 1)
                self.assertIn(toolkit.TAIL_MAP[code], _stamped_texts(outputs[0]))

    def test_no_plane_code_and_no_manual_tail_leaves_tail_unstamped(self):
        """Deliberate deviation, owner-approved.

        Desktop skips `_stamp_page_data` entirely when no plane code is found, so
        the card number, station and date go unstamped too. The web port keeps the
        already-shipped "falsy value is skipped" rule instead: only TAIL NUMBER is
        left alone, and never with a placeholder.
        """
        from worker import toolkit

        source = self._build_pdf([self._task_page("32-100-01-01")])

        outputs = self._web(source)
        self.assertEqual(len(outputs), 1)
        texts = _stamped_texts(outputs[0])
        for tail_value in toolkit.TAIL_MAP.values():
            self.assertNotIn(tail_value, texts)
        self.assertEqual(
            texts.count("TAIL NUMBER"),
            1,
            "the TAIL NUMBER label must be the only 'TAIL NUMBER' text on the page",
        )
        self.assertNotIn("TAIL", texts, "no placeholder may be invented for an unknown tail")
        # The other three fields are still stamped.
        self.assertIn("RC123-456-789", texts)
        self.assertIn(self.station, texts)
        self.assertIn(self.date, texts)

        # Pin the divergence itself: desktop stamps nothing at all here.
        desktop_output, _files = self._desktop(source)
        desktop_texts = _stamped_texts(desktop_output)
        self.assertNotIn("RC123-456-789", desktop_texts)
        self.assertNotIn(self.station, desktop_texts)

    def test_plane_code_after_the_first_five_pages_is_not_detected(self):
        """`if i > 4: break` — the cover scan sees pages 0-4 only."""
        from worker import toolkit

        pages = [self._task_page("32-100-01-01") for _ in range(5)]
        pages.append(self._task_page("32-100-01-01", extra=[(60, "AIRCRAFT REG: BTR")]))
        source = self._build_pdf(pages)

        outputs = self._web(source)
        self.assertEqual(len(outputs), 1)
        texts = _stamped_texts(outputs[0])
        self.assertNotIn(toolkit.TAIL_MAP["BTR"], texts)
        self.assertEqual(len(_page_texts(outputs[0])), 6)

    def test_plane_code_on_the_fifth_page_is_still_detected(self):
        """Boundary companion: page index 4 is inside the window."""
        from worker import toolkit

        pages = [self._task_page("32-100-01-01") for _ in range(4)]
        pages.append(self._task_page("32-100-01-01", extra=[(60, "AIRCRAFT REG: BTR")]))
        source = self._build_pdf(pages)

        outputs = self._web(source)
        self.assertEqual(len(outputs), 1)
        self.assertIn(toolkit.TAIL_MAP["BTR"], _stamped_texts(outputs[0]))

    # ── per-task splitting: every task must survive ──────────────────────────
    def test_multi_task_pdf_produces_one_surviving_output_per_task(self):
        """THE bug being fixed: desktop keeps only the last task, the port keeps all."""
        from worker import toolkit

        source = self._build_pdf(
            [
                self._task_page("32-100-01-01", extra=[(60, "AIRCRAFT REG: BTR")]),
                self._task_page("52-200-02-03", card_no="444-555-666"),
            ]
        )

        outputs = self._web(source)
        self.assertEqual(
            len(outputs), 2, "one output per detected task — none may be overwritten"
        )
        self.assertEqual(len({p.name for p in outputs}), 2, "output names must not collide")
        for path in outputs:
            self.assertTrue(path.exists(), f"{path.name} was overwritten or never written")
            self.assertIn(Path(source).stem, path.name, "output must trace back to its source")

        by_task = {}
        for path in outputs:
            pages = _page_texts(path)
            self.assertEqual(len(pages), 1)
            codes = re.findall(DESKTOP_TASK_PATTERN, pages[0])
            by_task[codes[0]] = path
        self.assertEqual(set(by_task), {"32-100-01-01", "52-200-02-03"})
        for task_code, path in by_task.items():
            self.assertIn(task_code, path.name, "the task code must be in the filename")

        # Both extracts carry the cover-detected tail, and each matches what the
        # desktop stamper produces for that task's pages.
        expected_tail = toolkit.TAIL_MAP["BTR"]
        self.assertEqual(
            _all_spans(
                self._desktop_expected_extract(source, [0], expected_tail, "exp_a.pdf")
            ),
            _all_spans(by_task["32-100-01-01"]),
        )
        self.assertEqual(
            _all_spans(
                self._desktop_expected_extract(source, [1], expected_tail, "exp_b.pdf")
            ),
            _all_spans(by_task["52-200-02-03"]),
        )

        # And prove the defect the port is correcting is real in the desktop code:
        # whatever desktop leaves behind, it is never both task extracts. (POSIX:
        # one file, the last task, the first silently overwritten. Windows: the
        # os.replace onto the still-open input is denied, so only the stranded
        # temp_ file carries an extract and nothing is written where it belongs.)
        _desktop_output, desktop_files = self._desktop(source)
        desktop_extracts = {}
        for path in desktop_files:
            pages = _page_texts(path)
            if len(pages) != 1:
                continue
            match = re.search(DESKTOP_TASK_PATTERN, pages[0])
            if match:
                desktop_extracts[match.group(1)] = path
        self.assertLess(
            len(desktop_extracts),
            2,
            "desktop cannot keep both task extracts — that is the bug being fixed",
        )

    def test_task_pages_group_by_membership_not_contiguity(self):
        """Grouping is `tasks[code]["pages"].append(i)` — no contiguity requirement."""
        source = self._build_pdf(
            [
                self._task_page("32-100-01-01", card_no="111-222-333"),
                self._task_page("52-200-02-03", card_no="444-555-666"),
                self._task_page("32-100-01-01", card_no="777-888-999"),
            ]
        )

        outputs = self._web(source, tail="SU-MANUAL")
        self.assertEqual(len(outputs), 2)
        by_name = {p.name: p for p in outputs}
        split = next(p for n, p in by_name.items() if "32-100-01-01" in n)
        single = next(p for n, p in by_name.items() if "52-200-02-03" in n)

        split_pages = _page_texts(split)
        self.assertEqual(len(split_pages), 2, "source pages 0 and 2 belong to one task")
        # Ascending source order, and the intervening page is excluded.
        self.assertIn("111-222-333", split_pages[0])
        self.assertIn("777-888-999", split_pages[1])
        for page_text in split_pages:
            self.assertNotIn("52-200-02-03", page_text)
        self.assertEqual(len(_page_texts(single)), 1)

        expected = self._desktop_expected_extract(source, [0, 2], "SU-MANUAL", "exp.pdf")
        self.assertEqual(_all_spans(expected), _all_spans(split))

    def test_page_with_two_task_codes_joins_only_the_first_match(self):
        """`re.search`, not `finditer`: a page belongs to its first code only."""
        source = self._build_pdf(
            [
                [
                    (90, "TASK 32-100-01-01"),
                    (105, "SUPERSEDES 52-200-02-03"),
                    (120, "BOEING CARD NO. 123-456-789"),
                ]
                + self.LABEL_LINES
            ]
        )

        # Derive the winner from the real page text rather than assuming layout order.
        page_text = _page_texts(source)[0]
        expected_code = re.search(DESKTOP_TASK_PATTERN, page_text).group(1)
        other_code = next(
            code
            for code in re.findall(DESKTOP_TASK_PATTERN, page_text)
            if code != expected_code
        )

        outputs = self._web(source, tail="SU-MANUAL")
        self.assertEqual(len(outputs), 1, "the second code on the page must not create a task")
        self.assertIn(expected_code, outputs[0].name)
        self.assertNotIn(other_code, outputs[0].name)

    def test_pages_without_task_codes_are_excluded_from_split_outputs(self):
        """Desktop behaviour preserved: only pages carrying a code are extracted."""
        source = self._build_pdf(
            [
                [(90, "COVER SHEET, NO TASK CODE HERE")] + self.LABEL_LINES,
                self._task_page("32-100-01-01"),
            ]
        )

        outputs = self._web(source, tail="SU-MANUAL")
        self.assertEqual(len(outputs), 1)
        pages = _page_texts(outputs[0])
        self.assertEqual(len(pages), 1)
        self.assertNotIn("COVER SHEET", pages[0])

    # ── whole-document fallback when nothing is detected ─────────────────────
    def test_no_task_codes_anywhere_falls_back_to_whole_document(self):
        source = self._build_pdf(
            [
                [(120, "BOEING CARD NO. 111-222-333")] + self.LABEL_LINES,
                [(120, "BOEING CARD NO. 444-555-666")] + self.LABEL_LINES,
            ]
        )

        outputs = self._web(source, tail="SU-MANUAL")
        self.assertEqual(len(outputs), 1, "no task codes must not mean no output")
        self.assertEqual(outputs[0].name, f"STAMPED_{Path(source).name}")
        pages = _page_texts(outputs[0])
        self.assertEqual(len(pages), 2, "the whole document is stamped as one unit")
        texts = _stamped_texts(outputs[0])
        self.assertIn("SU-MANUAL", texts)
        self.assertIn("RC111-222-333", texts)
        self.assertIn("RC444-555-666", texts)

        expected = _run_desktop(
            source, self.tmpdir / "desktop_whole.pdf", "SU-MANUAL", self.station, self.date
        )
        self.assertEqual(_all_spans(expected), _all_spans(outputs[0]))

    def test_fallback_still_auto_detects_the_tail(self):
        """No tasks, no manual tail — the cover code still resolves the tail."""
        from worker import toolkit

        source = self._build_pdf(
            [
                [(60, "AIRCRAFT REG: GUN"), (120, "BOEING CARD NO. 111-222-333")]
                + self.LABEL_LINES
            ]
        )

        outputs = self._web(source)
        self.assertEqual(len(outputs), 1)
        self.assertIn(toolkit.TAIL_MAP["GUN"], _stamped_texts(outputs[0]))


if __name__ == "__main__":
    unittest.main()
