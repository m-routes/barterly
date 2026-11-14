import type { Metadata } from "next";

import { ApplicantsIndex } from "./ApplicantsIndex";

export const metadata: Metadata = { title: "Applicants · Barterly" };

export default function ApplicantsPage() {
  return <ApplicantsIndex />;
}
