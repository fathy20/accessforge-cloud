# Database configuration

## Environments

`APP_ENV` accepts exactly `development`, `test`, or `production`; when unset it is
`development`. Unknown values fail during configuration.

| Environment | Permitted | Rejected/defaulted |
| --- | --- | --- |
| development | Local SQLite, or an explicitly configured SQL Server URL | Incomplete SQL Server assembly falls back to the local SQLite default |
| test | `sqlite:///:memory:` or an absolute SQLite file below the system temporary directory | SQL Server/ODBC, development database targets, repository-relative SQLite files, and user-home database files |
| production | A non-empty, non-SQLite `DATABASE_URL` | Missing `DATABASE_URL` and every SQLite URL; no silent fallback |

Deployment-specific hosts, database names, drivers, credentials, and connection
strings stay in environment configuration and must not be copied into source,
documentation, tests, or logs.

SQLite is rejected in production because a file fallback can silently select the
wrong storage target and bypass the reviewed SQL Server deployment path.

Schema changes are manual, reviewed, and owned by Alembic. Application startup never
runs migrations. `Base.metadata.create_all` remains available only in development and
test; production logs that Alembic owns the schema and skips it.

Pytest sets `APP_ENV=test` before backend database import and validates the effective
URL during collection. If no URL is supplied, the collection harness uses an isolated
in-memory SQLite target for import-only legacy tests; a supplied URL must be memory or
an absolute file under the temporary directory. Test authors should set a temporary
SQLite URL before importing `backend.database`, and must never point tests at a local
or shared database.

## Alembic baseline and migration verification

The current Alembic baseline is revision `a4fcbd8f8388`, the sole revision-chain head.
It has never been applied in any known environment. Migrations are manual, reviewed,
and deliberate; application startup and worker execution never run Alembic
automatically.

The DB-2 migration harness covers the round trip from an empty database to the head,
head to base, and base back to the head. It also requires an empty Alembic
autogenerate diff against `Base.metadata`, no application tables after downgrade,
stable naming-convention constraint names, dependency-safe foreign-key teardown, no
`Base.metadata.create_all()` call, and no seeded users. Online migration tests use
temporary SQLite files only. SQL Server checks generate offline DDL and do not open a
SQL Server connection.

DB-2b repaired the two known SQL Server type defects in the unapplied baseline:

1. Bounded user-facing `String(n)` columns now use `Unicode(n)` and compile to
   `NVARCHAR(n)`. This covers bilingual names, departments, job titles, rendered module
   labels/descriptions/categories, project names, audit actor names, notification
   titles, and uploaded original filenames.
2. Free-text `Text` columns now use `UnicodeText` and compile to `NVARCHAR(max)` for
   `jobs.error_message`, `projects.description`, and `notifications.body`.

The classification policy is deliberate. Unicode is required for user-facing bilingual
text and free text. Machine identifiers, UUIDs, keys, tokens, hashes, enum/status
values, email and technical values, paths/storage keys, MIME values, and protocol
values remain `String` because they are ASCII by construction; widening them provides
no functional benefit while increasing storage and index-key cost.

The baseline was repaired in place because it was proven unapplied everywhere known
immediately before the change: `REDSEA_DEV` reported
`alembic_version = 0` with only its pre-existing system table and zero rows, the root
SQLite database reported `alembic_version = 0`, and the revision digest matched the
approved DB-2 state. No database was modified by this repair, and the revision identity,
chain, ordering, and constraints remain unchanged.

Any future user-facing text column must choose `Unicode(n)` for bounded text or
`UnicodeText` for free text so new schema remains Unicode-correct before application.
No production or development database is a test target, and no connection string or
credential belongs in this document.

## Engine factory

`backend.database.create_database_engine()` is the single engine-construction path.
`engine_options_for()` is a pure function: it only selects keyword arguments from the
dialect name and environment and never creates an engine or opens a connection.

SQLite receives exactly `connect_args={"check_same_thread": False}`. It therefore keeps
SQLAlchemy's SQLite pool semantics and never receives SQL Server-only pool arguments or
`fast_executemany`. SQL Server receives the bounded pool policy below; other supported
dialects retain the existing `pool_pre_ping` fallback. The module-level `engine` and
`SessionLocal` names remain stable for existing imports.

## SQL Server pool policy

| Option | Value | Reason |
| --- | ---: | --- |
| `pool_pre_ping` | `True` | Validate a pooled connection before use because SQL Server and intermediate firewalls can silently drop idle TCP sessions. |
| `pool_size` | `10` | Keep steady-state concurrent connections available. |
| `max_overflow` | `20` | Provide burst headroom with a hard ceiling of 30 total connections. |
| `pool_recycle` | `3600` | Recycle connections before common one-hour idle timeouts. |
| `pool_timeout` | `30` | Bound the wait for a pooled connection instead of blocking a request thread indefinitely under exhaustion. |
| `connect_args["timeout"]` | `10` seconds | Bound the pyodbc login wait so readiness fails fast for a dead or unreachable server. |

The existing SQL echo gate remains disabled in production. `fast_executemany` is
deliberately not enabled: it changes pyodbc parameter binding and has known
large-`NVARCHAR`/`DECIMAL` truncation and typing pitfalls, while this codebase has no
bulk-insert path. A custom isolation level is also deliberately absent; SQL Server's
default `READ COMMITTED` is correct for this workload and changing it would be a
behavioral change. An engine-level statement/query timeout is deferred: pyodbc's
`timeout` attribute is a connection-level query timeout with driver-specific behavior,
so this slice only sets the explicitly bounded login timeout and does not guess at
query-timeout semantics.

## Session lifecycle and transaction ownership

`SessionLocal` keeps `autocommit=False` and `autoflush=False`. `get_db()` creates one
session per dependency invocation, yields it, rolls it back on any consumer exception,
re-raises the original exception, and always closes the session. It never commits.

The caller or service that owns a write owns its commit and may commit exactly once for
that unit of work. Read paths do not commit. There is no shared global session and no
nested-transaction machinery in this slice. Worker session handling is unchanged and
is deferred to DB-2 if it needs the same policy.

SQLAlchemy's default `expire_on_commit=True` is retained. Existing write paths explicitly
commit and, where they need values after commit, explicitly refresh their ORM object;
the repository-wide usage was not verified sufficiently to justify changing the default
and potentially changing post-commit refresh behavior or detached-instance handling.

## Transient-error policy

`DatabaseFailureKind` and `classify_database_error()` only classify errors; no existing
application call site is wrapped in a retry. The classification is intentionally
conservative:

| Signal | Classification |
| --- | --- |
| SQLAlchemy `DisconnectionError` | `TRANSIENT` |
| SQLAlchemy pool `TimeoutError` or SQL Server number `-2` | `TIMEOUT` |
| SQL Server error number `1205` | `DEADLOCK` |
| SQLAlchemy `IntegrityError` | `INTEGRITY` |
| SQLAlchemy `ProgrammingError` | `PROGRAMMING` |
| SQL Server connection/transient numbers `4060`, `40197`, `40501`, `40613`, `49918`, `49919`, `49920`, `10928`, `10929`, `233`, or `64` when present in an `OperationalError` | `TRANSIENT` |
| Unrecognised errors/numbers | `UNKNOWN` |

An `OperationalError` with SQLAlchemy's `connection_invalidated` flag is also treated
as transient; an unrecognised `OperationalError` remains unknown rather than being
guessed. The SQLAlchemy exception hierarchy and wrapped DB-API error contract are
documented in the [SQLAlchemy Core exceptions reference](https://docs.sqlalchemy.org/en/20/core/exceptions.html).
The Azure SQL transient-code portion of the mapping follows Microsoft's [transient
error reference](https://learn.microsoft.com/en-us/azure/azure-sql/database/troubleshoot-common-errors-issues?view=azuresql);
the connection codes are cross-checked against Microsoft's [SQL Server connectivity
guidance](https://learn.microsoft.com/en-us/troubleshoot/sql/database-engine/connect/network-related-or-instance-specific-error-occurred-while-establishing-connection)
and [SQL Server deadlock guidance](https://learn.microsoft.com/en-us/sql/connect/golang/error-handling?view=sql-server-ver17).
The [SQL Server error reference](https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/errors-and-events-reference-database-engine?view=sql-server-ver17)
also documents the network error represented by 64.

`retry_idempotent()` is a bounded, exponential-backoff helper with a default of three
attempts. Callers **must** roll back transaction state before each retry. Only
`TRANSIENT`, `TIMEOUT`, and `DEADLOCK` are retryable; `INTEGRITY`, `PROGRAMMING`, and
`UNKNOWN` are never retried. It must never be used for user creation, permission
assignment, artifact creation, job submission, or any write without an idempotency key.
No application code calls this helper in DB-1.

## SQL Server 2025 warning assessment

The pinned SQLAlchemy 2.0.25 SQL Server dialect warns when the reported major version
is outside `range(8, 17)`. SQL Server 2025 reports major version 17, so this is an
advisory upper-bound warning. The functional dialect gates in this version are
lower-bound checks: multivalue inserts require at least SQL Server 2008, large-type
deprecation requires at least SQL Server 2012, and `OFFSET/FETCH` requires major
version 11. All remain true for major version 17; the version-range warning is the only
upper-bound gate identified.

No SQLAlchemy upgrade, requirements change, or warning filter was made. Suppressing the
warning would also hide a genuinely unsupported future version. Re-check this finding
when SQLAlchemy is next upgraded for an unrelated reason.

## Readiness behavior

`/health/ready` reports only `status`, `dialect`, and `migration`. It first performs the
existing connectivity probe. If the database is reachable, it loads the expected
single Alembic head from local `ScriptDirectory` files and issues one plain
`SELECT version_num FROM alembic_version`:

- `current`: the single stored revision equals the single script head;
- `behind`: the table is readable but empty, branched, or does not contain the head;
- `unmanaged`: the revision table is absent;
- `unavailable`: Alembic files/configuration cannot be loaded or the revision query
  fails for a reason other than a missing table.

The readiness path performs no DDL, DML, Alembic upgrade, or stamp operation and does
not expose connection details, SQL text, credentials, or tracebacks. A connectivity
failure remains an HTTP 503 with a safe degraded response.
