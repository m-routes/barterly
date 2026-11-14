import type { Metadata } from "next";

import { EditGig } from "../../builder/GigBuilderPages";

export const metadata: Metadata = { title: "Edit gig · Barterly" };

export default function EditGigPage() {
  return <EditGig />;
}
