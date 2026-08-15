from __future__ import annotations

import unittest
from unittest.mock import patch

from sqlalchemy.exc import DisconnectionError, IntegrityError, OperationalError, ProgrammingError

from backend import database


class _SpySession:
    def __init__(self):
        self.events = []

    def add(self, value):
        self.events.append(("add", value))

    def commit(self):
        self.events.append(("commit",))

    def rollback(self):
        self.events.append(("rollback",))

    def close(self):
        self.events.append(("close",))


def _dependency_session(session):
    with patch.object(database, "SessionLocal", return_value=session):
        generator = database.get_db()
        yielded = next(generator)
    assert yielded is session
    return generator, yielded


def _operational_error(number: int) -> OperationalError:
    return OperationalError("SELECT", {}, RuntimeError(f"database error {number}"))


class TestEngineOptions(unittest.TestCase):
    def test_sqlite_options_are_free_of_sql_server_pool_arguments(self):
        options = database.engine_options_for("sqlite", "test")

        self.assertEqual(options, {"connect_args": {"check_same_thread": False}})
        for forbidden in (
            "pool_size",
            "max_overflow",
            "pool_timeout",
            "pool_recycle",
            "fast_executemany",
        ):
            self.assertNotIn(forbidden, options)

    def test_sql_server_options_use_the_approved_bounded_pool(self):
        options = database.engine_options_for("mssql", "production")

        self.assertTrue(options["pool_pre_ping"])
        self.assertEqual(options["pool_size"], 10)
        self.assertEqual(options["max_overflow"], 20)
        self.assertEqual(options["pool_timeout"], 30)
        self.assertEqual(options["pool_recycle"], 3600)
        self.assertEqual(options["connect_args"], {"timeout": 10})
        self.assertNotIn("fast_executemany", options)


class TestSessionLifecycle(unittest.TestCase):
    def test_get_db_closes_session(self):
        session = _SpySession()
        generator, _ = _dependency_session(session)

        with self.assertRaises(StopIteration):
            next(generator)

        self.assertEqual(session.events, [("close",)])

    def test_get_db_rolls_back_on_consumer_exception_and_reraises(self):
        session = _SpySession()
        generator, _ = _dependency_session(session)

        with self.assertRaisesRegex(RuntimeError, "consumer failure"):
            generator.throw(RuntimeError("consumer failure"))

        self.assertEqual(session.events, [("rollback",), ("close",)])

    def test_successful_read_path_does_not_commit(self):
        session = _SpySession()
        generator, _ = _dependency_session(session)
        generator.close()

        self.assertNotIn(("commit",), session.events)
        self.assertEqual(session.events, [("close",)])

    def test_explicit_write_unit_of_work_commits_once(self):
        session = _SpySession()
        generator, db = _dependency_session(session)

        db.add("write")
        db.commit()
        generator.close()

        self.assertEqual(session.events, [("add", "write"), ("commit",), ("close",)])

    def test_failed_write_rolls_back_and_does_not_commit(self):
        session = _SpySession()
        generator, db = _dependency_session(session)

        with self.assertRaisesRegex(RuntimeError, "write failure"):
            try:
                db.add("write")
                raise RuntimeError("write failure")
            except Exception:
                db.rollback()
                raise
        generator.close()

        self.assertNotIn(("commit",), session.events)
        self.assertEqual(session.events, [("add", "write"), ("rollback",), ("close",)])


class TestDatabaseFailurePolicy(unittest.TestCase):
    def test_integrity_errors_are_non_retryable(self):
        error = IntegrityError("INSERT", {}, RuntimeError("constraint violation"))
        self.assertEqual(
            database.classify_database_error(error), database.DatabaseFailureKind.INTEGRITY
        )

        calls = 0

        def operation():
            nonlocal calls
            calls += 1
            raise error

        with self.assertRaises(IntegrityError):
            database.retry_idempotent(operation, attempts=3, base_delay=0)
        self.assertEqual(calls, 1)

    def test_classification_uses_known_sql_server_numbers(self):
        self.assertEqual(
            database.classify_database_error(DisconnectionError()),
            database.DatabaseFailureKind.TRANSIENT,
        )
        self.assertEqual(
            database.classify_database_error(_operational_error(1205)),
            database.DatabaseFailureKind.DEADLOCK,
        )
        self.assertEqual(
            database.classify_database_error(_operational_error(-2)),
            database.DatabaseFailureKind.TIMEOUT,
        )
        self.assertEqual(
            database.classify_database_error(_operational_error(40613)),
            database.DatabaseFailureKind.TRANSIENT,
        )
        self.assertEqual(
            database.classify_database_error(ProgrammingError("SELECT", {}, RuntimeError("syntax"))),
            database.DatabaseFailureKind.PROGRAMMING,
        )
        self.assertEqual(
            database.classify_database_error(_operational_error(9999)),
            database.DatabaseFailureKind.UNKNOWN,
        )
        self.assertEqual(
            database.classify_database_error(
                OperationalError("SELECT 1205", {}, RuntimeError("unclassified"))
            ),
            database.DatabaseFailureKind.UNKNOWN,
        )

    def test_retry_idempotent_respects_attempt_bound_for_retryable_error(self):
        calls = 0
        error = _operational_error(1205)

        def operation():
            nonlocal calls
            calls += 1
            raise error

        with self.assertRaises(OperationalError):
            database.retry_idempotent(operation, attempts=3, base_delay=0)

        self.assertEqual(calls, 3)
