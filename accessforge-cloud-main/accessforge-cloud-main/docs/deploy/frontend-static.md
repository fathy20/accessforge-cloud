# Frontend: static SPA build (2026-09-03)

The frontend no longer ships a Node/nitro server. `npx vite build` produces a
plain static site in `dist/client/` that any CDN, object store, or nginx can
serve. The backend (FastAPI) is the only long-running process.

## Why

Every authenticated route was already `ssr: false`, so the SSR server only ever
rendered the landing, sign-in, and reset-password pages. Keeping a second
server process (plus its error wrappers in `src/server.ts` / `src/start.ts`)
for three public pages cost deployment complexity and a cold Node start on
every request path, and bought nothing users could see.

## What the build emits

| File | Purpose |
|---|---|
| `dist/client/index.html` | Landing page, fully prerendered HTML |
| `dist/client/auth/index.html`, `reset-password/index.html` | Public pages, prerendered |
| `dist/client/_shell.html` | The SPA shell: root layout + scripts, no route content |
| `dist/client/<route>/index.html` | One copy of the shell per static route path (except `/dashboard`, which *is* the shell), so deep links load even on hosts with no rewrite rules |
| `dist/client/assets/*` | Hashed JS/CSS chunks, cache forever |
| `dist/server/` | Used only by the prerender step at build time. Do not deploy. |

Configuration lives in `vite.config.ts`: `nitro: false`, `tanstackStart.spa`,
`tanstackStart.prerender`, and `pages`.

## API origin

`ApiClient.API_URL` defaults to the relative path `/api`. The Vite dev server
proxies `/api` to `DEV_API_ORIGIN` (default `http://localhost:8000`), and the
production reverse proxy must do the same. Because the browser talks to one
origin, CORS is not involved. Set `VITE_API_URL` only if the API is genuinely
served from a different origin.

## Minimal nginx

The containerised version of this (with envsubst for the upstream) is
`deploy/web/default.conf.template`; see `docker.md`.

```nginx
server {
    listen 80;
    root /srv/redsea/dist/client;

    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;   # large uploads / exports
        client_max_body_size 120m; # backend MAX_UPLOAD_SIZE is 100 MB
    }

    location / {
        try_files $uri $uri/index.html /_shell.html;
    }
}
```

## Local verification

```bash
cd accessforge-cloud-main/accessforge-cloud-main && npx vite build && python -m http.server 8081 --directory dist/client
```

The landing and auth pages must render with JavaScript disabled; authenticated
routes redirect to `/auth` once the client bundle runs.
