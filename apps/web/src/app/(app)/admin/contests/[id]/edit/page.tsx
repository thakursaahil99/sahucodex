import type { Metadata } from "next";

import { ContestEditorPage } from "@/components/admin/contest-editor";

type Params = Promise<{ id: string }>;

export const metadata: Metadata = { title: "Edit contest" };

export default async function EditContestPage({ params }: { params: Params }) {
  const { id } = await params;
  return <ContestEditorPage contestId={id} />;
}
