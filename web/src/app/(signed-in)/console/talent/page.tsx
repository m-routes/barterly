import type { Metadata } from "next";

import { TalentSearchPage } from "./TalentSearchPage";

export const metadata: Metadata = { title: "Talent search · Barterly" };

export default function TalentSearch() {
  return <TalentSearchPage />;
}
