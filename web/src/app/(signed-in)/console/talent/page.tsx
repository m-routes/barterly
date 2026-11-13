import type { Metadata } from "next";

import { SectionPage } from "../SectionPage";

export const metadata: Metadata = { title: "Talent search · Barterly" };

export default function TalentSearchPage() {
  return <SectionPage href="/console/talent" />;
}
