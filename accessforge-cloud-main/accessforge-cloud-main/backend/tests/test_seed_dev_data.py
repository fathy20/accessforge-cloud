"""The dev seeder must refuse every target except a local SQLite database."""

from __future__ import annotations

import unittest

from backend.tools.seed_dev_data import SeedSafetyError, assert_local_database


class TestSeedRefusesNonLocalDatabases(unittest.TestCase):
    def test_rejects_sql_server_odbc_url(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database(
                "mssql+pyodbc://redsea:secret@prod-sql.internal:1433/redsea_db"
            )

    def test_rejects_assembled_odbc_connect_url(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database(
                "mssql+pyodbc:///?odbc_connect=DRIVER%3D%7BODBC%2BDriver%2B17%7D%3BSERVER%3Dprod"
            )

    def test_rejects_postgresql_url(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database("postgresql://user:pw@db.example.com:5432/redsea")

    def test_rejects_mysql_url(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database("mysql+pymysql://user:pw@10.0.0.9/redsea")

    def test_rejects_sqlite_url_naming_a_host(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database("sqlite://remote-host/redsea.db")

    def test_rejects_unc_network_share(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database(r"sqlite:///\fileserver\share\redsea.db")

    def test_rejects_production_app_env_even_for_sqlite(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database("sqlite:///./redsea.db", app_env="production")

    def test_rejects_missing_or_blank_url(self) -> None:
        for value in (None, "", "   "):
            with self.subTest(value=value), self.assertRaises(SeedSafetyError):
                assert_local_database(value)

    def test_rejects_garbage_url(self) -> None:
        with self.assertRaises(SeedSafetyError):
            assert_local_database("not-a-url-at-all")

    def test_error_message_names_the_offending_backend(self) -> None:
        with self.assertRaises(SeedSafetyError) as caught:
            assert_local_database("postgresql://user:pw@db.example.com/redsea")
        self.assertIn("non-local", str(caught.exception))


class TestSeedRefusesAssembledSqlServerUrl(unittest.TestCase):
    """SQL_SERVER_* variables assemble an mssql URL; the guard must reject it."""

    def test_rejects_url_assembled_from_sql_server_env(self) -> None:
        from backend.config import resolve_database_url

        environment = {
            "APP_ENV": "development",
            "SQL_SERVER_HOST": "prod-sql.redsea.local",
            "SQL_SERVER_DB": "redsea_db",
            "SQL_SERVER_TRUSTED_CONNECTION": "yes",
        }
        assembled = resolve_database_url("development", environment)
        self.assertTrue(assembled.startswith("mssql+pyodbc"), assembled)

        with self.assertRaises(SeedSafetyError):
            assert_local_database(assembled)


class TestSeedAcceptsLocalSqlite(unittest.TestCase):
    def test_accepts_relative_sqlite_file(self) -> None:
        url = "sqlite:///./redsea.db"
        self.assertEqual(assert_local_database(url), url)

    def test_accepts_absolute_sqlite_file(self) -> None:
        url = "sqlite:////tmp/redsea.db"
        self.assertEqual(assert_local_database(url), url)

    def test_accepts_in_memory_sqlite(self) -> None:
        url = "sqlite:///:memory:"
        self.assertEqual(assert_local_database(url), url)


if __name__ == "__main__":
    unittest.main()
