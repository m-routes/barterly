"use client";

import Link from "next/link";
import { useState } from "react";

import { Pager } from "@/components/ui/Pager";
import { GigStatusChip } from "@/components/ui/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Gig, GigStatus } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";
import { COMPENSATION_MODELS, GIG_STATUS_LABELS, ROLE_TEMPLATE_LABELS } from "@/lib/vendor/labels";

const PAGE_SIZE = 20;
const FILTERS: (GigStatus | "all")[] = [
  "all",
  "draft",
  "in_review",
  "live",
  "paused",
  "filled",
  "closed",
];
const EDITABLE: ReadonlySet<GigStatus> = new Set(["draft", "in_review", "live", "paused"]);

function GigActions({ gig }: { gig: Gig }) {
  return (
    <div className="table-actions">
      {EDITABLE.has(gig.status) ? (
        <Link href={`/console/gigs/${gig.id}/edit`} className="button button--ghost">
          {gig.status === "draft" ? "Continue" : "Edit"}
          <span className="visually-hidden">: {gig.title}</span>
        </Link>
      ) : null}
      {gig.status !== "draft" ? (
        <Link href={`/console/gigs/${gig.id}/applicants`} className="button button--ghost">
          Applicants<span className="visually-hidden">: {gig.title}</span>
        </Link>
      ) : null}
    </div>
  );
}

/** The vendor's gigs, newest first, filtered by status. */
export function GigList() {
  const [status, setStatus] = useState<GigStatus | "all">("all");
  const [page, setPage] = useState(1);
  const { state, reload } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/gigs/mine/", {
          params: {
            query: { page, page_size: PAGE_SIZE, ...(status === "all" ? {} : { status }) },
          },
        }),
      ),
    `${status}:${page}`,
  );

  return (
    <div className="page">
      <header className="page__header page__header--row">
        <h1 className="page__title">Gigs</h1>
        <Link href="/console/gigs/new" className="button button--primary">
          Post a gig
        </Link>
      </header>

      <div className="filter-chips" role="group" aria-label="Show gigs by status">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`filter-chip${status === f ? " filter-chip--on" : ""}`}
            aria-pressed={status === f}
            onClick={() => {
              setStatus(f);
              setPage(1);
            }}
          >
            {f === "all" ? "All" : GIG_STATUS_LABELS[f]}
          </button>
        ))}
      </div>

      {state.status === "loading" ? <LoadingState label="Loading your gigs…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your gigs"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length === 0 ? (
        status === "all" ? (
          <EmptyState
            title="No gigs yet"
            description="Gigs describe the help you need and what you offer in return. Post your first one."
            action={{ label: "Post a gig", href: "/console/gigs/new" }}
          />
        ) : (
          <EmptyState
            title={`No ${GIG_STATUS_LABELS[status].toLowerCase()} gigs`}
            description="Choose another status to see the rest."
          />
        )
      ) : null}
      {state.status === "ready" && state.data.results.length > 0 ? (
        <>
          <div className="table-wrap">
            <table className="table table--cards">
              <caption className="visually-hidden">
                Your gigs{status === "all" ? "" : `: ${GIG_STATUS_LABELS[status]}`}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Gig</th>
                  <th scope="col">Status</th>
                  <th scope="col">Starts</th>
                  <th scope="col">Slots</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {state.data.results.map((gig) => (
                  <tr key={gig.id}>
                    <th scope="row" className="table__primary">
                      <span className="table__title">{gig.title}</span>
                      <span className="table__sub">
                        {ROLE_TEMPLATE_LABELS[gig.role_template]} ·{" "}
                        {COMPENSATION_MODELS[gig.compensation_model].badge}
                      </span>
                    </th>
                    <td data-label="Status">
                      <GigStatusChip status={gig.status} />
                    </td>
                    <td data-label="Starts">{formatDate(gig.start_date)}</td>
                    <td data-label="Slots">{gig.slots ?? 1}</td>
                    <td>
                      <GigActions gig={gig} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={page}
            count={state.data.count}
            pageSize={PAGE_SIZE}
            onPage={setPage}
            label="Gig pages"
          />
        </>
      ) : null}
    </div>
  );
}
