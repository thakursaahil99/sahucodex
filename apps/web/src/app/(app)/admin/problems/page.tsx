import type { Metadata } from "next";
import { Suspense } from "react";

import { AdminProblemsTable } from "@/components/admin/admin-problems-table";

export const metadata: Metadata = { title: "Manage problems" };

export default function AdminProblemsPage() {
  return (
    <Suspense>
      <AdminProblemsTable />
    </Suspense>
  );
}
