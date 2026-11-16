import type { Metadata } from "next";

import { AgreementsIndex } from "./AgreementsIndex";

export const metadata: Metadata = { title: "Agreements · Barterly" };

export default function AgreementsPage() {
  return <AgreementsIndex />;
}
