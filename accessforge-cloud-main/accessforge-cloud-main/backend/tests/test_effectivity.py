import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class TestEffectivity(unittest.TestCase):
    """`effectivity`'s desktop counterpart (`_tab_effectivity` /
    `_load_excel_generic`, app2.py:2122-2168) is an "Under Development" stub
    -- it only shows a messagebox and never reads a file. There is no app2
    ground truth for this handler's actual behavior; it is an original web
    feature. These tests pin its own documented contract instead of a
    desktop comparison.
    """

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="effectivity_"))
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_excel_headers_are_stripped_and_rows_preserved(self):
        from worker.handlers import effectivity

        src = self.tmpdir / "raw.xlsx"
        pd.DataFrame({" MPD ": ["27-001-00"], "TITLE ": ["Some title"]}).to_excel(src, index=False)

        outputs = effectivity({}, [str(src)], self.workdir, lambda *_args: None)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(Path(outputs[0]).name, "EFFECTIVITY_raw.xlsx")

        out_df = pd.read_excel(outputs[0])
        self.assertEqual(list(out_df.columns), ["MPD", "TITLE"])
        self.assertEqual(out_df.iloc[0]["MPD"], "27-001-00")

    def test_csv_input_is_accepted(self):
        from worker.handlers import effectivity

        src = self.tmpdir / "raw.csv"
        pd.DataFrame({"A": [1, 2], "B": [3, 4]}).to_csv(src, index=False)

        outputs = effectivity({}, [str(src)], self.workdir, lambda *_args: None)
        out_df = pd.read_excel(outputs[0])
        self.assertEqual(len(out_df), 2)

    def test_multiple_input_files_each_produce_their_own_output(self):
        from worker.handlers import effectivity

        first = self.tmpdir / "one.xlsx"
        second = self.tmpdir / "two.xlsx"
        pd.DataFrame({"X": [1]}).to_excel(first, index=False)
        pd.DataFrame({"Y": [2]}).to_excel(second, index=False)

        outputs = effectivity({}, [str(first), str(second)], self.workdir, lambda *_args: None)
        names = sorted(Path(p).name for p in outputs)
        self.assertEqual(names, ["EFFECTIVITY_one.xlsx", "EFFECTIVITY_two.xlsx"])

    def test_db_data_source_raises_not_implemented(self):
        from worker.handlers import effectivity

        with self.assertRaises(NotImplementedError):
            effectivity(
                {"input_refs": {"data_source": "db"}},
                [],
                self.workdir,
                lambda *_args: None,
            )


if __name__ == "__main__":
    unittest.main()
