import type { Metadata } from "next";

import { RecentDiscussionsList } from "@/components/community/recent-discussions-list";

export const metadata: Metadata = {
  title: "Discussions",
  description: "Recent discussions across every problem.",
};

export default function DiscussionsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-bold tracking-tight">Discussions</h1>
      <p className="mt-1 text-muted-foreground">Recent discussions across every problem.</p>
      <div className="mt-6">
        <RecentDiscussionsList />
      </div>
    </div>
  );
}
