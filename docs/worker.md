# REDSEA Worker — Reference (Python)

External Python service that processes jobs queued by the web app.

## Contract

The web app exposes two **public, HMAC-protected** endpoints:

- `POST /api/public/hooks/worker-poll` — claim the oldest queued job (atomic).
- `POST /api/public/hooks/worker-callback` — stream progress / logs / finalize result.

Base URL (stable):
- Production: `https://project--0d19a868-5f9d-4bb7-931b-bb0c1f72c7c5.lovable.app`
- Preview:    `https://project--0d19a868-5f9d-4bb7-931b-bb0c1f72c7c5-dev.lovable.app`

## Auth: HMAC-SHA256

Shared secret: `WORKER_HMAC_SECRET` (already set in Lovable Cloud).
Set the **same** value as an env var on the worker.

### Poll signing
```
sig = hex(hmac_sha256(secret, ts))
```
Headers: `x-worker-id`, `x-worker-ts` (unix ms), `x-worker-sig`.
Drift window: ±60 seconds.

### Callback signing
```
sig = hex(hmac_sha256(secret, f"{ts}.{raw_body}"))
```
Headers: `x-worker-ts`, `x-worker-sig`.

## Job payload

`worker-poll` returns:
```json
{ "job": {
  "id": "uuid",
  "module_key": "task_extractor",
  "input_refs": { "upload_ids": ["uuid", ...] },
  "project_id": "uuid|null",
  "created_by": "uuid"
}}
```
Or `{ "job": null }` when the queue is empty.

## Module keys → handlers

| module_key       | inputs (kind)     | outputs                       |
|------------------|-------------------|-------------------------------|
| task_extractor   | pdf               | tasks rows + xlsx/json export |
| task_stamping    | pdf               | stamped pdfs                  |
| effectivity      | excel/csv         | normalized export             |
| check_control    | csv/excel         | checks table rows             |
| utilization      | excel/csv         | utilization rows + hashes     |
| cmp_tcm          | pdf               | tcm_index rows + task cards   |
| cover_merge      | pdf (≥2)          | merged pdf                    |
| mail_merge       | docx + excel      | RC Cards pdfs                 |

## Minimal worker loop (Python)

```python
import os, time, hmac, hashlib, json, requests

BASE   = os.environ["REDSEA_BASE_URL"]
SECRET = os.environ["WORKER_HMAC_SECRET"].encode()
WID    = os.environ.get("WORKER_ID", "worker-1")

def sign(msg: bytes) -> str:
    return hmac.new(SECRET, msg, hashlib.sha256).hexdigest()

def poll():
    ts = str(int(time.time() * 1000))
    r = requests.post(f"{BASE}/api/public/hooks/worker-poll",
        headers={"x-worker-id": WID, "x-worker-ts": ts, "x-worker-sig": sign(ts.encode())},
        timeout=15)
    r.raise_for_status()
    return r.json().get("job")

def callback(payload: dict):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    ts  = str(int(time.time() * 1000))
    sig = sign(f"{ts}.".encode() + raw)
    requests.post(f"{BASE}/api/public/hooks/worker-callback",
        data=raw,
        headers={"content-type": "application/json",
                 "x-worker-ts": ts, "x-worker-sig": sig},
        timeout=15).raise_for_status()

def run(job):
    jid = job["id"]
    callback({"jobId": jid, "progress": 5, "logMessage": f"start {job['module_key']}"})
    try:
        # 1. download uploads via Supabase signed URLs
        # 2. dispatch by module_key → run extraction / stamping / etc.
        # 3. upload outputs to Supabase Storage (bucket: outputs)
        callback({"jobId": jid, "status": "done", "progress": 100,
                  "outputRefs": {"files": ["outputs/.../result.pdf"]}})
    except Exception as e:
        callback({"jobId": jid, "status": "failed", "error": str(e)[:4000]})

if __name__ == "__main__":
    while True:
        j = poll()
        if j: run(j)
        else: time.sleep(3)
```

## Supabase storage access

The worker needs `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` to:
1. Read `uploads` rows for `storage_path`.
2. Create signed URLs (or download directly) from the `uploads` bucket.
3. Upload results to the `outputs` bucket under `{user_id}/{job_id}/...`.

> Note: service role key isn't available on Lovable Cloud. Use a separate
> Supabase project for the worker, or wire the worker to read inputs through
> signed URLs returned by the web app in a future callback (e.g. `/api/public/hooks/worker-fetch-input`).

## Deployment

Railway / Fly.io / Render. Env vars required:
- `REDSEA_BASE_URL`
- `WORKER_HMAC_SECRET`
- `WORKER_ID`
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (optional, depending on input-fetch strategy)
