import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class TestUtilization(unittest.TestCase):
    """`utilization`'s desktop counterpart (`_tab_utilization` /
    `hash_function_md5`/`_sha256`/`_blake2`, app2.py:2303+/2453+) is an
    "Under Development" stub in every form -- even the hash functions the
    module name implies are unimplemented placeholders. There is no app2
    ground truth here; this is an original web feature. These tests pin its
    own documented contract (append a sha256 and md5 digest per row) instead
    of a desktop comparison.
    """

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="utilization_"))
        self.workdir = self.tmpdir / "web-work"
        (self.workdir / "out").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_hash_columns_match_pipe_joined_row_digest(self):
        from worker.handlers import utilization

        src = self.tmpdir / "raw.xlsx"
        pd.DataFrame({"A": ["x"], "B": ["y"]}).to_excel(src, index=False)

        outputs = utilization({}, [str(src)], self.workdir, lambda *_args: None)
        self.assertEqual(Path(outputs[0]).name, "UTIL_raw.xlsx")

        out_df = pd.read_excel(outputs[0])
        row = out_df.iloc[0]
        joined = "|".join(str(v) for v in [row["A"], row["B"]])
        self.assertEqual(row["_sha256"], hashlib.sha256(joined.encode()).hexdigest())
        self.assertEqual(row["_md5"], hashlib.md5(joined.encode()).hexdigest())

    def test_different_rows_get_different_hashes(self):
        from worker.handlers import utilization

        src = self.tmpdir / "raw.xlsx"
        pd.DataFrame({"A": ["one", "two"]}).to_excel(src, index=False)

        outputs = utilization({}, [str(src)], self.workdir, lambda *_args: None)
        out_df = pd.read_excel(outputs[0])
        self.assertNotEqual(out_df.iloc[0]["_sha256"], out_df.iloc[1]["_sha256"])
        self.assertNotEqual(out_df.iloc[0]["_md5"], out_df.iloc[1]["_md5"])

    def test_csv_input_is_accepted(self):
        from worker.handlers import utilization

        src = self.tmpdir / "raw.csv"
        pd.DataFrame({"A": [1, 2]}).to_csv(src, index=False)

        outputs = utilization({}, [str(src)], self.workdir, lambda *_args: None)
        out_df = pd.read_excel(outputs[0])
        self.assertIn("_sha256", out_df.columns)
        self.assertIn("_md5", out_df.columns)
        self.assertEqual(len(out_df), 2)

    def test_db_data_source_raises_not_implemented(self):
        from worker.handlers import utilization

        with self.assertRaises(NotImplementedError):
            utilization(
                {"input_refs": {"data_source": "db"}},
                [],
                self.workdir,
                lambda *_args: None,
            )


if __name__ == "__main__":
    unittest.main()
