import type { Metadata } from "next";

import { SectionPage } from "../SectionPage";

export const metadata: Metadata = { title: "Agreements · Barterly" };

export default function AgreementsPage() {
  return <SectionPage href="/console/agreements" />;
}
