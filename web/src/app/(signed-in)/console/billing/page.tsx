import type { Metadata } from "next";

import { BillingPage } from "./BillingPage";

export const metadata: Metadata = { title: "Billing · Barterly" };

export default function Billing() {
  return <BillingPage />;
}
