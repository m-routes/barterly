import type { Metadata } from "next";

import { PropertyList } from "./PropertyList";

export const metadata: Metadata = { title: "Properties · Barterly" };

export default function PropertiesPage() {
  return <PropertyList />;
}
