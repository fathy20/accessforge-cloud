import csv
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestCheckControlApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="check_control_api_"))
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

        cls.database = database
        cls.main = main
        cls.client = TestClient(main.app)
        auth = cls.client.post(
            "/api/auth/register",
            json={"email": "api-test@example.com", "password": "test-password", "full_name": "API Test"},
        )
        auth.raise_for_status()
        cls.headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
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

    def _upload_checks_csv(self):
        content = io.StringIO()
        writer = csv.DictWriter(content, fieldnames=["CHECK", "TASK"])
        writer.writeheader()
        writer.writerows([
            {"CHECK": "A1", "TASK": "27-001-00"},
            {"CHECK": "A2", "TASK": "27-002-00"},
            {"CHECK": "C1", "TASK": "28-001-00"},
        ])
        response = self.client.post(
            "/api/uploads",
            headers=self.headers,
            files={"files": ("checks.csv", content.getvalue().encode(), "text/csv")},
        )
        response.raise_for_status()
        return response.json()[0]["id"]

    def test_upload_job_output_and_download(self):
        upload_id = self._upload_checks_csv()
        created = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={"module_key": "check_control", "input_refs": {"files": [upload_id], "check": "A2", "data_source": "files"}},
        )
        created.raise_for_status()

        job = self.client.get(f"/api/jobs/{created.json()['id']}", headers=self.headers)
        job.raise_for_status()
        self.assertEqual(job.json()["status"], "done")
        output = job.json()["output_refs"]["files"][0]
        self.assertEqual(output["name"], "CHECKS_A2.xlsx")

        download = self.client.get(urlsplit(output["url"]).path, headers=self.headers)
        download.raise_for_status()
        checks = pd.read_excel(io.BytesIO(download.content))["CHECK"].astype(str).str.upper().tolist()
        self.assertEqual(set(checks), {"A1", "A2"})

    def test_missing_upload_marks_job_failed_without_output(self):
        created = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={"module_key": "check_control", "input_refs": {"files": ["missing"], "check": "A2", "data_source": "files"}},
        )
        created.raise_for_status()

        job = self.client.get(f"/api/jobs/{created.json()['id']}", headers=self.headers)
        job.raise_for_status()
        self.assertEqual(job.json()["status"], "failed")
        self.assertTrue(job.json()["error_message"])
        self.assertFalse((job.json().get("output_refs") or {}).get("files"))

    def test_unknown_module_is_rejected(self):
        before = self.client.get("/api/jobs", headers=self.headers)
        before.raise_for_status()
        response = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={"module_key": "unknown_module", "input_refs": {"files": []}},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Unknown module: unknown_module")
        after = self.client.get("/api/jobs", headers=self.headers)
        after.raise_for_status()
        self.assertEqual(after.json(), before.json())


if __name__ == "__main__":
    unittest.main()
