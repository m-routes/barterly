"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { SignPanel } from "@/components/agreements/SignPanel";
import { TermsSummary } from "@/components/agreements/TermsSummary";
import { Button } from "@/components/ui/Button";
import { Chip, type ChipTone } from "@/components/ui/StatusChip";
import { FormError, SelectField, TextArea, TextField } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { CANCELLATION_LABELS, VERSION_STATUS_LABELS } from "@/lib/agreements/terms";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Agreement, AgreementVersion, Terms } from "@/lib/api/types";
import {
  firebasePhoneSignIn,
  type FirebaseWebConfig,
  type PhoneSignIn,
} from "@/lib/firebase/phoneAuth";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { BookingPanel } from "./BookingPanel";
import { useSession } from "@/lib/session/session";
import { MEALS_LABELS, STAY_TYPE_LABELS, options } from "@/lib/vendor/labels";

const VERSION_TONES: Record<AgreementVersion["status"], ChipTone> = {
  awaiting: "pending",
  active: "success",
  superseded: "neutral",
  declined: "neutral",
  voided: "neutral",
};

type Props = { config?: FirebaseWebConfig | null; phoneSignIn?: PhoneSignIn };

export function AgreementDetail({ config, phoneSignIn }: Props) {
  const { agreementId } = useParams<{ agreementId: string }>();
  const session = useSession();
  const phone = session.state.status === "signed-in" ? session.state.user.phone : "";
  const signIn = useMemo(
    () => phoneSignIn ?? (config ? firebasePhoneSignIn(config) : null),
    [phoneSignIn, config],
  );
  const { state, reload, setData } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/agreements/{agreement_id}/", {
          params: { path: { agreement_id: agreementId } },
        }),
      ),
    agreementId,
  );
  const [changing, setChanging] = useState(false);

  if (state.status === "loading") return <LoadingState label="Loading the agreement…" />;
  if (state.status === "error") {
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load this agreement"
          description={describeError(state.error)}
          retry={() => void reload()}
          action={{ label: "All agreements", href: "/console/agreements" }}
        />
      </div>
    );
  }
  const agreement = state.data;
  const base = agreement.versions.find((v) => v.status === "active") ?? agreement.versions[0];
  const canChange = ["signing", "confirmed", "checked_in", "delivering"].includes(
    agreement.booking_status,
  );

  return (
    <div className="page page--narrow">
      <header className="page__header">
        <Link href="/console/agreements" className="back-link">
          Agreements
        </Link>
        <div className="page__title-row">
          <h1 className="page__title">{agreement.gig_title}</h1>
          {agreement.in_force ? (
            <Chip tone="success">In force: version {agreement.current_version}</Chip>
          ) : (
            <Chip tone="pending">Not signed by both yet</Chip>
          )}
        </div>
        <p className="page__lead">
          Valid only once both of you sign the same version. A change is a new version you both sign
          again; until then the version in force stays.
        </p>
      </header>

      <div className="stack">
        <BookingPanel agreement={agreement} onChange={() => void reload()} />
        {agreement.versions.map((version) => (
          <VersionCard
            key={version.id}
            agreement={agreement}
            version={version}
            phone={phone}
            phoneSignIn={signIn}
            onChange={() => void reload()}
          />
        ))}

        {canChange && base ? (
          changing ? (
            <ChangeForm
              agreement={agreement}
              base={base.terms}
              onDone={(updated) => {
                setChanging(false);
                if (updated) setData(() => updated);
              }}
            />
          ) : (
            <div>
              <Button variant="secondary" onClick={() => setChanging(true)}>
                Change the terms
              </Button>
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}

function VersionCard({
  agreement,
  version,
  phone,
  phoneSignIn,
  onChange,
}: {
  agreement: Agreement;
  version: AgreementVersion;
  phone: string;
  phoneSignIn: PhoneSignIn | null;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const other = agreement.my_side === "vendor" ? "talent" : "vendor";
  const signedByOther = version.signatures.some((s) => s.party === other);
  const isChange = version.number > 1 && version.status === "awaiting" && agreement.in_force;
  const mine = version.proposed_by === agreement.my_side;
  const path = { params: { path: { version_id: version.id } } };

  async function openPdf() {
    setBusy(true);
    setError("");
    try {
      const link = await unwrap(api.GET("/api/v1/agreement-versions/{version_id}/pdf/", path));
      window.open(link.url, "_blank", "noopener");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  async function decline() {
    setBusy(true);
    setError("");
    try {
      await unwrap(
        api.POST("/api/v1/agreement-versions/{version_id}/decline/", { ...path, body: {} }),
      );
      onChange();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel stack-sm" aria-labelledby={`v-${version.id}`}>
      <div className="panel__header panel__header--row">
        <h2 id={`v-${version.id}`} className="panel__title">
          Version {version.number}
        </h2>
        <Chip tone={VERSION_TONES[version.status]}>{VERSION_STATUS_LABELS[version.status]}</Chip>
      </div>
      {!version.template_reviewed ? (
        <p className="note note--warning">
          The legal text is a placeholder that a lawyer must review before launch.
        </p>
      ) : null}
      {version.change_reason ? (
        <p>
          <strong>{mine ? "You asked for this change" : "They asked for this change"}:</strong>{" "}
          {version.change_reason}
        </p>
      ) : null}
      <TermsSummary terms={version.terms} changed={version.changed_fields} />
      <ul className="signatures">
        {(["vendor", "talent"] as const).map((side) => {
          const signature = version.signatures.find((s) => s.party === side);
          const who = side === agreement.my_side ? "You" : side === "vendor" ? "Host" : "Talent";
          return (
            <li key={side}>
              {who}: {signature ? `signed ${formatDate(signature.signed_at)}` : "not signed yet"}
            </li>
          );
        })}
      </ul>
      <p className="field__hint">
        Fingerprint (SHA-256): <code>{version.pdf_sha256 || "being prepared"}</code>
      </p>
      <FormError message={error} />
      <div className="actions-row actions-row--start">
        <Button
          variant="secondary"
          busy={busy}
          disabled={!version.pdf_ready}
          onClick={() => void openPdf()}
        >
          {version.pdf_ready ? "Open PDF" : "PDF being prepared"}
        </Button>
        {isChange ? (
          <Button variant="ghost" disabled={busy} onClick={() => void decline()}>
            {mine ? "Withdraw this change" : "Decline this change"}
          </Button>
        ) : null}
      </div>
      {version.can_sign ? (
        <>
          {signedByOther ? (
            <p>The other side has signed. Your signature puts it in force.</p>
          ) : null}
          <SignPanel
            version={version}
            phone={phone}
            phoneSignIn={phoneSignIn}
            onSigned={onChange}
          />
        </>
      ) : null}
    </section>
  );
}

type Changes = Partial<Terms>;

function ChangeForm({
  agreement,
  base,
  onDone,
}: {
  agreement: Agreement;
  base: Terms;
  onDone: (updated: Agreement | null) => void;
}) {
  const [terms, setTerms] = useState<Terms>(base);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const started = !["signing", "confirmed"].includes(agreement.booking_status);
  const set = <K extends keyof Terms>(key: K, value: Terms[K]) =>
    setTerms((t) => ({ ...t, [key]: value }));

  function changes(): Changes {
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(terms) as Array<keyof Terms>) {
      if (JSON.stringify(terms[key]) !== JSON.stringify(base[key])) out[key] = terms[key];
    }
    return out as Changes;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        api.POST("/api/v1/bookings/{booking_id}/agreement/changes/", {
          params: { path: { booking_id: agreement.booking } },
          body: { changes: changes(), reason },
        }),
      );
      onDone(updated);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel stack-sm" onSubmit={(e) => void submit(e)} noValidate>
      <h2 className="panel__title">Change the terms</h2>
      <p className="field__hint">
        This draws up a new version. Both of you sign it again; until then the version in force
        stays.{started ? " The stay has started, so the dates can't change." : ""}
      </p>
      <div className="form-grid form-grid--two">
        <TextField
          label="Arrive"
          type="date"
          disabled={started}
          value={terms.start_date}
          onChange={(e) => set("start_date", e.target.value)}
        />
        <TextField
          label="Leave"
          type="date"
          disabled={started}
          value={terms.end_date}
          onChange={(e) => set("end_date", e.target.value)}
        />
        <TextField
          label="Hours a day"
          type="number"
          min={1}
          max={6}
          value={terms.hours_per_day}
          onChange={(e) => set("hours_per_day", Number(e.target.value))}
        />
        <TextField
          label="Days a week"
          type="number"
          min={1}
          max={6}
          value={terms.days_per_week}
          onChange={(e) => set("days_per_week", Number(e.target.value))}
        />
        <SelectField
          label="Stay"
          options={options(STAY_TYPE_LABELS)}
          value={terms.stay_type}
          onChange={(e) => set("stay_type", e.target.value as Terms["stay_type"])}
        />
        <SelectField
          label="Meals"
          options={options(MEALS_LABELS)}
          value={terms.meals}
          onChange={(e) => set("meals", e.target.value as Terms["meals"])}
        />
        {base.stipend_amount != null ? (
          <TextField
            label="Stipend (₹)"
            type="number"
            min={1}
            value={terms.stipend_amount ?? ""}
            onChange={(e) => set("stipend_amount", e.target.value)}
          />
        ) : null}
        <SelectField
          label="Cancellation"
          options={options(CANCELLATION_LABELS)}
          value={terms.cancellation_policy}
          onChange={(e) =>
            set("cancellation_policy", e.target.value as Terms["cancellation_policy"])
          }
        />
      </div>
      <TextArea
        label="Why the change"
        maxLength={1000}
        required
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <FormError message={error} />
      <div className="actions-row actions-row--start">
        <Button
          type="submit"
          busy={busy}
          disabled={!reason.trim() || Object.keys(changes()).length === 0}
        >
          Propose the change
        </Button>
        <Button variant="ghost" disabled={busy} onClick={() => onDone(null)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
