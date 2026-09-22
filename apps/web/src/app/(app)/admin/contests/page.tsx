import type { Metadata } from "next";

import { AdminContestsTable } from "@/components/admin/admin-contests-table";

export const metadata: Metadata = { title: "Admin · Contests" };

export default function AdminContestsPage() {
  return <AdminContestsTable />;
}
