# Docker deployment (2026-09-03)

Two images, one origin:

| Image | Built from | Runs |
|---|---|---|
| `web` | `Dockerfile.web` | nginx serving the prerendered SPA from `dist/client` and proxying `/api/*` and `/health/*` to the API |
| `api` | `Dockerfile` | uvicorn + FastAPI, Alembic on start, Tesseract and the SQL Server ODBC driver installed |
| `worker` | `Dockerfile` (entrypoint `python -m worker.runner`) | claims jobs from the `jobs` table and runs each in a killable child process |

The browser only ever talks to `web`. Because `/api` is same-origin, CORS is
out of the request path entirely; `CORS_ORIGINS` only matters for tools that
call the API port directly.

## Run locally

```bash
cd accessforge-cloud-main/accessforge-cloud-main && docker compose up --build
```

Then open http://localhost:8080. Defaults: `APP_ENV=development`, SQLite at
`/data/app.db` inside the `data` volume (the bootstrap tool refuses a file
named `redsea.db` by policy), uploads under `/data/storage`.
Compose reads `.env` in this directory for variable interpolation. The
database is the one exception: set `COMPOSE_DATABASE_URL` to override the
in-volume SQLite default, because the developer `.env` points `DATABASE_URL`
at a host-relative file that would not live in the volume.

First admin account (once, against the running container):

```bash
docker compose exec api python -m backend.tools.bootstrap_admin --email you@redseaairlines.com
```

## Production

Set these in the environment of the `api` service (never in the image):

| Variable | Notes |
|---|---|
| `APP_ENV=production` | The API refuses SQLite and wildcard CORS in this mode |
| `DATABASE_URL` | `mssql+pyodbc://user:pass@host/db?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes` (Driver 18 encrypts by default; drop `TrustServerCertificate` once the server has a trusted certificate) |
| `JWT_SECRET_KEY` | 32+ characters |
| `WEB_CONCURRENCY` | uvicorn workers. Note the login rate limiter is per process; the persistent lockout in the DB is the real control |
| `RUN_MIGRATIONS` | `1` (default) runs `alembic upgrade head` at start. Set `0` and run it once from the pipeline when scaling to several replicas |
| `ARTIFACT_STORAGE_DIR` | Defaults to `/data/storage`; mount persistent storage there |

Build the API without the Microsoft driver for a lighter development image:

```bash
docker compose build --build-arg INSTALL_MSSQL_DRIVER=0 api
```

## Health

- `GET /health/live` answers as soon as the process is up.
- `GET /health/ready` checks the database and reports the Alembic state; `web` waits for the API health check before it starts.

## Job execution

With `JOB_EXECUTION_MODE=worker` (set on the `api` service) `POST /api/jobs`
only inserts a `queued` row. The `worker` service claims rows with an
optimistic UPDATE that stamps a lease token, runs the job in a child process,
heartbeats the lease, and fences every write on the token:

| Variable (worker) | Default | Meaning |
|---|---|---|
| `JOB_LEASE_SECONDS` | 120 | A claim without a heartbeat for this long is reclaimable |
| `JOB_HEARTBEAT_SECONDS` | 30 | Lease extension interval while the child runs |
| `JOB_TIMEOUT_SECONDS` | 3600 | Wall-clock cap per attempt; the process tree is killed past it |
| `JOB_MAX_ATTEMPTS` | 3 | Claims (first run + reclaims) before a job whose workers keep dying is failed |
| `JOB_POLL_SECONDS` | 2 | Idle poll interval |

Semantics, stated honestly: **at-least-once**. A job whose worker died is run
again by whoever reclaims it, so handlers must tolerate re-execution; a
crash between persisting output files and the fenced row update leaves
orphan files, never a row pointing at missing files. `POST
/api/jobs/{id}/cancel` cancels a queued job at once and flags a running one
for the worker to kill; `POST /api/jobs/{id}/retry` requeues a failed or
cancelled job. `docker compose stop worker` gives the running job
`stop_grace_period` to finish, then it is released back to the queue.

Scale with `docker compose up --scale worker=3`: claims are atomic, so
replicas never execute the same job at the same time. Size by the machine,
though: each child runs the toolkit's own thread pool and Tesseract processes.

Not verified here: the claim path under SQL Server contention (only SQLite
was available). The correctness argument is the single-row conditional
UPDATE plus rowcount check, which both engines honour; SQL Server lock hints
(`READPAST`) are a throughput tuning that would need a real instance to test.

Set `JOB_EXECUTION_MODE=inline` (the default outside compose) to run jobs
inside the API process as before — fine for one developer, not for production.

## Known limits

- The login rate limiter lives in process memory; with `WEB_CONCURRENCY>1` it
  is per worker. Persistent lockout (`failed_login_count`) still applies.
- Output files have no relational home yet (TECHNICAL_DEBT #2); the
  orphan-file window above closes when they do.
