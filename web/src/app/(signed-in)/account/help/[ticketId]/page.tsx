"use client";

import { useParams } from "next/navigation";

import { SupportThread } from "@/components/support/SupportThread";

import { AccountFrame } from "../AccountFrame";

export default function AccountHelpThreadPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  return (
    <AccountFrame>
      <SupportThread ticketId={ticketId} backHref="/account/help" />
    </AccountFrame>
  );
}
