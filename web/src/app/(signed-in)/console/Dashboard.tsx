"use client";

import Link from "next/link";

import { Chip, VerificationChip } from "@/components/ui/StatusChip";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError } from "@/lib/api/errors";
import { useLoad } from "@/lib/hooks/useLoad";
import { buildChecklist, type ChecklistInput } from "@/lib/vendor/checklist";
import { BADGE_LABELS } from "@/lib/vendor/labels";

async function loadChecklist(): Promise<ChecklistInput> {
  const [profile, properties, verification] = await Promise.all([
    unwrap(api.GET("/api/v1/profiles/vendor/me/")).catch((error: unknown) => {
      if (error instanceof ApiError && error.code === "profile_not_found") return null;
      throw error;
    }),
    unwrap(api.GET("/api/v1/properties/", { params: { query: { page_size: 50 } } })),
    unwrap(api.GET("/api/v1/verification/me/")),
  ]);
  return { profile, properties: properties.results, verification };
}

function CheckIcon({ done }: { done: boolean }) {
  return (
    <span className={`checklist__mark${done ? " checklist__mark--done" : ""}`} aria-hidden="true">
      {done ? (
        <svg viewBox="0 0 24 24" width="16" height="16">
          <path d="m5 12 4 4 10-10" fill="none" stroke="currentColor" strokeWidth="2.5" />
        </svg>
      ) : null}
    </span>
  );
}

/** The vendor's home: the getting-started checklist until everything is done. */
export function Dashboard() {
  const { state, reload } = useLoad(loadChecklist, "dashboard");

  if (state.status === "loading") return <LoadingState label="Loading your setup…" />;
  if (state.status === "error") {
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load your dashboard"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      </div>
    );
  }

  const steps = buildChecklist(state.data);
  const done = steps.filter((s) => s.done).length;
  const next = steps.find((s) => !s.done);
  const { verification, properties } = state.data;

  return (
    <div className="page">
      <header className="page__header page__header--row">
        <div>
          <h1 className="page__title">{next ? "Get ready to host" : "You're all set"}</h1>
          <p className="page__lead">
            {next
              ? "Finish these steps so talent can trust your gigs."
              : "Your business is verified. Post a gig to start getting applications."}
          </p>
        </div>
        <Link href="/console/gigs/new" className="button button--primary">
          Post a gig
        </Link>
      </header>

      <section className="panel" aria-labelledby="checklist-title">
        <div className="panel__header panel__header--row">
          <h2 id="checklist-title" className="panel__title">
            Setup checklist
          </h2>
          <p className="checklist__count">
            {done} of {steps.length} done
          </p>
        </div>
        <progress className="progress" max={steps.length} value={done} aria-label="Setup progress">
          {done} of {steps.length}
        </progress>
        <ol className="checklist">
          {steps.map((step) => (
            <li
              key={step.id}
              className={`checklist__item${step === next ? " checklist__item--next" : ""}`}
            >
              <CheckIcon done={step.done} />
              <div className="checklist__body">
                <h3 className="checklist__title">
                  {step.title}{" "}
                  <span className="visually-hidden">{step.done ? "(done)" : "(to do)"}</span>
                </h3>
                <p className="checklist__text">{step.description}</p>
                {step.id === "verified" ? (
                  <div className="chip-row">
                    {verification.badges.map((b) => (
                      <Chip key={b.kind} tone="success">
                        {BADGE_LABELS[b.kind]}
                      </Chip>
                    ))}
                    {properties.map((p) => (
                      <span key={p.id} className="chip-row__pair">
                        {p.name}: <VerificationChip status={p.verification_status} />
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <Link
                href={step.href}
                className={`button ${step === next ? "button--primary" : "button--ghost"}`}
              >
                {step.action}
                <span className="visually-hidden">: {step.title}</span>
              </Link>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
