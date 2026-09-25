import type { Metadata } from "next";

import { DiscussionThread } from "@/components/community/discussion-thread";

export const metadata: Metadata = { title: "Discussion" };

type Params = Promise<{ id: string }>;

export default async function DiscussionPage({ params }: { params: Params }) {
  const { id } = await params;
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <DiscussionThread discussionId={id} />
    </div>
  );
}
