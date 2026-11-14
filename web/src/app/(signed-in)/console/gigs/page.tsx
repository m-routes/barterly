import type { Metadata } from "next";

import { GigList } from "./GigList";

export const metadata: Metadata = { title: "Gigs · Barterly" };

export default function GigsPage() {
  return <GigList />;
}
