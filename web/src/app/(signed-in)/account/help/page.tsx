"use client";

import { HelpCenter } from "@/components/support/HelpCenter";

import { AccountFrame } from "./AccountFrame";

export default function AccountHelpPage() {
  return (
    <AccountFrame>
      <HelpCenter basePath="/account/help" screen="account/help" />
    </AccountFrame>
  );
}
