import type { Metadata } from "next";

import { Pipeline } from "../../../applicants/pipeline/Pipeline";

export const metadata: Metadata = { title: "Applicants · Barterly" };

export default function GigApplicantsPage() {
  return <Pipeline />;
}
