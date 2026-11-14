"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useId, useState } from "react";

import { Pager } from "@/components/ui/Pager";
import { ApplicationStatusChip, Chip, GigStatusChip } from "@/components/ui/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { ApplicationStatus, BadgeKind } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";
import { APPLICATION_STATUS_LABELS, BADGE_LABELS, options } from "@/lib/vendor/labels";

const PAGE_SIZE = 25;
const SORTS = [
  { value: "fit", label: "Best fit" },
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
] as const;
type Sort = (typeof SORTS)[number]["value"];
const MIN_SCORES = [
  { value: "", label: "Any fit" },
  { value: "50", label: "50% or more" },
  { value: "70", label: "70% or more" },
  { value: "85", label: "85% or more" },
];

export function badgeLabel(badge: string): string {
  return BADGE_LABELS[badge as BadgeKind] ?? badge;
}

export function FitScore({ score }: { score: number }) {
  return (
    <span className="fit">
      <span className="fit__value">{score}%</span>
      <span className="fit__bar" aria-hidden="true">
        <span className="fit__fill" style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </span>
    </span>
  );
}

/**
 * A gig's applicants as a table, best fit first. (The kanban pipeline from the design
 * canvas comes with Phase 3, when vendors can move applicants between stages.)
 */
export function ApplicantTable() {
  const { gigId } = useParams<{ gigId: string }>();
  const ids = useId();
  const [status, setStatus] = useState<ApplicationStatus | "">("");
  const [minScore, setMinScore] = useState("");
  const [sort, setSort] = useState<Sort>("fit");
  const [page, setPage] = useState(1);

  const gig = useLoad(
    () => unwrap(api.GET("/api/v1/gigs/{gig_id}/", { params: { path: { gig_id: gigId } } })),
    gigId,
  );
  const list = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/gigs/{gig_id}/applications/", {
          params: {
            path: { gig_id: gigId },
            query: {
              page,
              page_size: PAGE_SIZE,
              sort,
              ...(status ? { status } : {}),
              ...(minScore ? { min_score: Number(minScore) } : {}),
            },
          },
        }),
      ),
    `${gigId}:${status}:${minScore}:${sort}:${page}`,
  );

  const filtered = Boolean(status || minScore);

  return (
    <div className="page page--wide">
      <header className="page__header">
        <Link href="/console/applicants" className="back-link">
          All gigs with applicants
        </Link>
        {gig.state.status === "ready" ? (
          <>
            <div className="page__title-row">
              <h1 className="page__title">{gig.state.data.title}</h1>
              <GigStatusChip status={gig.state.data.status} />
            </div>
            <p className="page__lead">
              Applicants · {gig.state.data.slots ?? 1} slot{gig.state.data.slots === 1 ? "" : "s"}
            </p>
          </>
        ) : (
          <h1 className="page__title">Applicants</h1>
        )}
      </header>

      <div className="filters" role="group" aria-label="Filter and sort applicants">
        <div className="field">
          <label className="field__label" htmlFor={`${ids}-status`}>
            Status
          </label>
          <select
            id={`${ids}-status`}
            className="field__control field__control--select"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as ApplicationStatus | "");
              setPage(1);
            }}
          >
            <option value="">All statuses</option>
            {options(APPLICATION_STATUS_LABELS).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field__label" htmlFor={`${ids}-fit`}>
            Fit
          </label>
          <select
            id={`${ids}-fit`}
            className="field__control field__control--select"
            value={minScore}
            onChange={(e) => {
              setMinScore(e.target.value);
              setPage(1);
            }}
          >
            {MIN_SCORES.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field__label" htmlFor={`${ids}-sort`}>
            Sort by
          </label>
          <select
            id={`${ids}-sort`}
            className="field__control field__control--select"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value as Sort);
              setPage(1);
            }}
          >
            {SORTS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {list.state.status === "loading" ? <LoadingState label="Loading applicants…" /> : null}
      {list.state.status === "error" ? (
        <ErrorState
          title="We couldn't load the applicants"
          description={describeError(list.state.error)}
          retry={() => void list.reload()}
          action={{ label: "All gigs", href: "/console/gigs" }}
        />
      ) : null}
      {list.state.status === "ready" && list.state.data.results.length === 0 ? (
        <EmptyState
          title={filtered ? "No applicants match" : "No applicants yet"}
          description={
            filtered
              ? "Try another status or a lower fit."
              : "When talent apply, they show up here with their fit score."
          }
        />
      ) : null}
      {list.state.status === "ready" && list.state.data.results.length > 0 ? (
        <>
          <p className="table-count">
            {list.state.data.count} applicant{list.state.data.count === 1 ? "" : "s"}
          </p>
          <div className="table-wrap">
            <table className="table table--cards">
              <caption className="visually-hidden">
                Applicants, sorted by {SORTS.find((s) => s.value === sort)!.label.toLowerCase()}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Applicant</th>
                  <th scope="col">Fit</th>
                  <th scope="col">Status</th>
                  <th scope="col">Dates</th>
                  <th scope="col">Badges</th>
                  <th scope="col">Applied</th>
                  <th scope="col">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.state.data.results.map((a) => (
                  <tr key={a.id}>
                    <th scope="row" className="table__primary">
                      <span className="table__title">{a.applicant.display_name}</span>
                      <span className="table__sub">
                        {[a.applicant.talent_type, a.applicant.home_city]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </th>
                    <td data-label="Fit">
                      <FitScore score={a.fit.score} />
                    </td>
                    <td data-label="Status">
                      <ApplicationStatusChip status={a.status} />
                    </td>
                    <td data-label="Dates">
                      {formatDate(a.proposed_start)} to {formatDate(a.proposed_end)}
                    </td>
                    <td data-label="Badges">
                      <div className="chip-row">
                        {a.applicant.badges.length
                          ? a.applicant.badges.map((b) => (
                              <Chip key={b} tone="success">
                                {badgeLabel(b)}
                              </Chip>
                            ))
                          : "None"}
                      </div>
                    </td>
                    <td data-label="Applied">{formatDate(a.applied_at)}</td>
                    <td>
                      <Link href={`/console/applicants/${a.id}`} className="button button--ghost">
                        View <span className="visually-hidden">{a.applicant.display_name}</span>
                        {a.attachment_count ? (
                          <span className="table__count">
                            {" "}
                            · {a.attachment_count} file{a.attachment_count === 1 ? "" : "s"}
                          </span>
                        ) : null}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager
            page={page}
            count={list.state.data.count}
            pageSize={PAGE_SIZE}
            onPage={setPage}
            label="Applicant pages"
          />
        </>
      ) : null}
    </div>
  );
}
