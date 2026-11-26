import type { Metadata } from "next";

import { NotificationSettings } from "../NotificationSettings";

export const metadata: Metadata = { title: "Notification settings · Barterly" };

export default function NotificationSettingsPage() {
  return <NotificationSettings />;
}
