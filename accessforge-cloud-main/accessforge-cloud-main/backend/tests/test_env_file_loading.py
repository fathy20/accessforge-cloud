from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestEnvironmentFileLoading(unittest.TestCase):
    def test_resolve_environment_files_returns_both_with_root_first(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temporary_directory:
            from backend.config import resolve_environment_files

            root_dir = Path(temporary_directory)
            backend_dir = root_dir / "backend"
            backend_dir.mkdir()
            root_env = root_dir / ".env"
            backend_env = backend_dir / ".env"
            root_env.touch()
            backend_env.touch()

            self.assertEqual(resolve_environment_files(backend_dir), (root_env, backend_env))

    def test_resolve_environment_files_returns_only_existing_files(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temporary_directory:
            from backend.config import resolve_environment_files

            root_dir = Path(temporary_directory)
            backend_dir = root_dir / "backend"
            backend_dir.mkdir()
            root_env = root_dir / ".env"
            backend_env = backend_dir / ".env"

            root_env.touch()
            self.assertEqual(resolve_environment_files(backend_dir), (root_env,))

            root_env.unlink()
            backend_env.touch()
            self.assertEqual(resolve_environment_files(backend_dir), (backend_env,))

            backend_env.unlink()
            self.assertEqual(resolve_environment_files(backend_dir), ())

    def test_load_environment_files_loads_backend_environment(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temporary_directory:
            from backend.config import load_environment_files

            backend_dir = Path(temporary_directory) / "backend"
            backend_dir.mkdir()
            (backend_dir / ".env").write_text("LEON_SYNTHETIC_VALUE=backend\n", encoding="utf-8")

            loaded = load_environment_files(backend_dir)

            self.assertEqual(loaded, (backend_dir / ".env",))
            self.assertEqual(os.environ["LEON_SYNTHETIC_VALUE"], "backend")

    def test_root_environment_wins_over_backend_environment(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temporary_directory:
            from backend.config import load_environment_files

            root_dir = Path(temporary_directory)
            backend_dir = root_dir / "backend"
            backend_dir.mkdir()
            (root_dir / ".env").write_text("SHARED_SYNTHETIC_VALUE=root\n", encoding="utf-8")
            (backend_dir / ".env").write_text("SHARED_SYNTHETIC_VALUE=backend\n", encoding="utf-8")

            load_environment_files(backend_dir)

            self.assertEqual(os.environ["SHARED_SYNTHETIC_VALUE"], "root")

    def test_process_environment_wins_over_both_files(self):
        with patch.dict(
            os.environ,
            {"SHARED_SYNTHETIC_VALUE": "process"},
            clear=True,
        ), tempfile.TemporaryDirectory() as temporary_directory:
            from backend.config import load_environment_files

            root_dir = Path(temporary_directory)
            backend_dir = root_dir / "backend"
            backend_dir.mkdir()
            (root_dir / ".env").write_text("SHARED_SYNTHETIC_VALUE=root\n", encoding="utf-8")
            (backend_dir / ".env").write_text("SHARED_SYNTHETIC_VALUE=backend\n", encoding="utf-8")

            load_environment_files(backend_dir)

            self.assertEqual(os.environ["SHARED_SYNTHETIC_VALUE"], "process")

    def test_resolving_environment_files_is_independent_of_current_working_directory(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as temporary_directory:
            from backend.config import resolve_environment_files

            root_dir = Path(temporary_directory)
            backend_dir = root_dir / "backend"
            unrelated_dir = root_dir / "unrelated"
            backend_dir.mkdir()
            unrelated_dir.mkdir()
            root_env = root_dir / ".env"
            backend_env = backend_dir / ".env"
            root_env.touch()
            backend_env.touch()
            expected = (root_env, backend_env)
            original_cwd = Path.cwd()

            try:
                os.chdir(unrelated_dir)
                self.assertEqual(resolve_environment_files(backend_dir), expected)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(resolve_environment_files(backend_dir), expected)

    def test_unconfigured_leon_client_raises_configuration_error(self):
        with patch.dict(os.environ, {}, clear=True):
            from backend.statistics.crew_hours.errors import LeonConfigurationError
            from backend.statistics.crew_hours.leon_client import get_crew_hours_leon_client

            client = get_crew_hours_leon_client()
            with self.assertRaises(LeonConfigurationError):
                client.fetch_flights("2026-01-01", "2026-01-02")


if __name__ == "__main__":
    unittest.main()
