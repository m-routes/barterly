import type { Metadata } from "next";

import { SectionPage } from "../SectionPage";

export const metadata: Metadata = { title: "Analytics · Barterly" };

export default function AnalyticsPage() {
  return <SectionPage href="/console/analytics" />;
}
