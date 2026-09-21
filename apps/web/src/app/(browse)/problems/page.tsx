import type { Metadata } from "next";
import { Suspense } from "react";

import { ProblemsBrowser } from "@/components/problems/problems-browser";

export const metadata: Metadata = {
  title: "Problems",
  description: "Browse original practice problems by difficulty and topic.",
};

export default function ProblemsPage() {
  // useSearchParams() (filters live in the URL) needs a Suspense boundary.
  return (
    <Suspense>
      <ProblemsBrowser />
    </Suspense>
  );
}
