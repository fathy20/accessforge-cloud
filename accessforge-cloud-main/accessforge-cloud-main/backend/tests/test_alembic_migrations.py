"""DB-2 Alembic baseline safety and compatibility harness.

All online migration exercises run in child processes so Alembic can import
``backend.database`` against the explicit temporary URL for that exercise.
The SQL Server checks are offline-only and never open a connection.
"""

from __future__ import annotations

import importlib
import inspect as inspect_module
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

# unittest does not load the collection fixture; keep this module isolated from
# application or development database targets before importing backend.database.
os.environ["APP_ENV"] = "test"
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect as sa_inspect, text

from backend.config import validate_test_database_url
from backend.database import Base, NAMING_CONVENTION
import backend.models  # noqa: F401


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIG_PATH = REPOSITORY_ROOT / "alembic.ini"
from backend.tools.alembic_head import expected_migration_head

BASELINE_REVISION = "a4fcbd8f8388"
CURRENT_HEAD = expected_migration_head()
BASELINE_PATH = REPOSITORY_ROOT / "alembic" / "versions" / "a4fcbd8f8388_current_schema_baseline.py"
APP_TABLES = frozenset(Base.metadata.tables)

# This URL is used only with command.upgrade(..., sql=True).  It is a
# deliberately non-routable documentation target, not a database to connect to.
OFFLINE_SQL_SERVER_URL = (
    "mssql+pyodbc://offline-db2-host/offline_db2"
    "?driver=ODBC+Driver+18+for+SQL+Server"
)


_PROGRAMMATIC_ALEMBIC_SCRIPT = r'''
import sys
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config


database_url = sys.argv[1]
operation = sys.argv[2]
sql_mode = sys.argv[3] == "1"
# Optional explicit revision target; absent means the operation's natural end
# (head for upgrade, base for downgrade), preserving every existing call site.
target = sys.argv[4] if len(sys.argv) > 4 else ""
config = Config(str(Path.cwd() / "alembic.ini"))
config.attributes["database_url"] = database_url

if operation == "upgrade":
    command.upgrade(config, target or "head", sql=sql_mode)
elif operation == "upgrade_with_create_all_spy":
    from backend.database import Base
    import backend.models  # noqa: F401

    with patch.object(Base.metadata, "create_all") as create_all:
        command.upgrade(config, "head", sql=sql_mode)
    print(create_all.call_count)
elif operation == "downgrade":
    command.downgrade(config, "base", sql=sql_mode)
else:
    raise ValueError(f"unsupported migration operation: {operation}")
'''


def _sqlite_url(path: Path) -> str:
    """Return and validate an absolute, temporary SQLite file URL."""

    absolute_path = path.resolve()
    if not absolute_path.is_absolute():
        raise AssertionError("temporary SQLite path must be absolute")
    url = f"sqlite:///{absolute_path.as_posix()}"
    validate_test_database_url(url)
    return url


def _child_environment(database_url: str, app_env: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["APP_ENV"] = app_env
    environment["DATABASE_URL"] = database_url
    return environment


def _run_child(code: str, database_url: str, *, app_env: str = "test") -> str:
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPOSITORY_ROOT,
        env=_child_environment(database_url, app_env),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Child-process verification failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout.strip()


def _load_baseline_module():
    spec = importlib.util.spec_from_file_location("db2_baseline_revision", BASELINE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load the Alembic baseline revision")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_programmatic_migration(
    database_url: str,
    operation: str,
    *,
    app_env: str = "test",
    sql: bool = False,
    target: str | None = None,
) -> str:
    """Run Alembic through Config/command without invoking the CLI.

    ``target`` pins an explicit revision; omitting it keeps the historical
    behaviour (upgrade to head, downgrade to base).
    """

    if app_env == "test":
        validate_test_database_url(database_url)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROGRAMMATIC_ALEMBIC_SCRIPT,
            database_url,
            operation,
            "1" if sql else "0",
            target or "",
        ],
        cwd=REPOSITORY_ROOT,
        env=_child_environment(database_url, app_env),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Programmatic Alembic {operation} failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


def _offline_ddl_column_type(ddl: str, table_name: str, column_name: str) -> str:
    table_match = re.search(
        rf"CREATE TABLE {re.escape(table_name)} \((?P<body>.*?)\r?\n\);",
        ddl,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if table_match is None:
        raise AssertionError(f"CREATE TABLE statement not found for {table_name}")

    column_match = re.search(
        rf"^\s+{re.escape(column_name)}\s+(?P<type>[A-Z]+(?:\([^)]+\))?)\s+(?:NULL|NOT NULL),?\s*$",
        table_match.group("body"),
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if column_match is None:
        raise AssertionError(f"Column {table_name}.{column_name} not found in offline DDL")
    return column_match.group("type").upper()


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return set(sa_inspect(connection).get_table_names())
    finally:
        engine.dispose()


def _schema_constraint_signature(database_url: str) -> dict[str, dict[str, tuple]]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = sa_inspect(connection)
            signature: dict[str, dict[str, tuple]] = {}
            for table_name in sorted(APP_TABLES):
                primary_key = inspector.get_pk_constraint(table_name).get("name")
                foreign_keys = tuple(
                    sorted(
                        (
                            item.get("name"),
                            tuple(item.get("constrained_columns", ())),
                            item.get("referred_table"),
                            tuple(item.get("referred_columns", ())),
                        )
                        for item in inspector.get_foreign_keys(table_name)
                    )
                )
                unique_constraints = tuple(
                    sorted(
                        item.get("name")
                        for item in inspector.get_unique_constraints(table_name)
                        if item.get("name")
                    )
                )
                indexes = tuple(
                    sorted(
                        (
                            item.get("name"),
                            bool(item.get("unique")),
                            tuple(item.get("column_names", ())),
                        )
                        for item in inspector.get_indexes(table_name)
                    )
                )
                signature[table_name] = {
                    "primary_key": (primary_key,),
                    "foreign_keys": foreign_keys,
                    "unique_constraints": unique_constraints,
                    "indexes": indexes,
                }
            return signature
    finally:
        engine.dispose()


class _TemporarySQLiteTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="db2-alembic-")

    def tearDown(self):
        try:
            self._temporary_directory.cleanup()
        finally:
            super().tearDown()

    def _temporary_sqlite_url(self, filename: str) -> str:
        return _sqlite_url(Path(self._temporary_directory.name) / filename)


class TestMigrationLifecycle(_TemporarySQLiteTestCase):
    def test_upgrade_from_empty_temporary_database_to_head_succeeds(self):
        database_url = self._temporary_sqlite_url("upgrade.sqlite")
        self.assertFalse(Path(database_url.removeprefix("sqlite:///" )).exists())

        _run_programmatic_migration(database_url, "upgrade")

        self.assertEqual(BASELINE_REVISION, "a4fcbd8f8388")
        self.assertIn("alembic_version", _table_names(database_url))

    def test_upgraded_schema_matches_metadata_with_empty_autogenerate_diff(self):
        database_url = self._temporary_sqlite_url("metadata.sqlite")
        _run_programmatic_migration(database_url, "upgrade")

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                migration_context = MigrationContext.configure(
                    connection,
                    opts={"compare_type": True},
                )
                differences = compare_metadata(migration_context, Base.metadata)
        finally:
            engine.dispose()

        self.assertEqual(differences, [])

    def test_downgrade_from_head_to_base_succeeds(self):
        database_url = self._temporary_sqlite_url("downgrade.sqlite")
        _run_programmatic_migration(database_url, "upgrade")
        _run_programmatic_migration(database_url, "downgrade")

    def test_downgrade_leaves_no_application_tables(self):
        database_url = self._temporary_sqlite_url("empty-after-downgrade.sqlite")
        _run_programmatic_migration(database_url, "upgrade")
        _run_programmatic_migration(database_url, "downgrade")

        self.assertEqual(_table_names(database_url).intersection(APP_TABLES), set())
        self.assertLessEqual(_table_names(database_url), {"alembic_version"})

    def test_upgrade_after_downgrade_is_deterministic(self):
        database_url = self._temporary_sqlite_url("round-trip.sqlite")
        _run_programmatic_migration(database_url, "upgrade")
        _run_programmatic_migration(database_url, "downgrade")
        _run_programmatic_migration(database_url, "upgrade")

        self.assertEqual(_table_names(database_url).intersection(APP_TABLES), APP_TABLES)


class TestMigrationIntegrity(_TemporarySQLiteTestCase):
    def test_revision_chain_is_valid_and_walkable(self):
        script_directory = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG_PATH)))
        revision = script_directory.get_revision(BASELINE_REVISION)

        self.assertIsNotNone(revision)
        self.assertIsNone(revision.down_revision)

        walked: list[str] = []
        cursor = revision
        while cursor is not None:
            walked.append(cursor.revision)
            if cursor.down_revision is None:
                break
            self.assertIsInstance(cursor.down_revision, str)
            cursor = script_directory.get_revision(cursor.down_revision)

        self.assertEqual(walked, [BASELINE_REVISION])

    def test_exactly_one_alembic_head_exists(self):
        script_directory = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG_PATH)))

        self.assertEqual(script_directory.get_heads(), [CURRENT_HEAD])

    def test_importing_migration_revision_does_not_import_backend_main(self):
        database_url = self._temporary_sqlite_url("import-only.sqlite")
        output = _run_child(
            "import importlib.util, sys; "
            "from pathlib import Path; "
            "path = Path.cwd() / 'alembic' / 'versions' / 'a4fcbd8f8388_current_schema_baseline.py'; "
            "spec = importlib.util.spec_from_file_location('db2_baseline_revision', path); "
            "module = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(module); "
            "print('backend.main' in sys.modules)",
            database_url,
        )

        self.assertEqual(output, "False")

    def test_running_migrations_does_not_call_base_metadata_create_all(self):
        database_url = self._temporary_sqlite_url("create-all-spy.sqlite")
        output = _run_programmatic_migration(
            database_url,
            "upgrade_with_create_all_spy",
        )

        self.assertEqual(output.strip(), "0")

    def test_upgrade_does_not_seed_users(self):
        database_url = self._temporary_sqlite_url("no-seed.sqlite")
        _run_programmatic_migration(database_url, "upgrade")

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                user_count = connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one()
        finally:
            engine.dispose()

        self.assertEqual(user_count, 0)

    # Revision immediately before c9d0e1f2a3b4, whose upgrade() deduplicates
    # user_roles and module_access before adding the unique indexes.
    _PRE_DEDUPE_REVISION = "b8c9d0e1f2a3"

    def _seed_conflicting_module_access(self, database_url: str) -> None:
        """Seed one (user, module) pair holding both a denied and an enabled row.

        The ENABLED row is given the lexicographically smaller id on purpose:
        module_access.id is a String(36) UUID, so a MIN(id) survivor rule keeps
        this row and silently grants access that was explicitly denied. The
        owner ruling (Q-2, 2026-08-19) is that the denied row must win.
        """

        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO users (id, email) VALUES ('user-1', 'dedupe@dev.local')")
                )
                connection.execute(
                    text("INSERT INTO modules (id, key) VALUES ('module-1', 'crew_hours')")
                )
                connection.execute(
                    text(
                        "INSERT INTO module_access (id, user_id, module_id, enabled) "
                        "VALUES ('00000000-aaaa', 'user-1', 'module-1', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO module_access (id, user_id, module_id, enabled) "
                        "VALUES ('ffffffff-zzzz', 'user-1', 'module-1', 0)"
                    )
                )
        finally:
            engine.dispose()

    def _module_access_rows(self, database_url: str) -> list[tuple]:
        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                return [
                    tuple(row)
                    for row in connection.execute(
                        text(
                            "SELECT id, enabled FROM module_access "
                            "WHERE user_id = 'user-1' AND module_id = 'module-1' ORDER BY id"
                        )
                    ).fetchall()
                ]
        finally:
            engine.dispose()

    def test_module_access_dedupe_keeps_the_denied_row_over_an_enabled_duplicate(self):
        """A migration must never grant access that was explicitly denied."""

        database_url = self._temporary_sqlite_url("dedupe-restrictive.sqlite")
        _run_programmatic_migration(
            database_url, "upgrade", target=self._PRE_DEDUPE_REVISION
        )
        self._seed_conflicting_module_access(database_url)

        _run_programmatic_migration(database_url, "upgrade")

        rows = self._module_access_rows(database_url)
        self.assertEqual(len(rows), 1, f"dedupe must leave exactly one row, got {rows}")
        surviving_id, surviving_enabled = rows[0]
        self.assertEqual(
            bool(surviving_enabled),
            False,
            f"the denied row must survive; kept {surviving_id!r} with enabled={surviving_enabled!r}",
        )
        self.assertEqual(surviving_id, "ffffffff-zzzz")

    def test_module_access_dedupe_is_deterministic_when_no_row_is_denied(self):
        """With no conflict of intent, the survivor stays deterministic."""

        database_url = self._temporary_sqlite_url("dedupe-agreeing.sqlite")
        _run_programmatic_migration(
            database_url, "upgrade", target=self._PRE_DEDUPE_REVISION
        )
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO users (id, email) VALUES ('user-1', 'dedupe@dev.local')")
                )
                connection.execute(
                    text("INSERT INTO modules (id, key) VALUES ('module-1', 'crew_hours')")
                )
                for identifier in ("00000000-aaaa", "ffffffff-zzzz"):
                    connection.execute(
                        text(
                            "INSERT INTO module_access (id, user_id, module_id, enabled) "
                            f"VALUES ('{identifier}', 'user-1', 'module-1', 1)"
                        )
                    )
        finally:
            engine.dispose()

        _run_programmatic_migration(database_url, "upgrade")

        rows = self._module_access_rows(database_url)
        self.assertEqual(rows, [("00000000-aaaa", 1)])

    def test_module_access_dedupe_collapses_null_keyed_duplicates_without_deleting_them(self):
        """NULL user_id/module_id groups must keep one row, not lose all of them.

        GROUP BY treats NULLs as one group, so the original dedupe kept a
        survivor here. A correlated rewrite using plain ``=`` would compare
        NULL to NULL, match nothing, and delete every row in the group. The
        NULL-safe join predicates in the migration exist for this case.
        """

        database_url = self._temporary_sqlite_url("dedupe-null-keys.sqlite")
        _run_programmatic_migration(
            database_url, "upgrade", target=self._PRE_DEDUPE_REVISION
        )
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO modules (id, key) VALUES ('module-1', 'crew_hours')")
                )
                # Same NULL user_id, so one group; the allow row sorts first.
                connection.execute(
                    text(
                        "INSERT INTO module_access (id, user_id, module_id, enabled) "
                        "VALUES ('00000000-aaaa', NULL, 'module-1', 1)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO module_access (id, user_id, module_id, enabled) "
                        "VALUES ('ffffffff-zzzz', NULL, 'module-1', 0)"
                    )
                )
        finally:
            engine.dispose()

        _run_programmatic_migration(database_url, "upgrade")

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                rows = [
                    tuple(row)
                    for row in connection.execute(
                        text(
                            "SELECT id, enabled FROM module_access "
                            "WHERE user_id IS NULL AND module_id = 'module-1'"
                        )
                    ).fetchall()
                ]
        finally:
            engine.dispose()

        self.assertEqual(len(rows), 1, f"the NULL-keyed group must not be emptied, got {rows}")
        self.assertEqual(bool(rows[0][1]), False, "the denied row must still win")

    def test_constraint_names_are_stable_across_two_migration_runs(self):
        first_url = self._temporary_sqlite_url("names-first.sqlite")
        second_url = self._temporary_sqlite_url("names-second.sqlite")
        _run_programmatic_migration(first_url, "upgrade")
        _run_programmatic_migration(second_url, "upgrade")

        self.assertEqual(_schema_constraint_signature(first_url), _schema_constraint_signature(second_url))

    def test_constraint_names_match_naming_convention_prefixes(self):
        database_url = self._temporary_sqlite_url("naming-convention.sqlite")
        _run_programmatic_migration(database_url, "upgrade")

        prefixes = {key: value.split("%", 1)[0] for key, value in NAMING_CONVENTION.items()}
        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                inspector = sa_inspect(connection)
                for table_name in sorted(APP_TABLES):
                    primary_key_name = inspector.get_pk_constraint(table_name).get("name")
                    self.assertTrue(primary_key_name.startswith(prefixes["pk"]))

                    for foreign_key in inspector.get_foreign_keys(table_name):
                        self.assertTrue(foreign_key["name"].startswith(prefixes["fk"]))
                    for unique_constraint in inspector.get_unique_constraints(table_name):
                        self.assertTrue(unique_constraint["name"].startswith(prefixes["uq"]))
                    for index in inspector.get_indexes(table_name):
                        self.assertTrue(index["name"].startswith(prefixes["ix"]))
        finally:
            engine.dispose()

    def test_foreign_key_creation_and_drop_order_is_dependency_safe(self):
        database_url = self._temporary_sqlite_url("foreign-keys.sqlite")
        _run_programmatic_migration(database_url, "upgrade")

        engine = create_engine(database_url)
        try:
            with engine.connect() as connection:
                foreign_key_count = sum(
                    len(sa_inspect(connection).get_foreign_keys(table_name))
                    for table_name in APP_TABLES
                )
        finally:
            engine.dispose()

        self.assertGreater(foreign_key_count, 0)
        _run_programmatic_migration(database_url, "downgrade")

    def test_revision_defines_an_explicit_real_downgrade(self):
        migration = _load_baseline_module()
        downgrade = getattr(migration, "downgrade", None)
        source = inspect_module.getsource(downgrade)

        self.assertTrue(callable(downgrade))
        self.assertIn("op.drop_table", source)
        self.assertIn("op.drop_index", source)
        self.assertIsNone(re.search(r"\bpass\b", source))


class TestSqlServerOfflineDDL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sql_server_offline_ddl = _run_programmatic_migration(
            OFFLINE_SQL_SERVER_URL,
            "upgrade",
            app_env="development",
            sql=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.sql_server_offline_ddl = None
        super().tearDownClass()

    def test_sql_server_offline_ddl_contains_no_sqlite_only_syntax(self):
        ddl = self.sql_server_offline_ddl.upper()

        self.assertNotIn("AUTOINCREMENT", ddl)
        self.assertNotIn("PRAGMA", ddl)
        self.assertNotIn("WITHOUT ROWID", ddl)

    def test_json_columns_compile_to_nvarchar_max_on_sql_server(self):
        json_columns = {
            "audit_log.metadata_json",
            "jobs.input_refs",
            "jobs.output_refs",
            "jobs.logs",
            "uploads.metadata_json",
        }
        for qualified_name in sorted(json_columns):
            table_name, column_name = qualified_name.split(".")
            with self.subTest(column=qualified_name):
                self.assertEqual(
                    _offline_ddl_column_type(self.sql_server_offline_ddl, table_name, column_name),
                    "NVARCHAR(MAX)",
                )

    def test_boolean_columns_compile_to_bit_on_sql_server(self):
        for qualified_name in ("modules.enabled", "module_access.enabled"):
            table_name, column_name = qualified_name.split(".")
            with self.subTest(column=qualified_name):
                self.assertEqual(
                    _offline_ddl_column_type(self.sql_server_offline_ddl, table_name, column_name),
                    "BIT",
                )

    def test_timezone_aware_datetime_compiles_to_datetimeoffset(self):
        datetime_columns = {
            "audit_log.ts",
            "jobs.started_at",
            "jobs.completed_at",
            "jobs.created_at",
            "module_access.created_at",
            "notifications.read_at",
            "notifications.created_at",
            "projects.created_at",
            "projects.updated_at",
            "uploads.created_at",
            "user_invitations.accepted_at",
            "user_invitations.expires_at",
            "user_invitations.created_at",
            "users.last_seen_at",
            "users.created_at",
            "users.updated_at",
        }
        for qualified_name in sorted(datetime_columns):
            table_name, column_name = qualified_name.split(".")
            with self.subTest(column=qualified_name):
                self.assertEqual(
                    _offline_ddl_column_type(self.sql_server_offline_ddl, table_name, column_name),
                    "DATETIMEOFFSET",
                )

    def test_uuid_string_primary_keys_do_not_emit_identity(self):
        """The current design uses String(36) UUID primary keys, not IDENTITY."""

        self.assertNotIn("IDENTITY", self.sql_server_offline_ddl.upper())

    def test_sql_server_user_facing_text_targets_are_precisely_unicode(self):
        unicode_columns = {
            "audit_log.actor_name": "NVARCHAR(255)",
            "modules.category": "NVARCHAR(128)",
            "modules.description": "NVARCHAR(1024)",
            "modules.name": "NVARCHAR(255)",
            "notifications.title": "NVARCHAR(255)",
            "projects.name": "NVARCHAR(255)",
            "uploads.original_name": "NVARCHAR(512)",
            "users.department": "NVARCHAR(255)",
            "users.full_name": "NVARCHAR(255)",
            "users.job_title": "NVARCHAR(255)",
        }
        for qualified_name, expected_type in sorted(unicode_columns.items()):
            table_name, column_name = qualified_name.split(".")
            with self.subTest(column=qualified_name):
                self.assertEqual(
                    _offline_ddl_column_type(self.sql_server_offline_ddl, table_name, column_name),
                    expected_type,
                )

        machine_columns = {
            "uploads.mime": "VARCHAR(128)",
            "uploads.storage_path": "VARCHAR(1024)",
            "users.email": "VARCHAR(255)",
            "users.id": "VARCHAR(36)",
        }
        for qualified_name, expected_type in sorted(machine_columns.items()):
            table_name, column_name = qualified_name.split(".")
            with self.subTest(column=qualified_name):
                self.assertEqual(
                    _offline_ddl_column_type(self.sql_server_offline_ddl, table_name, column_name),
                    expected_type,
                )

    def test_sql_server_free_text_targets_are_nvarchar_max_without_bare_text(self):
        free_text_columns = {
            "jobs.error_message",
            "notifications.body",
            "projects.description",
        }
        for qualified_name in sorted(free_text_columns):
            table_name, column_name = qualified_name.split(".")
            with self.subTest(column=qualified_name):
                self.assertEqual(
                    _offline_ddl_column_type(self.sql_server_offline_ddl, table_name, column_name),
                    "NVARCHAR(MAX)",
                )

        self.assertEqual(len(re.findall(r"\bTEXT\b", self.sql_server_offline_ddl.upper())), 0)


class TestMigrationSafety(_TemporarySQLiteTestCase):
    def test_test_database_url_is_temporary_sqlite_and_never_development_database(self):
        configured_url = os.environ.get("DATABASE_URL")
        validate_test_database_url(configured_url)
        temporary_url = self._temporary_sqlite_url("guard.sqlite")

        self.assertIsNotNone(configured_url)
        self.assertTrue(configured_url.casefold().startswith("sqlite:"))
        self.assertNotIn("redsea_dev", configured_url.casefold())
        self.assertTrue(temporary_url.casefold().startswith("sqlite:"))
