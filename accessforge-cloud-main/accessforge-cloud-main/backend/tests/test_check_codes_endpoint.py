"""GET /api/uploads/{id}/check-codes: the Check list comes from the workbook.

App2's "Check:" dropdown is not a fixed list. Picking the MPD RSD Excel calls
``_refresh_available_checks`` -> ``_extract_available_checks_from_excel``
(app2.py:2916/3288/3333), which repopulates the combo with the distinct values
actually present in column 24 of that workbook. The web UI shipped a hardcoded
list instead, so an unlisted code was unselectable and a listed code the
workbook lacked ran a job that produced nothing. These tests pin the endpoint
that closes that gap -- including a direct comparison against app2 itself, so
the desktop method, not this file's reading of it, is the source of truth.
"""

import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSB_MIME = "application/vnd.ms-excel.sheet.binary.macroEnabled.12"
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"

# A genuine binary workbook (Excel 16.0, xlExcel12). Sheet order is deliberate:
# a decoy "Cover" sheet FIRST, the real "MPD RSD" sheet SECOND, so anything that
# silently falls back to sheet 0 reads the wrong sheet and is caught.
XLSB_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mpd_rsd_sample.xlsb"
XLSB_MPD_RSD_TASK = "27-001-00"  # lives on the MPD RSD sheet
XLSB_COVER_TASK = "27-002-00"  # lives on the decoy Cover sheet


class _DesktopCheckContext:
    """Stand-in ``self`` for the desktop extractor: it only touches logging.

    Same shape as ``_DesktopCmpContext`` in test_cmp_tcm_parity.py, minus the
    check-code normaliser the extractor never calls.
    """

    tx_cmp_tcm_log = None

    def _safe_log(self, *_args, **_kwargs):
        return None


def _write_workbook(path: Path, check_values, width: int = 25) -> None:
    """Write a sheet whose column 24 holds ``check_values``, one per row.

    ``width`` under 25 produces a sheet with no column 24 at all, which is the
    case the desktop app rejects with ``df.shape[1] <= 24``.
    """

    columns = [f"COL_{index}" for index in range(width)]
    rows = []
    for position, value in enumerate(check_values):
        row = [""] * width
        row[0] = f"27-{position:03d}-00"
        if width > 24:
            row[24] = value
        rows.append(row)
    pd.DataFrame(rows, columns=columns).to_excel(path, index=False)


class TestCheckCodesEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="check_codes_api_"))
        cls.fixtures = cls.tmpdir / "fixtures"
        cls.fixtures.mkdir()
        cls.original_cwd = os.getcwd()
        cls.original_db_url = os.environ.get("DATABASE_URL")
        cls.original_jwt_secret = os.environ.get("JWT_SECRET_KEY")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'api.db'}"
        os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-with-at-least-thirty-two-bytes"
        os.chdir(cls.tmpdir)
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)

        import backend.database as database
        import backend.main as main
        from backend.auth import get_password_hash
        from backend.models import AppRole, User, UserRole, UserStatus
        from backend.tools.sync_registry import sync_registry

        cls.database = database
        cls.main = main
        # Keep uploaded artifacts inside the temp tree instead of the real
        # local_storage/uploads directory.
        cls.original_upload_dir = main.UPLOAD_DIR
        cls.upload_dir = cls.tmpdir / "uploads"
        cls.upload_dir.mkdir()
        main.UPLOAD_DIR = cls.upload_dir

        with database.SessionLocal() as session:
            for email in ("owner@example.com", "intruder@example.com"):
                user = User(
                    email=email,
                    hashed_password=get_password_hash("test-password"),
                    full_name=email,
                    status=UserStatus.active,
                )
                session.add(user)
                session.flush()
                session.add(UserRole(user_id=user.id, role=AppRole.engineer))
            session.commit()
            sync_registry(session)

        cls.client = TestClient(main.app)
        cls.headers = cls._login("owner@example.com")
        cls.intruder_headers = cls._login("intruder@example.com")

    @classmethod
    def _login(cls, email: str) -> dict:
        auth = cls.client.post(
            "/api/auth/login",
            json={"email": email, "password": "test-password"},
        )
        auth.raise_for_status()
        return {"Authorization": f"Bearer {auth.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.main.UPLOAD_DIR = cls.original_upload_dir
        cls.database.engine.dispose()
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        os.chdir(cls.original_cwd)
        if cls.original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.original_db_url
        if cls.original_jwt_secret is None:
            os.environ.pop("JWT_SECRET_KEY", None)
        else:
            os.environ["JWT_SECRET_KEY"] = cls.original_jwt_secret
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _upload(self, path: Path, headers=None, mime: str = XLSX_MIME) -> str:
        response = self.client.post(
            "/api/uploads",
            headers=headers or self.headers,
            files={"files": (path.name, path.read_bytes(), mime)},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()[0]["id"]

    def _codes(self, upload_id: str, headers=None):
        response = self.client.get(
            f"/api/uploads/{upload_id}/check-codes",
            headers=headers or self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        # An object, not a bare array, so the response can gain fields later.
        self.assertIsInstance(payload, dict)
        self.assertEqual(list(payload), ["codes"])
        return payload["codes"]

    def _fixture(self, name: str, check_values, width: int = 25) -> Path:
        path = self.fixtures / name
        _write_workbook(path, check_values, width=width)
        return path

    def test_distinct_column_24_values_are_sorted_and_deduplicated(self):
        # "  120DY  " and "120DY" are one code: the desktop app strips before
        # it deduplicates, so the whitespace variant must not survive as a
        # second, unselectable entry.
        path = self._fixture(
            "codes.xlsx",
            ["A1", "C3", "A1", "  120DY  ", "120DY", "2000FC"],
        )
        codes = self._codes(self._upload(path))

        self.assertEqual(codes, ["120DY", "2000FC", "A1", "C3"])

    def test_codes_outside_the_hardcoded_frontend_list_are_returned(self):
        # The reason this endpoint exists: the frontend's fixed CHECK_OPTIONS
        # cannot express an operator's own code, so it was unselectable.
        path = self._fixture("custom.xlsx", ["A1", "6YR", "SVC-CHK/2"])
        codes = self._codes(self._upload(path))

        self.assertEqual(codes, ["6YR", "A1", "SVC-CHK/2"])

    def test_blank_nan_and_none_cells_are_excluded(self):
        path = self._fixture(
            "empties.xlsx",
            ["", "   ", "nan", "NaN", "none", "None", "A1"],
        )
        codes = self._codes(self._upload(path))

        self.assertEqual(codes, ["A1"])

    def test_workbook_of_only_empty_markers_yields_no_codes(self):
        path = self._fixture("all-empty.xlsx", ["", "nan", "None"])

        self.assertEqual(self._codes(self._upload(path)), [])

    def test_sheet_without_column_24_returns_empty_codes_and_200(self):
        # A too-narrow sheet is a legitimate empty answer, not a server error.
        path = self._fixture("narrow.xlsx", ["ignored", "ignored"], width=10)

        self.assertEqual(self._codes(self._upload(path)), [])

    def test_unreadable_artifact_returns_empty_codes_and_200(self):
        pdf_path = self.fixtures / "not-a-workbook.pdf"
        pdf_path.write_bytes(PDF_BYTES)
        upload_id = self._upload(pdf_path, mime="application/pdf")

        self.assertEqual(self._codes(upload_id), [])

    def test_overlong_values_are_not_offered_as_codes(self):
        # Bounded so a crafted workbook cannot balloon the response; dropped
        # rather than truncated, because a truncated code is not the code.
        path = self._fixture("overlong.xlsx", ["A1", "X" * 200])

        self.assertEqual(self._codes(self._upload(path)), ["A1"])

    def test_the_declared_cap_is_the_agreed_number(self):
        """Pin the literal, not the constant.

        `test_distinct_code_count_is_capped` derives both its fixture size and
        its expectation from `MAX_CHECK_CODES`, so it passes for ANY cap value
        -- 5 or 100000 alike -- and can only catch the `break` being deleted
        outright. The agreed bound is part of the endpoint's contract, so it
        gets asserted directly here; the test below then proves the cap is
        actually enforced at that number.
        """

        self.assertEqual(self.main.MAX_CHECK_CODES, 500)
        self.assertEqual(self.main.MAX_CHECK_CODE_LENGTH, 64)

    def test_distinct_code_count_is_capped(self):
        # 600 distinct codes against the agreed cap of 500. Fixed numbers, not
        # `MAX_CHECK_CODES +/- n`: an expectation derived from the same constant
        # as the input can never detect that constant changing.
        values = [f"CODE{index:04d}" for index in range(600)]
        path = self._fixture("hostile.xlsx", values)

        codes = self._codes(self._upload(path))

        self.assertEqual(len(codes), 500)
        self.assertTrue(set(codes).issubset(set(values)))

    def test_binary_xlsb_workbook_is_read_through_the_endpoint(self):
        """A real `.xlsb` survives upload -> storage allowlist -> this endpoint.

        Without this the `.xlsb` path had NO coverage at all: injecting a hard
        failure into the reader's `.xlsb` branch left every other test in this
        file green, because every other fixture here is `.xlsx`. MPD RSD
        deliveries are frequently `.xlsb`, so this is the format most likely to
        matter.

        Scope, precisely: this pins that the binary workbook is ACCEPTED and
        READ (remove `.xlsb` from storage.py's allowlist and the upload 415s
        here). It does not pin the explicit `engine="pyxlsb"` kwarg -- pandas
        infers that engine from the extension anyway -- nor sheet selection,
        since both sheets of the fixture share a column-24 value. Sheet
        selection is pinned by the test below, which reads column 0 instead.
        """

        self.assertTrue(
            XLSB_FIXTURE.exists(),
            f"missing committed fixture {XLSB_FIXTURE}",
        )
        upload_id = self._upload(XLSB_FIXTURE, mime=XLSB_MIME)

        self.assertEqual(self._codes(upload_id), ["A1"])

    def test_backend_reader_prefers_the_mpd_rsd_sheet_over_the_first_sheet(self):
        """Pin THIS copy of the sheet-selection rule, not just the worker's.

        `worker/toolkit.py::read_mpd_rsd_frame` carries a duplication note
        saying both copies must change together. The worker copy is pinned by
        test_cmp_tcm_parity.py; this one was not, so the two could drift apart
        silently -- exactly what that note warns about.

        The fixture's two sheets share a column-24 value, so codes alone cannot
        tell them apart; column 0 can. Falling back to sheet 0 yields the Cover
        sheet's task instead of the MPD RSD sheet's.
        """

        frame = self.main._read_mpd_rsd_frame(XLSB_FIXTURE)

        self.assertIsNotNone(frame)
        column_zero = [str(value).strip() for value in frame.iloc[:, 0]]
        self.assertIn(XLSB_MPD_RSD_TASK, column_zero)
        self.assertNotIn(
            XLSB_COVER_TASK,
            column_zero,
            "read the decoy Cover sheet -- the MPD RSD sheet was not preferred",
        )

    def test_another_users_upload_is_not_readable(self):
        path = self._fixture("owned.xlsx", ["A1", "C2"])
        upload_id = self._upload(path)
        self.assertEqual(self._codes(upload_id), ["A1", "C2"])

        forbidden = self.client.get(
            f"/api/uploads/{upload_id}/check-codes",
            headers=self.intruder_headers,
        )
        missing = self.client.get(
            f"/api/uploads/{uuid.uuid4()}/check-codes",
            headers=self.intruder_headers,
        )

        self.assertEqual(forbidden.status_code, 404)
        # Indistinguishable from a nonexistent id: another user's upload must
        # not be confirmable, let alone readable.
        self.assertEqual(forbidden.status_code, missing.status_code)
        self.assertEqual(forbidden.json(), missing.json())
        self.assertNotIn("A1", forbidden.text)

    def test_nonexistent_upload_returns_404(self):
        response = self.client.get(
            f"/api/uploads/{uuid.uuid4()}/check-codes",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Upload not found"})

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get(f"/api/uploads/{uuid.uuid4()}/check-codes")

        self.assertEqual(response.status_code, 401)

    def test_endpoint_matches_desktop_extract_available_checks_from_excel(self):
        """App2, not this test, decides which codes a workbook contains."""

        from worker import toolkit

        path = self._fixture(
            "parity.xlsx",
            ["A1", "C3", "A1", "  120DY  ", "", "None", "nan", "2000FC", "6YR"],
        )
        desktop_codes = toolkit.rt.RedseaApp._extract_available_checks_from_excel(
            _DesktopCheckContext(), str(path), None
        )

        self.assertEqual(self._codes(self._upload(path)), desktop_codes)
        # Guard against both sides agreeing on nothing.
        self.assertTrue(desktop_codes)


if __name__ == "__main__":
    unittest.main()
