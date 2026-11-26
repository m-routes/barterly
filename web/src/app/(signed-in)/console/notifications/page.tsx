import type { Metadata } from "next";

import { NotificationInbox } from "./NotificationInbox";

export const metadata: Metadata = { title: "Notifications · Barterly" };

export default function NotificationsPage() {
  return <NotificationInbox />;
}
