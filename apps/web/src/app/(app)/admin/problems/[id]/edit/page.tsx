import type { Metadata } from "next";

import { ProblemEditor } from "@/components/admin/problem-editor";

export const metadata: Metadata = { title: "Edit problem" };

export default async function EditProblemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProblemEditor problemId={id} />;
}
