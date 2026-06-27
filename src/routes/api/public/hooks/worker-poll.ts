/**
 * Worker poll endpoint — claims the next queued job atomically.
 *
 * Caller: Python worker. Auth: HMAC over the timestamp using WORKER_HMAC_SECRET.
 * Headers:
 *   x-worker-id: <string>
 *   x-worker-ts: <unix ms>
 *   x-worker-sig: hex(hmacSha256(secret, ts))
 * Replay protection: ts must be within ±60s of server time.
 */
import { createFileRoute } from "@tanstack/react-router";
import { createHmac, timingSafeEqual } from "crypto";

function verify(req: Request): { ok: boolean; workerId?: string; error?: string } {
  const id = req.headers.get("x-worker-id");
  const ts = req.headers.get("x-worker-ts");
  const sig = req.headers.get("x-worker-sig");
  const secret = process.env.WORKER_HMAC_SECRET;
  if (!id || !ts || !sig || !secret) return { ok: false, error: "missing headers" };
  const drift = Math.abs(Date.now() - Number(ts));
  if (!Number.isFinite(drift) || drift > 60_000) return { ok: false, error: "stale timestamp" };
  const expected = createHmac("sha256", secret).update(ts).digest("hex");
  const a = Buffer.from(sig); const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return { ok: false, error: "bad signature" };
  return { ok: true, workerId: id };
}

export const Route = createFileRoute("/api/public/hooks/worker-poll")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const v = verify(request);
        if (!v.ok) return new Response(JSON.stringify({ error: v.error }), { status: 401, headers: { "content-type": "application/json" } });

        const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

        // Atomic claim via SQL: pick oldest queued, mark running.
        const { data: claimed, error } = await supabaseAdmin
          .from("jobs")
          .select("id")
          .eq("status", "queued")
          .order("created_at", { ascending: true })
          .limit(1)
          .maybeSingle();
        if (error) return new Response(JSON.stringify({ error: error.message }), { status: 500 });
        if (!claimed) return new Response(JSON.stringify({ job: null }), { status: 200, headers: { "content-type": "application/json" } });

        const { data: updated, error: uErr } = await supabaseAdmin
          .from("jobs")
          .update({ status: "running", started_at: new Date().toISOString(), worker_id: v.workerId, progress: 0 })
          .eq("id", claimed.id)
          .eq("status", "queued") // optimistic guard against double-claim
          .select("id, module_key, input_refs, project_id, created_by")
          .maybeSingle();
        if (uErr) return new Response(JSON.stringify({ error: uErr.message }), { status: 500 });
        if (!updated) return new Response(JSON.stringify({ job: null }), { status: 200 }); // raced

        return new Response(JSON.stringify({ job: updated }), { status: 200, headers: { "content-type": "application/json" } });
      },
    },
  },
});
