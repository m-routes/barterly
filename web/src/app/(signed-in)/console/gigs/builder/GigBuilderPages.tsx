"use client";

import { useParams } from "next/navigation";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { Gig, Property, Skill } from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";

import { GigBuilder } from "./GigBuilder";

type BuilderData = { gig: Gig | null; properties: Property[]; skills: Skill[] };

async function loadBuilder(gigId: string | null): Promise<BuilderData> {
  const [gig, properties, skills] = await Promise.all([
    gigId
      ? unwrap(api.GET("/api/v1/gigs/{gig_id}/", { params: { path: { gig_id: gigId } } }))
      : Promise.resolve(null),
    unwrap(api.GET("/api/v1/properties/", { params: { query: { page_size: 50 } } })),
    // Skills only improve matching; the builder works without them.
    unwrap(api.GET("/api/v1/profiles/skills/")).catch(() => [] as Skill[]),
  ]);
  return { gig, properties: properties.results, skills };
}

function Builder({ gigId }: { gigId: string | null }) {
  const { state, reload } = useLoad(() => loadBuilder(gigId), gigId ?? "new");
  if (state.status === "loading") return <LoadingState label="Loading the gig builder…" />;
  if (state.status === "error") {
    return (
      <div className="page">
        <ErrorState
          title={gigId ? "We couldn't load this gig" : "We couldn't open the gig builder"}
          description={describeError(state.error)}
          retry={() => void reload()}
          action={{ label: "All gigs", href: "/console/gigs" }}
        />
      </div>
    );
  }
  const { gig, properties, skills } = state.data;
  if (!properties.length) {
    return (
      <div className="page">
        <EmptyState
          title="Add a property first"
          description="Every gig happens at one of your properties. Add it, with its map pin, then come back."
          action={{ label: "Add a property", href: "/console/properties/new" }}
        />
      </div>
    );
  }
  return <GigBuilder initialGig={gig} properties={properties} skills={skills} />;
}

export function NewGig() {
  return <Builder gigId={null} />;
}

export function EditGig() {
  const { gigId } = useParams<{ gigId: string }>();
  return <Builder gigId={gigId} />;
}
