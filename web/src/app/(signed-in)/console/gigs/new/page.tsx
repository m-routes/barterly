import type { Metadata } from "next";

import { NewGig } from "../builder/GigBuilderPages";

export const metadata: Metadata = { title: "Post a gig · Barterly" };

export default function NewGigPage() {
  return <NewGig />;
}
