/**
 * Worker callback — update job progress, append logs, finalize result.
 * HMAC: hex(hmacSha256(secret, ts + "." + rawBody))
 * Body: { jobId, progress?, logLevel?, logMessage?, status?, error?, outputRefs? }
 */
import { createFileRoute } from "@tanstack/react-router";
import { createHmac, timingSafeEqual } from "crypto";
import { z } from "zod";

const schema = z.object({
  jobId: z.string().uuid(),
  progress: z.number().int().min(0).max(100).optional(),
  logLevel: z.enum(["info", "warn", "error"]).optional(),
  logMessage: z.string().max(4000).optional(),
  status: z.enum(["running", "done", "failed"]).optional(),
  error: z.string().max(4000).nullable().optional(),
  outputRefs: z.record(z.string(), z.unknown()).optional(),
});

export const Route = createFileRoute("/api/public/hooks/worker-callback")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const ts = request.headers.get("x-worker-ts");
        const sig = request.headers.get("x-worker-sig");
        const secret = process.env.WORKER_HMAC_SECRET;
        if (!ts || !sig || !secret) return new Response("missing headers", { status: 401 });
        const drift = Math.abs(Date.now() - Number(ts));
        if (!Number.isFinite(drift) || drift > 60_000) return new Response("stale", { status: 401 });

        const raw = await request.text();
        const expected = createHmac("sha256", secret).update(`${ts}.${raw}`).digest("hex");
        const a = Buffer.from(sig); const b = Buffer.from(expected);
        if (a.length !== b.length || !timingSafeEqual(a, b)) return new Response("bad signature", { status: 401 });

        let body: z.infer<typeof schema>;
        try { body = schema.parse(JSON.parse(raw)); }
        catch (e) { return new Response(`bad body: ${(e as Error).message}`, { status: 400 }); }

        const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

        if (body.logMessage) {
          await supabaseAdmin.from("job_logs").insert({
            job_id: body.jobId,
            level: body.logLevel ?? "info",
            message: body.logMessage,
          });
        }

        const patch: Record<string, unknown> = {};
        if (typeof body.progress === "number") patch.progress = body.progress;
        if (body.status) {
          patch.status = body.status;
          if (body.status === "done" || body.status === "failed") {
            patch.finished_at = new Date().toISOString();
          }
        }
        if (body.error !== undefined) patch.error = body.error;
        if (body.outputRefs) patch.output_refs = body.outputRefs;

        if (Object.keys(patch).length) {
          const { error } = await supabaseAdmin.from("jobs").update(patch).eq("id", body.jobId);
          if (error) return new Response(error.message, { status: 500 });
        }

        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      },
    },
  },
});
