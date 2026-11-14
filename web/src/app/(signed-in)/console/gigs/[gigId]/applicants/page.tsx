import type { Metadata } from "next";

import { ApplicantTable } from "../../../applicants/ApplicantTable";

export const metadata: Metadata = { title: "Applicants · Barterly" };

export default function GigApplicantsPage() {
  return <ApplicantTable />;
}
