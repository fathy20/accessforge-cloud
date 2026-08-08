from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestJwtConfiguration(unittest.TestCase):
    def _import_auth(self, jwt_secret: str | None) -> dict[str, object]:
        script = """
import json
import sys
import types

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda: False
sys.modules["dotenv"] = dotenv_stub

try:
    import backend.auth
except Exception as exc:
    print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}))
else:
    print(json.dumps({"ok": True}))
"""
        environment = os.environ.copy()
        environment["APP_ENV"] = "test"
        environment["DATABASE_URL"] = "sqlite:///:memory:"
        environment["PYTHON_DOTENV_DISABLED"] = "true"
        if jwt_secret is None:
            environment.pop("JWT_SECRET_KEY", None)
        else:
            environment["JWT_SECRET_KEY"] = jwt_secret

        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout.strip())

    def test_import_without_jwt_secret_fails(self):
        result = self._import_auth(None)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("JWT_SECRET_KEY", result["error"])

    def test_import_with_short_jwt_secret_fails(self):
        short_key = "x" * 31

        result = self._import_auth(short_key)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "ValueError")
        self.assertIn("at least 32 characters", result["error"])

    def test_import_with_sufficient_jwt_secret_succeeds(self):
        result = self._import_auth("TEST_ONLY_JWT_SECRET_" + "x" * 32)

        self.assertEqual(result, {"ok": True})

    def test_short_jwt_error_does_not_contain_offending_key(self):
        short_key = "x" * 31

        result = self._import_auth(short_key)

        self.assertFalse(result["ok"])
        self.assertNotIn(short_key, result["error"])


if __name__ == "__main__":
    unittest.main()
