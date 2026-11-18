"use client";

import { EmptyState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { useLoad } from "@/lib/hooks/useLoad";

import { SectionPage } from "../SectionPage";

/** Talent search is on Growth and Pro: other plans see how to get it. */
export function TalentSearchPage() {
  const { state } = useLoad(() => unwrap(api.GET("/api/v1/billing/")), "billing");
  if (state.status === "loading") return <LoadingState label="Loading…" />;
  if (state.status === "ready" && !state.data.entitlements.features.talent_search) {
    return (
      <div className="page">
        <header className="page__header">
          <h1 className="page__title">Talent search</h1>
        </header>
        <EmptyState
          title="Talent search is on Growth and Pro"
          description={`You're on ${state.data.entitlements.plan_name}. Upgrade to search talent by skill, place and dates, and invite them to apply.`}
          action={{ label: "See plans", href: "/console/billing" }}
        />
      </div>
    );
  }
  return <SectionPage href="/console/talent" />;
}
