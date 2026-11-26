import type { Metadata } from "next";

import { ArrivalsPage } from "./ArrivalsPage";

export const metadata: Metadata = { title: "Arrivals · Barterly" };

export default function Arrivals() {
  return <ArrivalsPage />;
}
