import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.dialects import mssql


class _CapturedQuery:
    def __init__(self, entity, first_result=None):
        from sqlalchemy import select

        self.entity = entity
        self.statement = select(entity)
        self._first_result = first_result

    def filter(self, *criteria):
        self.statement = self.statement.where(*criteria)
        return self

    def order_by(self, *ordering):
        self.statement = self.statement.order_by(*ordering)
        return self

    def all(self):
        return []

    def first(self):
        return self._first_result


class _CaptureDb:
    def __init__(self, first_result=None):
        self.queries = []
        self.first_result = first_result

    def query(self, entity):
        query = _CapturedQuery(entity, first_result=self.first_result)
        self.queries.append(query)
        return query


class TestSqlDialectCompatibility(unittest.TestCase):
    def test_module_visibility_boolean_filters_compile_for_sql_server(self):
        """The list and detail visibility filters must use T-SQL-safe booleans."""

        # Importing the application module with schema creation disabled keeps
        # this test on SQL compilation only; no database connection is opened.
        with patch("backend.config.should_auto_create_schema", return_value=False):
            from backend import main

        user = SimpleNamespace(id="user-1")
        list_db = _CaptureDb()
        with patch.object(main, "get_effective_permissions", return_value=set()):
            main.get_modules(db=list_db, current_user=user)

        detail_db = _CaptureDb(first_result=SimpleNamespace(id="module-1"))
        with (
            patch.object(main, "get_effective_permissions", return_value=set()),
            patch.object(main, "_module_is_visible", return_value=True),
            patch.object(main, "_module_payload", return_value={}),
        ):
            main.get_module(module_key="module-1", db=detail_db, current_user=user)

        disabled_queries = [
            query.statement
            for db in (list_db, detail_db)
            for query in db.queries
            if query.entity is main.ModuleAccess.module_id
        ]
        self.assertEqual(len(disabled_queries), 2)

        compiled_queries = [
            str(query.compile(dialect=mssql.dialect()))
            for query in disabled_queries
        ]

        for compiled in compiled_queries:
            self.assertNotIn(" IS 0", compiled.upper())
            self.assertNotIn(" IS 1", compiled.upper())

        self.assertTrue(all("= 0" in compiled for compiled in compiled_queries))


if __name__ == "__main__":
    unittest.main()
