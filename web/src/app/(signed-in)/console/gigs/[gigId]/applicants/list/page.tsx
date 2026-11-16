import type { Metadata } from "next";

import { ApplicantTable } from "../../../../applicants/ApplicantTable";

export const metadata: Metadata = { title: "Applicants (list) · Barterly" };

export default function GigApplicantsListPage() {
  return <ApplicantTable />;
}
