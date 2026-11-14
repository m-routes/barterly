import type { Metadata } from "next";

import { EditProperty } from "../PropertyPages";

export const metadata: Metadata = { title: "Property · Barterly" };

export default function PropertyPage() {
  return <EditProperty />;
}
