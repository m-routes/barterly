"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { VerificationChip } from "@/components/ui/StatusChip";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import type { Property, VerificationStatus } from "@/lib/api/types";
import { verificationGaps } from "@/lib/validation/property";

const CAN_SUBMIT: ReadonlySet<VerificationStatus> = new Set([
  "not_started",
  "changes_requested",
  "rejected",
  "expired",
]);

const STATUS_TEXT: Partial<Record<VerificationStatus, string>> = {
  submitted: "We have your request and will check it within two working days.",
  in_review: "Our team is checking the location and photos.",
  approved: "Talent see a Property verified badge on this property's gigs.",
  changes_requested: "Our team asked for changes. Fix them below, then send it again.",
  rejected: "This property wasn't approved. Check the details and send it again.",
  expired: "Verification has expired. Send it again to keep the badge.",
};

/** Ask Barterly to verify the property: the pin plus geo-tagged photos taken near it. */
export function PropertyVerification({
  property,
  onStatus,
}: {
  property: Property;
  onStatus: (status: VerificationStatus) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  const status = property.verification_status;
  const gaps = verificationGaps(property);
  const canSubmit = CAN_SUBMIT.has(status);

  async function submit() {
    setBusy(true);
    setProblems([]);
    try {
      const result = await unwrap(
        api.POST("/api/v1/properties/{property_id}/verification/", {
          params: { path: { property_id: property.id } },
        }),
      );
      onStatus(result.status);
    } catch (error) {
      const byField = error instanceof ApiError ? fieldErrors(error) : {};
      const messages = Object.values(byField);
      setProblems(messages.length ? messages : [describeError(error)]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel stack" aria-labelledby="property-verification-title">
      <div className="panel__header panel__header--row">
        <h2 id="property-verification-title" className="panel__title">
          Verification
        </h2>
        <VerificationChip status={status} />
      </div>
      {STATUS_TEXT[status] ? <p>{STATUS_TEXT[status]}</p> : null}
      {canSubmit ? (
        <>
          {gaps.length ? (
            <div>
              <p className="field__label">Before you send it:</p>
              <ul className="todo-list">
                {gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p>Everything&apos;s in place. Send the property for verification.</p>
          )}
          {problems.length ? (
            <ul className="form-error" role="alert">
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          ) : null}
          <div>
            <Button
              onClick={() => void submit()}
              busy={busy}
              busyLabel="Sending…"
              disabled={gaps.length > 0}
            >
              Request verification
            </Button>
          </div>
        </>
      ) : null}
    </section>
  );
}
