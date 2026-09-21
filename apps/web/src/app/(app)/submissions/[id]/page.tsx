import type { Metadata } from "next";

import { SubmissionDetailView } from "@/components/submissions/submission-detail";

export const metadata: Metadata = { title: "Submission" };

export default async function SubmissionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SubmissionDetailView id={id} />;
}
