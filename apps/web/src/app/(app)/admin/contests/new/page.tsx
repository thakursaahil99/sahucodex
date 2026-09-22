import type { Metadata } from "next";

import { ContestEditorPage } from "@/components/admin/contest-editor";

export const metadata: Metadata = { title: "New contest" };

export default function NewContestPage() {
  return <ContestEditorPage />;
}
