"use client";

import Link from "next/link";

import { GigStatusChip } from "@/components/ui/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

/** Pick a gig to see its applicants. Drafts have none, so they're left out. */
export function ApplicantsIndex() {
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/gigs/mine/", { params: { query: { page_size: 100 } } })),
    "applicant-gigs",
  );
  const gigs =
    state.status === "ready" ? state.data.results.filter((g) => g.status !== "draft") : [];

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Applicants</h1>
        <p className="page__lead">Choose a gig to review who applied.</p>
      </header>
      {state.status === "loading" ? <LoadingState label="Loading your gigs…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your gigs"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && gigs.length === 0 ? (
        <EmptyState
          title="No applicants yet"
          description="When talent apply to your gigs, you'll review and shortlist them here."
          action={{ label: "Your gigs", href: "/console/gigs" }}
        />
      ) : null}
      {gigs.length ? (
        <ul className="card-list">
          {gigs.map((gig) => (
            <li key={gig.id} className="card-list__item">
              <div className="card-list__main">
                <Link href={`/console/gigs/${gig.id}/applicants`} className="card-list__title">
                  {gig.title}
                </Link>
                <p className="card-list__meta">Starts {formatDate(gig.start_date)}</p>
              </div>
              <GigStatusChip status={gig.status} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
