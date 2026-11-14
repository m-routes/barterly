import type { Metadata } from "next";

import { NewProperty } from "../PropertyPages";

export const metadata: Metadata = { title: "Add a property · Barterly" };

export default function NewPropertyPage() {
  return <NewProperty />;
}
