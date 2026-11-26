import type { Metadata } from "next";

import { HelpCenter } from "@/components/support/HelpCenter";

export const metadata: Metadata = { title: "Help and feedback · Barterly" };

export default function ConsoleHelpPage() {
  return <HelpCenter basePath="/console/help" screen="console/help" />;
}
