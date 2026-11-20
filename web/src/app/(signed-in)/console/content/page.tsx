import type { Metadata } from "next";

import { ContentPage } from "./ContentPage";

export const metadata: Metadata = { title: "Content · Barterly" };

export default function Content() {
  return <ContentPage />;
}
