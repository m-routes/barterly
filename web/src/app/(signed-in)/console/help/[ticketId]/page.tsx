"use client";

import { useParams } from "next/navigation";

import { SupportThread } from "@/components/support/SupportThread";

export default function ConsoleHelpThreadPage() {
  const { ticketId } = useParams<{ ticketId: string }>();
  return <SupportThread ticketId={ticketId} backHref="/console/help" />;
}
