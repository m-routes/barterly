"use client";

import Link from "next/link";

import { Chip } from "@/components/ui/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { sectionFor } from "../nav";

export function AgreementsIndex() {
  const section = sectionFor("/console/agreements");
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/agreements/", { params: { query: { page_size: 50 } } })),
    "agreements",
  );

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">{section.label}</h1>
        <p className="page__lead">
          One per booking. Each is valid once both of you sign it; changes are new versions.
        </p>
      </header>
      {state.status === "loading" ? <LoadingState label="Loading agreements…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your agreements"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length === 0 ? (
        <EmptyState title={section.empty.title} description={section.empty.description} />
      ) : null}
      {state.status === "ready" && state.data.results.length ? (
        <ul className="agreement-list">
          {state.data.results.map((a) => (
            <li key={a.id} className="panel agreement-list__item">
              <div className="stack-xs">
                <Link href={`/console/agreements/${a.id}`} className="agreement-list__title">
                  {a.gig_title}
                </Link>
                <span className="field__hint">
                  {a.other_name} · {formatDate(a.start_date)} to {formatDate(a.end_date)}
                </span>
              </div>
              <div className="chip-row">
                {a.awaiting_my_signature ? (
                  <Chip tone="warning">Sign version {a.awaiting_version}</Chip>
                ) : a.awaiting_version ? (
                  <Chip tone="pending">Version {a.awaiting_version}: waiting for them</Chip>
                ) : null}
                {a.in_force ? (
                  <Chip tone="success">In force: version {a.current_version}</Chip>
                ) : (
                  <Chip tone="neutral">Not in force yet</Chip>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
