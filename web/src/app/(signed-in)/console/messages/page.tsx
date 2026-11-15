import type { Metadata } from "next";

import { Inbox } from "./Inbox";

export const metadata: Metadata = { title: "Messages · Barterly" };

export default function MessagesPage() {
  return <Inbox />;
}
