"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { ApplicationStatusChip, Chip } from "@/components/ui/StatusChip";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Application } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { FitScore, badgeLabel } from "./ApplicantTable";

type Answer = { question: string; answer: string };

function asAnswers(value: unknown): Answer[] {
  return Array.isArray(value)
    ? value.filter(
        (a): a is Answer => typeof a === "object" && a !== null && "question" in a && "answer" in a,
      )
    : [];
}

function humanize(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Attachments({ items }: { items: Application["attachments"] }) {
  if (!items.length) return <p className="field__hint">No attachments.</p>;
  return (
    <ul className="attachment-grid">
      {items.map((item, index) => {
        const title = item.title || `${humanize(item.kind)} ${index + 1}`;
        return (
          <li key={item.id} className="attachment-grid__item">
            {item.kind === "photo" && (item.thumb_url || item.url) ? (
              // Signed storage URLs: next/image can't optimise them.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.thumb_url || item.url || undefined}
                alt={title}
                className="attachment-grid__img"
              />
            ) : null}
            {item.url ? (
              <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.kind === "link" ? item.url : `Open ${title}`}
              </a>
            ) : (
              <span className="field__hint">{title}: still processing</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** One applicant: who they are, their pitch and files. Never their contact details. */
export function ApplicantDetail() {
  const { applicationId } = useParams<{ applicationId: string }>();
  const { state, reload } = useLoad(
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
  const breakdown = Object.entries(a.fit.breakdown ?? {});
  const answers = asAnswers(a.answers);

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
      </header>

      <div className="stack">
        <section className="panel stack-sm" aria-labelledby="about-title">
          <h2 id="about-title" className="panel__title">
            About
          </h2>
          {person.badges.length ? (
            <div className="chip-row">
              {person.badges.map((b) => (
                <Chip key={b} tone="success">
                  {badgeLabel(b)}
                </Chip>
              ))}
            </div>
          ) : (
            <p className="field__hint">No verification badges yet.</p>
          )}
          {person.bio ? <p>{person.bio}</p> : null}
          <dl className="summary">
            <div>
              <dt>Wants to come</dt>
              <dd>
                {formatDate(a.proposed_start)} to {formatDate(a.proposed_end)}
              </dd>
            </div>
            {person.languages.length ? (
              <div>
                <dt>Languages</dt>
                <dd>{person.languages.join(", ")}</dd>
              </div>
            ) : null}
            {person.skills.length ? (
              <div>
                <dt>Skills</dt>
                <dd>{person.skills.join(", ")}</dd>
              </div>
            ) : null}
            {person.instagram_followers != null ? (
              <div>
                <dt>Instagram followers</dt>
                <dd>{person.instagram_followers.toLocaleString("en-IN")}</dd>
              </div>
            ) : null}
          </dl>
          <p className="note">
            Contact details are shared once you book someone. Until then, talk on Barterly.
          </p>
        </section>

        <section className="panel stack-sm" aria-labelledby="fit-title">
          <div className="panel__header panel__header--row">
            <h2 id="fit-title" className="panel__title">
              Fit
            </h2>
            <FitScore score={a.fit.score} />
          </div>
          {breakdown.length ? (
            <ul className="fit-breakdown">
              {breakdown.map(([key, part]) => (
                <li key={key}>
                  <span className="fit-breakdown__label">{humanize(key)}</span>
                  <span>{part.reason || (part.neutral ? "Not enough data yet." : "")}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="panel stack-sm" aria-labelledby="pitch-title">
          <h2 id="pitch-title" className="panel__title">
            Pitch
          </h2>
          <p className="prewrap">{a.pitch || "No pitch."}</p>
          {answers.length ? (
            <dl className="answers">
              {answers.map((item, index) => (
                <div key={index}>
                  <dt>{item.question}</dt>
                  <dd className="prewrap">{item.answer}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </section>

        <section className="panel stack-sm" aria-labelledby="files-title">
          <h2 id="files-title" className="panel__title">
            Attachments
          </h2>
          <Attachments items={a.attachments} />
        </section>
      </div>
    </div>
  );
}
