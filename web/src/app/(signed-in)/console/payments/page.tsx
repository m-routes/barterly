import type { Metadata } from "next";

import { SectionPage } from "../SectionPage";

export const metadata: Metadata = { title: "Payments · Barterly" };

export default function PaymentsPage() {
  return <SectionPage href="/console/payments" />;
}
