import type { Metadata } from "next";

import { ApplicantDetail } from "../ApplicantDetail";

export const metadata: Metadata = { title: "Applicant · Barterly" };

export default function ApplicantPage() {
  return <ApplicantDetail />;
}
