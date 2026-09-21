import type { Metadata } from "next";

import { ProblemEditor } from "@/components/admin/problem-editor";

export const metadata: Metadata = { title: "New problem" };

export default function NewProblemPage() {
  return <ProblemEditor />;
}
