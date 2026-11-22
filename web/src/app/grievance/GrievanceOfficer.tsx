"use client";

import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { useLoad } from "@/lib/hooks/useLoad";

/** The officer's name and contact, from the API (they're configuration, not code). */
export function GrievanceOfficer() {
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/privacy/grievance-officer/")),
    "grievance-officer",
  );
  if (state.status === "loading") return <LoadingState label="Loading contact details…" />;
  if (state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load the contact details"
        description={`${describeError(state.error)} You can also write to grievance@barterly.in.`}
        retry={() => void reload()}
      />
    );
  }
  const officer = state.data;
  return (
    <section className="legal__card" aria-labelledby="officer-title">
      <h2 id="officer-title">Contact</h2>
      <dl className="legal__contact">
        <dt>Name</dt>
        <dd>{officer.name}</dd>
        <dt>Email</dt>
        <dd>
          <a href={`mailto:${officer.email}`}>{officer.email}</a>
        </dd>
        {officer.phone ? (
          <>
            <dt>Phone</dt>
            <dd>
              <a href={`tel:${officer.phone}`}>{officer.phone}</a>
            </dd>
          </>
        ) : null}
        <dt>Address</dt>
        <dd>{officer.address}</dd>
        <dt>Hours</dt>
        <dd>{officer.hours}</dd>
      </dl>
      <p>
        We acknowledge complaints within {officer.acknowledge_hours} hours and resolve them within{" "}
        {officer.resolve_days} days.
      </p>
    </section>
  );
}
