"use client";

import { useParams } from "next/navigation";

import { ChatThread } from "@/components/chat/ChatThread";

export function Thread() {
  const { conversationId } = useParams<{ conversationId: string }>();
  return <ChatThread conversationId={conversationId} backHref="/console/messages" />;
}
