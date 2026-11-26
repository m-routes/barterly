import { api, unwrap } from "@/lib/api/client";

import type { AttendanceStore, Outcome } from "./store";

/**
 * Send queued check-ins. Applied, duplicate (already checked in) and refused ones all
 * leave the queue; refused ones are kept as outcomes to show the host why. A network
 * failure leaves everything queued for next time.
 */
export async function flush(store: AttendanceStore, now = new Date()): Promise<Outcome[]> {
  const queued = await store.queued();
  if (queued.length === 0) return [];
  const names = new Map(queued.map((q) => [q.client_id, q.talent_name]));
  const { results } = await unwrap(
    api.POST("/api/v1/attendance/sync/", {
      body: {
        events: queued.map((q) => ({
          client_id: q.client_id,
          booking_id: q.booking_id,
          method: q.method,
          token: q.token ?? "",
          code: q.code ?? "",
          reason: q.reason ?? "",
          scanned_at: q.scanned_at,
        })),
      },
    }),
  );
  const outcomes = results.map((r) => ({
    ...r,
    talent_name: names.get(r.client_id) ?? "",
    at: now.toISOString(),
  }));
  await store.remove(results.map((r) => r.client_id));
  await store.addOutcomes(outcomes);
  return outcomes;
}
