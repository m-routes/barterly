"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";

import { ApplicationStatusChip } from "@/components/ui/StatusChip";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { ApplicantProfile } from "./ApplicantProfile";
import { OfferPanel } from "./OfferPanel";

/** Opens (or reuses) the chat with this applicant. */
function MessageButton({ applicationId }: { applicationId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const open = async () => {
    setBusy(true);
    setError("");
    try {
      const conversation = await unwrap(
        api.POST("/api/v1/applications/{application_id}/conversation/", {
          params: { path: { application_id: applicationId } },
        }),
      );
      router.push(`/console/messages/${conversation.id}`);
    } catch (e) {
      setError(describeError(e));
      setBusy(false);
    }
  };
  return (
    <div>
      <Button variant="secondary" busy={busy} busyLabel="Opening…" onClick={() => void open()}>
        Message
      </Button>
      {error ? <p className="field__error">{error}</p> : null}
    </div>
  );
}

/** One applicant: who they are, their pitch and files. Never their contact details. */
export function ApplicantDetail() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const { state, reload, refresh } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/applications/{application_id}/", {
          params: { path: { application_id: applicationId } },
        }),
      ),
    applicationId,
  );

  if (state.status === "loading") return <LoadingState label="Loading the application…" />;
  if (state.status === "error") {
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load this application"
          description={describeError(state.error)}
          retry={() => void reload()}
          action={{ label: "All gigs", href: "/console/applicants" }}
        />
      </div>
    );
  }
  const a = state.data;
  const person = a.applicant;

  return (
    <div className="page page--narrow">
      <header className="page__header">
        <Link href={`/console/gigs/${a.gig}/applicants`} className="back-link">
          Applicants for {a.gig_title}
        </Link>
        <div className="page__title-row">
          <h1 className="page__title">{person.display_name}</h1>
          <ApplicationStatusChip status={a.status} />
        </div>
        <p className="page__lead">
          {[person.talent_type, person.home_city].filter(Boolean).join(" · ")} · applied{" "}
          {formatDate(a.applied_at)}
        </p>
        <MessageButton applicationId={a.id} />
      </header>

      <div className="stack">
        <OfferPanel application={a} onChange={() => void refresh()} />

        <ApplicantProfile application={a} />
      </div>
    </div>
  );
}
