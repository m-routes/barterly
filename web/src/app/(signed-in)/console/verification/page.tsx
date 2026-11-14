import type { Metadata } from "next";

import { VerificationPage } from "./VerificationPage";

export const metadata: Metadata = { title: "Verification · Barterly" };

export default function Page() {
  return <VerificationPage />;
}
