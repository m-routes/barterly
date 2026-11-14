"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormError, SelectField, TextField } from "@/components/ui/fields";
import { Chip, VerificationChip } from "@/components/ui/StatusChip";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import type { CheckSummary, IdDocumentType, MyVerification } from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";
import { checkStatus, latestCase } from "@/lib/vendor/checklist";
import { BADGE_LABELS, ID_DOCUMENT_LABELS, options } from "@/lib/vendor/labels";

const DOCUMENT_OPTIONS = options(ID_DOCUMENT_LABELS);
const STARTABLE = new Set(["not_started", "rejected", "changes_requested", "expired"]);

/** Start the ID and selfie check; the provider's page does the rest. */
function IdCheck({ check, onStarted }: { check: CheckSummary; onStarted: () => void }) {
  const [documentType, setDocumentType] = useState<IdDocumentType | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [continueUrl, setContinueUrl] = useState<string | null>(null);
  const status = checkStatus(check);

  async function start() {
    if (!documentType) {
      setError("Choose the document you'll use.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await unwrap(
        api.POST("/api/v1/verification/checks/id/", { body: { document_type: documentType } }),
      );
      setContinueUrl(result.session.redirect_url);
      onStarted();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  if (continueUrl) {
    return (
      <div className="stack-sm">
        <p>
          Your ID check is ready. Have your document with you; it takes about five minutes on our
          verification partner&apos;s site.
        </p>
        <div>
          <a className="button button--primary" href={continueUrl} rel="noopener">
            Continue to the ID check
          </a>
        </div>
      </div>
    );
  }
  if (!STARTABLE.has(status)) return null;
  return (
    <div className="stack-sm">
      <SelectField
        label="Document"
        options={DOCUMENT_OPTIONS}
        value={documentType}
        error={error && !documentType ? error : undefined}
        onChange={(e) => setDocumentType(e.target.value as IdDocumentType | "")}
      />
      {error && documentType ? <FormError message={error} /> : null}
      <div>
        <Button onClick={() => void start()} busy={busy} busyLabel="Starting…">
          {status === "not_started" ? "Start ID check" : "Start again"}
        </Button>
      </div>
    </div>
  );
}

/** PAN (and GSTIN if registered), checked against the tax records. */
function BusinessCheck({ check, onDone }: { check: CheckSummary; onDone: () => void }) {
  const [pan, setPan] = useState("");
  const [gstin, setGstin] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  if (!STARTABLE.has(checkStatus(check))) return null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const cleanPan = pan.trim().toUpperCase();
    if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(cleanPan)) {
      setErrors({ pan: "Enter the 10-character PAN, e.g. ABCDE1234F." });
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      await unwrap(
        api.POST("/api/v1/verification/checks/business/", {
          body: { pan: cleanPan, gstin: gstin.trim().toUpperCase() },
        }),
      );
      onDone();
    } catch (err) {
      const byField = err instanceof ApiError ? fieldErrors(err) : {};
      setErrors(Object.keys(byField).length ? byField : { root: describeError(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack-sm" onSubmit={(e) => void submit(e)} noValidate>
      <div className="form-grid">
        <TextField
          label="PAN"
          value={pan}
          maxLength={10}
          autoCapitalize="characters"
          spellCheck={false}
          error={errors.pan}
          onChange={(e) => setPan(e.target.value)}
        />
        <TextField
          label="GSTIN"
          optional
          value={gstin}
          maxLength={15}
          autoCapitalize="characters"
          spellCheck={false}
          error={errors.gstin}
          onChange={(e) => setGstin(e.target.value)}
        />
      </div>
      <FormError message={errors.root} />
      <div>
        <Button type="submit" busy={busy} busyLabel="Sending…">
          Send for checking
        </Button>
      </div>
    </form>
  );
}

function CheckRow({ check, reload }: { check: CheckSummary; reload: () => void }) {
  const status = checkStatus(check);
  const reason = latestCase(check)?.reason;
  return (
    <li className="check-row">
      <div className="check-row__header">
        <div>
          <h3 className="check-row__title">{check.label}</h3>
          <p className="field__hint">
            {check.required ? "Required" : "Optional"} · earns the {BADGE_LABELS[check.badge]} badge
          </p>
        </div>
        <VerificationChip status={status} />
      </div>
      {reason && (status === "rejected" || status === "changes_requested") ? (
        <p className="check-row__reason">{reason}</p>
      ) : null}
      {check.check_type === "id_selfie" ? <IdCheck check={check} onStarted={reload} /> : null}
      {check.check_type === "business_registration" ? (
        <BusinessCheck check={check} onDone={reload} />
      ) : null}
      {check.check_type === "property" ? (
        <p>
          Each property is verified on its own page.{" "}
          <Link href="/console/properties">Go to your properties</Link>
        </p>
      ) : null}
    </li>
  );
}

export function VerificationPage() {
  const { state, reload, refresh } = useLoad<MyVerification>(
    () => unwrap(api.GET("/api/v1/verification/me/")),
    "verification",
  );

  return (
    <div className="page page--narrow">
      <header className="page__header">
        <h1 className="page__title">Verification</h1>
        <p className="page__lead">
          Verified hosts get badges on their gigs. We never show your documents to talent.
        </p>
      </header>
      {state.status === "loading" ? <LoadingState label="Loading your verification…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your verification"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" ? (
        <div className="stack">
          <section className="panel" aria-labelledby="badges-title">
            <h2 id="badges-title" className="panel__title">
              Your badges
            </h2>
            {state.data.badges.length ? (
              <div className="chip-row">
                {state.data.badges.map((b) => (
                  <Chip key={b.kind} tone="success">
                    {BADGE_LABELS[b.kind]}
                  </Chip>
                ))}
              </div>
            ) : (
              <p className="field__hint">No badges yet. Finish a check below to earn one.</p>
            )}
          </section>
          <section className="panel" aria-labelledby="checks-title">
            <h2 id="checks-title" className="panel__title">
              Checks
            </h2>
            <ul className="check-list">
              {state.data.checks.map((check) => (
                <CheckRow key={check.check_type} check={check} reload={() => void refresh()} />
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </div>
  );
}
