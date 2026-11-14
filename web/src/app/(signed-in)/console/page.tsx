import type { Metadata } from "next";

import { SectionPage } from "./SectionPage";

export const metadata: Metadata = { title: "Dashboard · Barterly" };

export default function DashboardPage() {
  return <SectionPage href="/console" />;
}
