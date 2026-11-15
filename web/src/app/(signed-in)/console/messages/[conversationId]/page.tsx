import type { Metadata } from "next";

import { Thread } from "../Thread";

export const metadata: Metadata = { title: "Chat · Barterly" };

export default function ConversationPage() {
  return <Thread />;
}
