"use client";

import Link from "next/link";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { VerificationChip } from "@/components/ui/StatusChip";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { useLoad } from "@/lib/hooks/useLoad";
import { PROPERTY_TYPE_LABELS } from "@/lib/vendor/labels";

export function PropertyList() {
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/properties/", { params: { query: { page_size: 50 } } })),
    "properties",
  );

  return (
    <div className="page">
      <header className="page__header page__header--row">
        <h1 className="page__title">Properties</h1>
        <Link href="/console/properties/new" className="button button--primary">
          Add a property
        </Link>
      </header>
      {state.status === "loading" ? <LoadingState label="Loading your properties…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your properties"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length === 0 ? (
        <EmptyState
          title="No properties yet"
          description="Add the place talent will stay and work. Each gig belongs to a property."
          action={{ label: "Add a property", href: "/console/properties/new" }}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length > 0 ? (
        <ul className="card-list">
          {state.data.results.map((p) => (
            <li key={p.id} className="card-list__item">
              <div className="card-list__main">
                <Link href={`/console/properties/${p.id}`} className="card-list__title">
                  {p.name}
                </Link>
                <p className="card-list__meta">
                  {PROPERTY_TYPE_LABELS[p.property_type]} · {p.city} · {p.photos.length} photo
                  {p.photos.length === 1 ? "" : "s"}
                </p>
              </div>
              <VerificationChip status={p.verification_status} />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
