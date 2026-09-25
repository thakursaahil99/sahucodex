import type { Metadata } from "next";

import { AdminAnalytics } from "@/components/admin/admin-analytics";

export const metadata: Metadata = { title: "Analytics — Admin" };

export default function AdminAnalyticsPage() {
  return <AdminAnalytics />;
}
