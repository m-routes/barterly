import type { Metadata } from "next";

import { PrivacySettings } from "@/components/privacy/PrivacySettings";

export const metadata: Metadata = { title: "Privacy · Barterly" };

export default function ConsolePrivacyPage() {
  return <PrivacySettings profileHref="/onboarding/vendor" />;
}
