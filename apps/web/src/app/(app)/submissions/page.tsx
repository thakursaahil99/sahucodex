import type { Metadata } from "next";
import { Suspense } from "react";

import { SubmissionsTable } from "@/components/submissions/submissions-table";

export const metadata: Metadata = { title: "Submissions" };

export default function SubmissionsPage() {
  // useSearchParams() (filters live in the URL) needs a Suspense boundary.
  return (
    <Suspense>
      <SubmissionsTable />
    </Suspense>
  );
}
