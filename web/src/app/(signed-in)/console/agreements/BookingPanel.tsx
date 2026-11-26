"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Chip, type ChipTone } from "@/components/ui/StatusChip";
import { FormError, SelectField, TextArea } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type {
  Agreement,
  BookingStatus,
  CancelPreview,
  CancellationReason,
  Unlocked,
} from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";

/** "1 day", "7 days". */
const days = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;

export const BOOKING_STATUS: Record<BookingStatus, { label: string; tone: ChipTone }> = {
  signing: { label: "Awaiting signatures", tone: "pending" },
  confirmed: { label: "Confirmed", tone: "success" },
  checked_in: { label: "Checked in", tone: "success" },
  delivering: { label: "Delivering", tone: "success" },
  completed: { label: "Completed", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "danger" },
  no_show: { label: "No-show", tone: "danger" },
  disputed: { label: "Disputed", tone: "warning" },
  refunded: { label: "Refunded", tone: "neutral" },
  reviewed: { label: "Reviewed", tone: "neutral" },
};

const UNLOCKED: ReadonlyArray<BookingStatus> = ["confirmed", "checked_in", "delivering"];
const CANCELLABLE: ReadonlyArray<BookingStatus> = ["signing", "confirmed"];

/** The booking behind an agreement: its status, the talent's phone once both have signed,
 * and cancelling before check-in. */
export function BookingPanel({
  agreement,
  onChange,
}: {
  agreement: Agreement;
  onChange: () => void;
}) {
  const status = agreement.booking_status;
  const { label, tone } = BOOKING_STATUS[status];
  return (
    <section className="panel stack-sm" aria-labelledby="booking-title">
      <div className="panel__header panel__header--row">
        <h2 id="booking-title" className="panel__title">
          Booking
        </h2>
        <Chip tone={tone}>{label}</Chip>
      </div>
      {status === "signing" ? (
        <p className="field__hint">
          The place is taken, and the contact details shared, once both of you have signed.
        </p>
      ) : null}
      {UNLOCKED.includes(status) ? <Contacts bookingId={agreement.booking} /> : null}
      {CANCELLABLE.includes(status) ? (
        <CancelBooking bookingId={agreement.booking} onCancelled={onChange} />
      ) : null}
    </section>
  );
}

function Contacts({ bookingId }: { bookingId: string }) {
  const { state } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/bookings/{booking_id}/details/", {
          params: { path: { booking_id: bookingId } },
        }),
      ),
    bookingId,
  );
  if (state.status === "loading") return <p className="field__hint">Loading contact details…</p>;
  if (state.status === "error") return <FormError message={describeError(state.error)} />;
  const details: Unlocked = state.data;
  return (
    <dl className="summary">
      <div>
        <dt>Talent</dt>
        <dd>
          {details.talent.name}, <a href={`tel:${details.talent.phone}`}>{details.talent.phone}</a>{" "}
          <span className="field__hint">(verified by OTP)</span>
        </dd>
      </div>
    </dl>
  );
}

function CancelBooking({ bookingId, onCancelled }: { bookingId: string; onCancelled: () => void }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <div className="actions-row actions-row--start">
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Cancel this booking
        </Button>
      </div>
    );
  }
  return (
    <CancelForm bookingId={bookingId} onClose={() => setOpen(false)} onCancelled={onCancelled} />
  );
}

const EFFECT_TEXT: Record<CancelPreview["effect"], string> = {
  none: "This won't affect your reliability score.",
  free: "You're before the notice period: this won't affect your reliability score.",
  late: "You're inside the notice period: this counts as a late cancellation on your reliability score.",
  last_minute:
    "The stay is a day away or less: this counts as a last-minute cancellation on your reliability score.",
};

function CancelForm({
  bookingId,
  onClose,
  onCancelled,
}: {
  bookingId: string;
  onClose: () => void;
  onCancelled: () => void;
}) {
  const path = { params: { path: { booking_id: bookingId } } };
  const { state } = useLoad(
    () => unwrap(api.GET("/api/v1/bookings/{booking_id}/cancel/", path)),
    bookingId,
  );
  const [reason, setReason] = useState<CancellationReason | "">("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (state.status === "loading") return <p className="field__hint">Checking the policy…</p>;
  if (state.status === "error") return <FormError message={describeError(state.error)} />;
  const preview = state.data;
  const needsNote = reason === "other" && !note.trim();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!reason) return;
    setBusy(true);
    setError("");
    try {
      await unwrap(
        api.POST("/api/v1/bookings/{booking_id}/cancel/", { ...path, body: { reason, note } }),
      );
      onCancelled();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack-sm" onSubmit={(e) => void submit(e)} noValidate>
      <h3 className="panel__title">Cancel this booking</h3>
      <p
        className={
          preview.effect === "late" || preview.effect === "last_minute"
            ? "note note--warning"
            : "field__hint"
        }
      >
        {EFFECT_TEXT[preview.effect]}
        {preview.notice_days != null
          ? ` The agreement's policy is ${preview.policy}: ${days(preview.notice_days)}' notice; the stay starts in ${days(preview.days_before_start)}.`
          : ""}
      </p>
      <SelectField
        label="Reason"
        options={preview.reasons.map((r) => ({ value: r.code, label: r.label }))}
        value={reason}
        onChange={(e) => setReason(e.target.value as CancellationReason)}
      />
      <TextArea
        label="More about why"
        optional={reason !== "other"}
        maxLength={1000}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <FormError message={error} />
      <div className="actions-row actions-row--start">
        <Button type="submit" busy={busy} disabled={!reason || needsNote}>
          Cancel the booking
        </Button>
        <Button variant="ghost" disabled={busy} onClick={onClose}>
          Keep it
        </Button>
      </div>
    </form>
  );
}
