import type { Metadata } from "next";

import { SectionPage } from "../SectionPage";

export const metadata: Metadata = { title: "Applicants · Barterly" };

export default function ApplicantsPage() {
  return <SectionPage href="/console/applicants" />;
}
