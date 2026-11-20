"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Chip } from "@/components/ui/StatusChip";
import { FormError, TextArea, TextField } from "@/components/ui/fields";
import { EmptyState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Arrival, Arrivals, InHouse, PendingHourLog } from "@/lib/api/types";
import { codeMatches, verifyPass, type Verified } from "@/lib/attendance/crypto";
import {
  defaultStore,
  type AttendanceStore,
  type Outcome,
  type QueuedCheckIn,
} from "@/lib/attendance/store";
import { flush } from "@/lib/attendance/sync";
import { formatDate } from "@/lib/format";

import { Scanner } from "./Scanner";

const SCAN_PROBLEMS: Record<Exclude<Verified, { ok: true }>["reason"], string> = {
  "not-a-pass": "That isn't a Barterly check-in pass.",
  "unknown-key": "This pass was signed with a key this device doesn't know. Go online to refresh.",
  "bad-signature": "This pass has been tampered with. Use the six-digit code or confirm by hand.",
  expired: "This pass has expired. Ask the talent to open it again while online.",
  "not-yet": "This pass isn't valid yet. Check this device's clock.",
};

const SYNC_EVERY_MS = 30_000;

function newId(): string {
  return (
    globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
  );
}

function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

/**
 * The host's arrivals screen. It keeps the day's arrivals and the signing keys on the
 * device, checks passes and codes without a connection, queues check-ins, and syncs
 * them when it's back online. Check-out, no-shows and hours need a connection.
 */
export function ArrivalsPage({
  store: given,
  clock = () => new Date(),
}: {
  store?: AttendanceStore;
  clock?: () => Date;
}) {
  const store = useMemo(() => given ?? defaultStore(), [given]);
  const [day, setDay] = useState<Arrivals | null | undefined>(undefined);
  const [queued, setQueued] = useState<QueuedCheckIn[]>([]);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [scanning, setScanning] = useState(false);
  const [codeFor, setCodeFor] = useState<Arrival | null>(null);
  const [manualFor, setManualFor] = useState<Arrival | null>(null);
  const [noShowFor, setNoShowFor] = useState<Arrival | null>(null);
  const clockRef = useRef(clock);
  useEffect(() => {
    clockRef.current = clock;
  });

  const refreshDay = useCallback(async () => {
    try {
      const fresh = await unwrap(api.GET("/api/v1/attendance/arrivals/"));
      await store.setDay(fresh);
      setDay(fresh);
    } catch {
      // Offline or failing: keep showing the cached day.
    }
  }, [store]);

  const syncNow = useCallback(async () => {
    setSyncing(true);
    try {
      const results = await flush(store, clockRef.current());
      if (results.length) {
        const refused = results.filter((r) => r.status === "refused");
        setNotice(
          refused.length
            ? { tone: "error", text: `${refused.length} check-in(s) were refused. See below.` }
            : { tone: "ok", text: `Synced ${results.length} check-in(s).` },
        );
        await refreshDay();
      }
    } catch {
      // Still offline: everything stays queued.
    } finally {
      setQueued(await store.queued());
      setOutcomes(await store.outcomes());
      setSyncing(false);
    }
  }, [store, refreshDay]);

  useEffect(() => {
    void navigator.serviceWorker?.register("/sw.js").catch(() => undefined);
  }, []);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const [cached, waiting, past] = await Promise.all([
        store.getDay(),
        store.queued(),
        store.outcomes(),
      ]);
      if (!alive) return;
      setDay(cached);
      setQueued(waiting);
      setOutcomes(past);
      const isOnline = typeof navigator === "undefined" || navigator.onLine !== false;
      setOnline(isOnline);
      if (isOnline) {
        await refreshDay();
        await syncNow();
      }
      if (alive) setDay((d) => d ?? null);
    })();
    const up = () => {
      setOnline(true);
      void syncNow();
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    const timer = window.setInterval(() => {
      if (navigator.onLine !== false) void syncNow();
    }, SYNC_EVERY_MS);
    return () => {
      alive = false;
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
      window.clearInterval(timer);
    };
  }, [store, refreshDay, syncNow]);

  const queuedBookings = new Set(queued.map((q) => q.booking_id));

  async function enqueue(
    arrival: Arrival,
    fields: Partial<QueuedCheckIn> & { method: QueuedCheckIn["method"] },
  ) {
    if (queuedBookings.has(arrival.booking_id)) {
      setNotice({ tone: "ok", text: `${arrival.talent_name} is already waiting to sync.` });
      return;
    }
    const item: QueuedCheckIn = {
      client_id: newId(),
      booking_id: arrival.booking_id,
      scanned_at: clockRef.current().toISOString(),
      talent_name: arrival.talent_name,
      ...fields,
    };
    await store.enqueue(item);
    setQueued(await store.queued());
    setNotice({
      tone: "ok",
      text: `${arrival.talent_name} checked in. It syncs when you're online.`,
    });
    if (navigator.onLine !== false) void syncNow();
  }

  async function onScan(text: string) {
    if (!day) return;
    const result = verifyPass(text, day.public_keys, clockRef.current(), day.clock_skew_seconds);
    if (!result.ok) {
      setNotice({ tone: "error", text: SCAN_PROBLEMS[result.reason] });
      return;
    }
    const arrival = day.arrivals.find((a) => a.booking_id === result.payload.b);
    if (!arrival) {
      setNotice({
        tone: "error",
        text: "This pass is genuine but not for today's arrivals here. Go online to refresh the list.",
      });
      return;
    }
    setScanning(false);
    await enqueue(arrival, { method: "qr", token: text.trim() });
  }

  if (day === undefined) return <LoadingState label="Loading arrivals…" />;

  const refused = outcomes.filter((o) => o.status === "refused");
  return (
    <div className="page stack">
      <header className="page__header arrivals__header">
        <div>
          <h1 className="page__title">Arrivals</h1>
          <p className="field__hint">
            {day
              ? `For ${formatDate(day.date)} · updated ${time(day.generated_at)}`
              : "Not loaded yet"}
          </p>
        </div>
        <div className="chip-row">
          <Chip tone={online ? "success" : "warning"}>{online ? "Online" : "Offline"}</Chip>
          {queued.length ? <Chip tone="pending">{`${queued.length} waiting to sync`}</Chip> : null}
          <Button
            variant="secondary"
            className="button--small"
            busy={syncing}
            busyLabel="Syncing…"
            disabled={!online}
            onClick={() => void syncNow().then(refreshDay)}
          >
            Sync now
          </Button>
        </div>
      </header>

      {notice ? (
        <p className={notice.tone === "error" ? "form-error" : "notice"} role="status">
          {notice.text}
        </p>
      ) : null}

      {!day ? (
        <EmptyState
          title="Go online once to get today's arrivals"
          description="The list, and what's needed to check passes, are kept on this device for when there's no signal."
        />
      ) : (
        <>
          <section className="panel stack-sm" aria-labelledby="expected-title">
            <div className="panel__header panel__header--row">
              <h2 id="expected-title" className="panel__title">
                Expected
              </h2>
              {day.arrivals.length ? (
                <Button onClick={() => setScanning((s) => !s)}>
                  {scanning ? "Close camera" : "Scan a pass"}
                </Button>
              ) : null}
            </div>
            {scanning ? (
              <Scanner onCode={(t) => void onScan(t)} onClose={() => setScanning(false)} />
            ) : null}
            {day.arrivals.length === 0 ? (
              <p className="field__hint">No one is due to check in today.</p>
            ) : (
              <ul className="card-list">
                {day.arrivals.map((a) => (
                  <ArrivalRow
                    key={a.booking_id}
                    arrival={a}
                    queued={queuedBookings.has(a.booking_id)}
                    online={online}
                    now={clock()}
                    onCode={() => setCodeFor(a)}
                    onManual={() => setManualFor(a)}
                    onNoShow={() => setNoShowFor(a)}
                  />
                ))}
              </ul>
            )}
          </section>

          {refused.length ? (
            <section className="panel stack-sm" aria-labelledby="refused-title">
              <h2 id="refused-title" className="panel__title">
                Check-ins that didn&apos;t go through
              </h2>
              <ul className="card-list">
                {refused.map((o) => (
                  <li key={o.client_id} className="card-list__item">
                    <div className="card-list__main">
                      <p className="card-list__title">{o.talent_name || "A check-in"}</p>
                      <p className="field__hint">{o.message}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <InHouseSection people={day.in_house} online={online} onChange={refreshDay} />
          {online ? <HoursToReview onChange={refreshDay} /> : null}
        </>
      )}

      {codeFor && day ? (
        <CodeDialog
          arrival={codeFor}
          check={(code) =>
            codeMatches(codeFor.code_secret, code, clockRef.current(), day.code_period_seconds)
          }
          onClose={() => setCodeFor(null)}
          onConfirmed={async (code) => {
            const arrival = codeFor;
            setCodeFor(null);
            await enqueue(arrival, { method: "code", code });
          }}
        />
      ) : null}
      {manualFor ? (
        <ManualDialog
          arrival={manualFor}
          onClose={() => setManualFor(null)}
          onConfirmed={async (reason) => {
            const arrival = manualFor;
            setManualFor(null);
            await enqueue(arrival, { method: "manual", reason });
          }}
        />
      ) : null}
      {noShowFor ? (
        <NoShowDialog
          arrival={noShowFor}
          onClose={() => setNoShowFor(null)}
          onDone={async () => {
            setNoShowFor(null);
            await refreshDay();
          }}
        />
      ) : null}
    </div>
  );
}

function ArrivalRow({
  arrival,
  queued,
  online,
  now,
  onCode,
  onManual,
  onNoShow,
}: {
  arrival: Arrival;
  queued: boolean;
  online: boolean;
  now: Date;
  onCode: () => void;
  onManual: () => void;
  onNoShow: () => void;
}) {
  const noShowOpen = now >= new Date(arrival.no_show_from);
  return (
    <li className="card-list__item">
      <div className="card-list__main">
        <p className="card-list__title">{arrival.talent_name}</p>
        <p className="card-list__meta">
          {arrival.gig_title} · {formatDate(arrival.start_date)} to {formatDate(arrival.end_date)}
        </p>
        {arrival.problem && !queued ? <p className="field__hint">{arrival.problem}</p> : null}
      </div>
      <div className="actions-row">
        {queued ? (
          <Chip tone="pending">Checked in · waiting to sync</Chip>
        ) : (
          <>
            {arrival.problem ? <Chip tone="warning">Not ready</Chip> : null}
            <Button variant="secondary" className="button--small" onClick={onCode}>
              Enter code
            </Button>
            <Button variant="ghost" className="button--small" onClick={onManual}>
              Confirm by hand
            </Button>
            <Button
              variant="ghost"
              className="button--small"
              disabled={!online || !noShowOpen}
              title={
                noShowOpen
                  ? undefined
                  : `You can mark a no-show from ${new Date(arrival.no_show_from).toLocaleString("en-IN")}`
              }
              onClick={onNoShow}
            >
              No-show
            </Button>
          </>
        )}
      </div>
    </li>
  );
}

function CodeDialog({
  arrival,
  check,
  onClose,
  onConfirmed,
}: {
  arrival: Arrival;
  check: (code: string) => boolean;
  onClose: () => void;
  onConfirmed: (code: string) => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  return (
    <Dialog
      title={`Code for ${arrival.talent_name}`}
      description="Ask them to read the six-digit code on their pass. It changes every few minutes."
      onClose={onClose}
      footer={
        <Button
          onClick={() => {
            if (!check(code)) {
              setError("That code isn't right, or it has changed. Ask for the current one.");
              return;
            }
            void onConfirmed(code.replace(/\D/g, ""));
          }}
        >
          Check in
        </Button>
      }
    >
      <TextField
        label="Six-digit code"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={7}
        value={code}
        error={error || undefined}
        onChange={(e) => {
          setCode(e.target.value);
          setError("");
        }}
      />
    </Dialog>
  );
}

function ManualDialog({
  arrival,
  onClose,
  onConfirmed,
}: {
  arrival: Arrival;
  onClose: () => void;
  onConfirmed: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  return (
    <Dialog
      title={`Confirm ${arrival.talent_name} by hand`}
      description="Only if their pass and code won't work. Say why; it's kept with the check-in."
      onClose={onClose}
      footer={
        <Button disabled={reason.trim().length < 3} onClick={() => void onConfirmed(reason.trim())}>
          Confirm arrival
        </Button>
      }
    >
      <TextArea
        label="Why"
        value={reason}
        maxLength={300}
        onChange={(e) => setReason(e.target.value)}
      />
    </Dialog>
  );
}

function NoShowDialog({
  arrival,
  onClose,
  onDone,
}: {
  arrival: Arrival;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Dialog
      title={`Mark ${arrival.talent_name} as a no-show?`}
      description="It counts against their reliability score. They can dispute it."
      onClose={onClose}
      footer={
        <Button
          busy={busy}
          disabled={reason.trim().length < 3}
          onClick={async () => {
            setBusy(true);
            try {
              await unwrap(
                api.POST("/api/v1/bookings/{booking_id}/attendance/no-show/", {
                  params: { path: { booking_id: arrival.booking_id } },
                  body: { reason: reason.trim() },
                }),
              );
              await onDone();
            } catch (e) {
              setError(describeError(e));
              setBusy(false);
            }
          }}
        >
          Mark no-show
        </Button>
      }
    >
      <TextArea label="What happened" value={reason} onChange={(e) => setReason(e.target.value)} />
      <FormError message={error} />
    </Dialog>
  );
}

function InHouseSection({
  people,
  online,
  onChange,
}: {
  people: InHouse[];
  online: boolean;
  onChange: () => Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  if (!people.length) return null;
  return (
    <section className="panel stack-sm" aria-labelledby="in-house-title">
      <h2 id="in-house-title" className="panel__title">
        Staying with you
      </h2>
      <FormError message={error} />
      <ul className="card-list">
        {people.map((p) => (
          <li key={p.booking_id} className="card-list__item">
            <div className="card-list__main">
              <p className="card-list__title">{p.talent_name}</p>
              <p className="card-list__meta">
                {p.gig_title} · until {formatDate(p.end_date)}
                {p.hours_to_review ? ` · ${p.hours_to_review} day(s) of hours to review` : ""}
              </p>
            </div>
            <Button
              variant="secondary"
              className="button--small"
              disabled={!online}
              busy={busy === p.booking_id}
              onClick={async () => {
                setBusy(p.booking_id);
                setError("");
                try {
                  await unwrap(
                    api.POST("/api/v1/bookings/{booking_id}/attendance/check-out/", {
                      params: { path: { booking_id: p.booking_id } },
                    }),
                  );
                  await onChange();
                } catch (e) {
                  setError(describeError(e));
                } finally {
                  setBusy(null);
                }
              }}
            >
              Check out
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function hoursLabel(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

function HoursToReview({ onChange }: { onChange: () => Promise<void> }) {
  const [logs, setLogs] = useState<PendingHourLog[] | null>(null);
  const [disputing, setDisputing] = useState<PendingHourLog | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const page = await unwrap(api.GET("/api/v1/attendance/hours/pending/"));
      setLogs(page.results);
    } catch {
      setLogs([]);
    }
  }, []);
  useEffect(() => {
    // Loading is this effect's job; its result is state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function review(log: PendingHourLog, confirm: boolean, note = "") {
    setError("");
    try {
      await unwrap(
        api.POST("/api/v1/hours/{log_id}/review/", {
          params: { path: { log_id: log.id } },
          body: { confirm, note },
        }),
      );
      setDisputing(null);
      await load();
      await onChange();
    } catch (e) {
      setError(describeError(e));
    }
  }

  if (!logs?.length) return null;
  return (
    <section className="panel stack-sm" aria-labelledby="hours-title">
      <h2 id="hours-title" className="panel__title">
        Hours to review
      </h2>
      <FormError message={error} />
      <ul className="card-list">
        {logs.map((log) => (
          <li key={log.id} className="card-list__item">
            <div className="card-list__main">
              <p className="card-list__title">
                {log.talent_name} · {formatDate(log.day)} · {hoursLabel(log.minutes)}
              </p>
              {log.note ? <p className="card-list__meta">{log.note}</p> : null}
            </div>
            <div className="actions-row">
              <Button className="button--small" onClick={() => void review(log, true)}>
                Confirm
              </Button>
              <Button variant="ghost" className="button--small" onClick={() => setDisputing(log)}>
                Dispute
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {disputing ? (
        <DisputeDialog
          log={disputing}
          onClose={() => setDisputing(null)}
          onSubmit={(note) => review(disputing, false, note)}
        />
      ) : null}
    </section>
  );
}

function DisputeDialog({
  log,
  onClose,
  onSubmit,
}: {
  log: PendingHourLog;
  onClose: () => void;
  onSubmit: (note: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  return (
    <Dialog
      title={`Dispute ${hoursLabel(log.minutes)} on ${formatDate(log.day)}?`}
      description={`${log.talent_name} is told why and can correct the log.`}
      onClose={onClose}
      footer={
        <Button disabled={!note.trim()} onClick={() => void onSubmit(note.trim())}>
          Dispute hours
        </Button>
      }
    >
      <TextArea
        label="What's wrong"
        value={note}
        maxLength={300}
        onChange={(e) => setNote(e.target.value)}
      />
    </Dialog>
  );
}
