import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { LoadingState } from "@/components/ui/states";
import { firebaseWebConfig } from "@/lib/server/env";

import { AgreementDetail } from "../AgreementDetail";

export const metadata: Metadata = { title: "Agreement · Barterly" };

/** Reads the Firebase config at request time: signing re-confirms the phone by OTP. */
async function ConfiguredAgreement() {
  await connection();
  return <AgreementDetail config={firebaseWebConfig()} />;
}

export default function AgreementPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading the agreement…" />}>
      <ConfiguredAgreement />
    </Suspense>
  );
}
