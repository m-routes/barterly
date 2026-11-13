import type { Metadata } from "next";

import { SectionPage } from "../SectionPage";

export const metadata: Metadata = { title: "Gigs · Barterly" };

export default function GigsPage() {
  return <SectionPage href="/console/gigs" />;
}
