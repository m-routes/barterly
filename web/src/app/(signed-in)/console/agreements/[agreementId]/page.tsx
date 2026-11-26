import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { LoadingState } from "@/components/ui/states";
import { firebaseWebConfig, testNumbersAllowed } from "@/lib/server/env";

import { AgreementDetail } from "../AgreementDetail";

export const metadata: Metadata = { title: "Agreement · Barterly" };

type SearchParams = Promise<{ test_numbers?: string }>;

/**
 * Reads the Firebase config at request time: signing re-confirms the phone by OTP.
 * `?test_numbers=1` lets the acceptance suite confirm with a Firebase test number
 * (staging only; see testNumbersAllowed).
 */
async function ConfiguredAgreement({ searchParams }: { searchParams: SearchParams }) {
  await connection();
  const { test_numbers } = await searchParams;
  const config = firebaseWebConfig();
  return (
    <AgreementDetail
      config={config && { ...config, testNumbersOnly: testNumbersAllowed(test_numbers === "1") }}
    />
  );
}

export default function AgreementPage({ searchParams }: { searchParams: SearchParams }) {
  return (
    <Suspense fallback={<LoadingState label="Loading the agreement…" />}>
      <ConfiguredAgreement searchParams={searchParams} />
    </Suspense>
  );
}
