import type { Metadata } from "next";

import { Dashboard } from "./Dashboard";

export const metadata: Metadata = { title: "Dashboard · Barterly" };

export default function DashboardPage() {
  return <Dashboard />;
}
