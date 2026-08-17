# Local Setup for Frontend Development

Run the whole system on your machine against a **local, empty SQLite database**.
You do not need — and will not receive — any production credentials.

## Policy (read this first)

- Frontend work uses a **local database only**. Nobody receives the production
  connection string.
- If direct database access is ever genuinely needed, it is granted as a
  **separate read-only DB user** provisioned by the operator — never the
  application's credentials.
- API access to shared environments is granted by an admin **creating an
  account for you with the appropriate role** (viewer/engineer), not by
  sharing secrets.
- LEON credentials are likewise never shared: without them the Crew Hours
  module simply reports "LEON official report is not configured" (503), and
  everything else works. That is the expected local state.

## Prerequisites

Python 3.11+, Node 18+ (or Bun), git.

## 1) Clone and install

```bash
git clone https://github.com/fathy20/accessforge-cloud.git
cd accessforge-cloud/accessforge-cloud-main/accessforge-cloud-main   # note: nested app root

# Backend
python -m venv backend/venv
backend/venv/Scripts/pip install -r backend/requirements.txt         # Windows
# source backend/venv/bin/activate && pip install -r backend/requirements.txt  # POSIX

# Frontend
npm install
```

## 2) Configure .env (names only — generate your own values)

Create `.env` at the app root (same folder as `alembic.ini`). Required keys:

```
APP_ENV=development
DATABASE_URL=sqlite:///./redsea.db
JWT_SECRET_KEY=            # >= 32 chars: python -c "import secrets; print(secrets.token_urlsafe(48))"
VITE_API_URL=http://localhost:8000/api
CORS_ORIGINS=http://localhost:8080,http://localhost:5173
```

Do **not** set `SQL_SERVER_*` or `LEON_*` locally. Never commit `.env`.

## 3) Create the empty database (Alembic owns the schema)

```bash
python -m alembic upgrade head
```

## 4) Bootstrap the first admin

`backend/tools/bootstrap_admin.py` creates the one super-admin (refuses if one
exists). Password must be ≥ 12 characters.

```bash
python -m backend.tools.bootstrap_admin --email you@dev.local
# prompts for the password; or set BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD
```

## 5) Seed synthetic data (optional, recommended)

```bash
python -m backend.tools.seed_dev_data
```

Creates clearly-fake data: `dev-admin@dev.local`, `dev-engineer@dev.local`,
`dev-viewer@dev.local`, `dev-guest@dev.local` (shared local password printed by
the tool), 2 projects, 3 jobs in different states, 2 notifications. The tool
refuses to run against anything but a local SQLite development database, and
re-running is a no-op. There are **no flight/crew rows** — that data lives in
LEON, not this database.

## 6) Run

```bash
# Terminal 1 — backend on :8000
backend/venv/Scripts/python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend on :8080
npm run dev
```

Open http://localhost:8080 and sign in with your bootstrap admin or a seeded
account. Expected local behavior: Crew Hours and Copilot answer with "LEON is
not configured" — everything else is fully functional.

## Verify your setup

```bash
python -m pytest backend/tests/ -q     # backend suite
npx vitest run                          # frontend suite
```
