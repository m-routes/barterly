"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormError, TextArea, TextField } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { ConsentState, DataExport, DeletionStatus } from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";
import { LEGAL_VERSION } from "@/lib/legal/documents";

const PURPOSE_TEXT: Record<string, string> = {
  terms: "Needed to use Barterly. To withdraw it, delete your account below.",
  privacy: "Needed to use Barterly. To withdraw it, delete your account below.",
  location: "Record where you are when you open your check-in pass. Check-in works without it.",
  social: "Read public numbers for posts you hand in, and check your handle.",
  marketing: "Offers and news from Barterly. Booking and payment messages aren't marketing.",
};

function when(iso: string | null | undefined): string {
  return iso
    ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
    : "";
}

/**
 * Privacy settings: give or withdraw each consent, export your data, ask for a
 * correction, and delete your account. Every action here is one click (plus a
 * confirmation for deletion), so withdrawing is as easy as giving.
 */
export function PrivacySettings({ profileHref }: { profileHref?: string }) {
  return (
    <div className="page page--narrow stack">
      <header className="page__header">
        <h1 className="page__title">Privacy and your data</h1>
        <p>
          See the <Link href="/legal/privacy">privacy policy</Link>. Questions or complaints go to
          our <Link href="/grievance">Grievance Officer</Link>.
        </p>
      </header>
      <Consents />
      <ExportData />
      <CorrectData profileHref={profileHref} />
      <DeleteAccount />
    </div>
  );
}

function Consents() {
  const { state, reload, setData } = useLoad(
    () => unwrap(api.GET("/api/v1/privacy/consents/")),
    "privacy-consents",
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function change(consent: ConsentState, granted: boolean) {
    setBusy(consent.purpose);
    setError("");
    try {
      const updated = await unwrap(
        api.POST("/api/v1/privacy/consents/", {
          body: {
            purpose: consent.purpose,
            granted,
            ...(granted ? { version: LEGAL_VERSION } : {}),
            source: "web",
          },
        }),
      );
      setData(() => updated);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy("");
    }
  }

  let body: React.ReactNode;
  if (state.status === "loading") body = <LoadingState label="Loading your consents…" />;
  else if (state.status === "error") {
    body = (
      <ErrorState
        title="We couldn't load your consents"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  } else {
    body = (
      <ul className="privacy-list">
        {state.data.map((consent) => (
          <li key={consent.purpose} className="privacy-row">
            <div className="privacy-row__text">
              <strong>{consent.label}</strong>
              <p>{PURPOSE_TEXT[consent.purpose]}</p>
              <p className="privacy-row__meta">
                {consent.granted
                  ? `Given${consent.version ? ` (version ${consent.version})` : ""} ${when(consent.recorded_at)}`
                  : consent.recorded_at
                    ? `Withdrawn ${when(consent.recorded_at)}`
                    : "Not given"}
              </p>
            </div>
            {consent.required ? null : consent.granted ? (
              <Button
                variant="secondary"
                busy={busy === consent.purpose}
                busyLabel="Withdrawing…"
                onClick={() => void change(consent, false)}
              >
                Withdraw
              </Button>
            ) : (
              <Button
                busy={busy === consent.purpose}
                busyLabel="Saving…"
                onClick={() => void change(consent, true)}
              >
                Allow
              </Button>
            )}
          </li>
        ))}
      </ul>
    );
  }

  return (
    <section className="panel stack-sm" aria-labelledby="consents-title">
      <h2 id="consents-title" className="panel__title">
        Your consents
      </h2>
      {body}
      <FormError message={error} />
    </section>
  );
}

function ExportData() {
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/privacy/exports/")),
    "privacy-exports",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function make() {
    setBusy(true);
    setError("");
    try {
      await unwrap(api.POST("/api/v1/privacy/exports/"));
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function download(item: DataExport) {
    setError("");
    try {
      const link = await unwrap(
        api.POST("/api/v1/privacy/exports/{export_id}/link/", {
          params: { path: { export_id: item.id } },
        }),
      );
      window.location.assign(link.url);
    } catch (err) {
      setError(describeError(err));
    }
  }

  const ready =
    state.status === "ready" ? state.data.results.filter((e) => e.status === "ready") : [];
  return (
    <section className="panel stack-sm" aria-labelledby="export-title">
      <h2 id="export-title" className="panel__title">
        Download your data
      </h2>
      <p>
        One JSON file with everything we hold about you. It is kept for a day; each download link
        works for a few minutes.
      </p>
      {ready.map((item) => (
        <div key={item.id} className="privacy-row">
          <span className="privacy-row__text">
            Export from {when(item.created_at)}, available until {when(item.expires_at)}
          </span>
          <Button variant="secondary" onClick={() => void download(item)}>
            Download
          </Button>
        </div>
      ))}
      <div>
        <Button busy={busy} busyLabel="Preparing…" onClick={() => void make()}>
          Export my data
        </Button>
      </div>
      <FormError message={error} />
    </section>
  );
}

function CorrectData({ profileHref }: { profileHref?: string }) {
  const [field, setField] = useState("");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSent(false);
    if (!field.trim() || !value.trim()) {
      setError("Say what is wrong and what it should be.");
      return;
    }
    setBusy(true);
    try {
      await unwrap(
        api.POST("/api/v1/privacy/corrections/", {
          body: { field: field.trim(), correct_value: value.trim(), note: note.trim() },
        }),
      );
      setSent(true);
      setField("");
      setValue("");
      setNote("");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel stack-sm" aria-labelledby="correct-title">
      <h2 id="correct-title" className="panel__title">
        Correct your data
      </h2>
      <p>
        {profileHref ? (
          <>
            Edit most details yourself in <Link href={profileHref}>your profile</Link>.{" "}
          </>
        ) : null}
        For anything you can&apos;t change there, such as your phone number or a name on a signed
        agreement, ask us here.
      </p>
      <form className="stack-sm" onSubmit={(e) => void submit(e)} noValidate>
        <TextField
          label="What is wrong"
          maxLength={60}
          value={field}
          onChange={(e) => setField(e.target.value)}
          hint="For example: phone number"
        />
        <TextField
          label="What it should be"
          maxLength={500}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <TextArea
          label="Anything else we should know"
          optional
          maxLength={1000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <FormError message={error} />
        {sent ? <p role="status">Sent. We&apos;ll reply by email or in the app.</p> : null}
        <div>
          <Button type="submit" variant="secondary" busy={busy} busyLabel="Sending…">
            Ask for a correction
          </Button>
        </div>
      </form>
    </section>
  );
}

function DeleteAccount() {
  const { state, reload, setData } = useLoad(
    () => unwrap(api.GET("/api/v1/privacy/deletion/")),
    "privacy-deletion",
  );
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function schedule() {
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        api.POST("/api/v1/privacy/deletion/", { body: { confirm: true } }),
      );
      setData(() => updated);
      setConfirming(false);
    } catch (err) {
      setError(describeError(err));
      await reload();
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    setBusy(true);
    setError("");
    try {
      await unwrap(api.DELETE("/api/v1/privacy/deletion/"));
      await reload();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  let body: React.ReactNode;
  if (state.status === "loading") body = <LoadingState label="Loading…" />;
  else if (state.status === "error") {
    body = (
      <ErrorState
        title="We couldn't check your account"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  } else {
    body = (
      <DeletionBody
        status={state.data}
        busy={busy}
        confirming={confirming}
        onConfirm={setConfirming}
        onSchedule={() => void schedule()}
        onCancel={() => void cancel()}
      />
    );
  }

  return (
    <section className="panel stack-sm privacy-danger" aria-labelledby="delete-title">
      <h2 id="delete-title" className="panel__title">
        Delete your account
      </h2>
      {body}
      <FormError message={error} />
    </section>
  );
}

function DeletionBody({
  status,
  busy,
  confirming,
  onConfirm,
  onSchedule,
  onCancel,
}: {
  status: DeletionStatus;
  busy: boolean;
  confirming: boolean;
  onConfirm: (value: boolean) => void;
  onSchedule: () => void;
  onCancel: () => void;
}) {
  if (status.request) {
    return (
      <>
        <p role="status">
          Your account will be deleted on {when(status.request.scheduled_for)}. Until then you can
          change your mind.
        </p>
        <div>
          <Button variant="secondary" busy={busy} busyLabel="Cancelling…" onClick={onCancel}>
            Keep my account
          </Button>
        </div>
      </>
    );
  }
  return (
    <>
      <p>
        We erase your profile, photos, messages and everything that identifies you. Records the law
        makes us keep (payments, invoices, signed agreements, disputes) stay, with your personal
        details removed. You have {status.grace_days} days to change your mind.
      </p>
      {status.blockers.length ? (
        <div role="alert">
          <p>Before you can delete your account:</p>
          <ul>
            {status.blockers.map((blocker) => (
              <li key={blocker.code}>{blocker.message}</li>
            ))}
          </ul>
        </div>
      ) : confirming ? (
        <div className="stack-sm">
          <p>
            <strong>Are you sure?</strong> After {status.grace_days} days this can&apos;t be undone.
          </p>
          <div className="privacy-actions">
            <Button busy={busy} busyLabel="Scheduling…" onClick={onSchedule}>
              Yes, delete my account
            </Button>
            <Button variant="ghost" onClick={() => onConfirm(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button variant="secondary" onClick={() => onConfirm(true)}>
            Delete my account
          </Button>
        </div>
      )}
    </>
  );
}
