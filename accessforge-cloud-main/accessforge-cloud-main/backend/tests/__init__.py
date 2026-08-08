"""Test-package environment setup shared by every runner.

`conftest.py` is a pytest-only hook, so configuration placed there never reaches
`python -m unittest discover`. This module is imported by both runners before any
test module executes -- Python imports a package's ``__init__`` ahead of anything
inside it -- so the collection-time database safety rules apply either way.

Nothing here changes application behaviour. Every value uses ``setdefault``, so a
real environment always wins and a misconfigured deployment can never be masked.
"""

from __future__ import annotations

import os

# Tests must never run under production database rules, so this is forced rather
# than defaulted -- an inherited APP_ENV=production must not survive into a test run.
os.environ["APP_ENV"] = "test"

# Tests that purge ``backend.*`` from sys.modules re-import ``backend.auth``, which
# requires a signing key. Production keeps raising when this is unset; this value is
# deliberately fake and exists only so the suite can import the module.
os.environ.setdefault("JWT_SECRET_KEY", "TEST_ONLY_NOT_A_SECRET_JWT_KEY_32_CHARS")

# Tests that need a file choose their own temporary target. A process-scoped
# in-memory default keeps import-only tests isolated; unsafe targets are still
# rejected by ``validate_test_database_url``.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
