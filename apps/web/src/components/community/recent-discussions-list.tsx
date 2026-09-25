"use client";

import { MessageSquare } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecentDiscussions } from "@/lib/community/api";
import { timeAgo } from "@/lib/format";

/** Cross-problem feed for the `/discussions` landing page — every problem's thread in one place, newest first. */
export function RecentDiscussionsList() {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useRecentDiscussions(page);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  if (data && data.items.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-muted-foreground">
        No discussions yet — open any problem and start one.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <ul className="space-y-2">
        {data?.items.map((d) => (
          <li key={d.id}>
            <Link
              href={`/discussions/${d.id}`}
              className="block rounded-xl border bg-card p-4 transition-colors hover:border-foreground/30"
            >
              <div className="flex items-center gap-2">
                <span className="rounded-full border px-2 py-0.5 text-xs font-medium text-muted-foreground">
                  {d.problem_title}
                </span>
              </div>
              <p className="mt-1.5 font-medium">{d.title}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>{d.author.username ?? "[deleted]"}</span>
                <span>{timeAgo(d.created_at)}</span>
                <span className="inline-flex items-center gap-1">
                  <MessageSquare className="size-3.5" aria-hidden /> {d.comment_count}
                </span>
                <span>
                  {d.vote_score >= 0 ? "+" : ""}
                  {d.vote_score} votes
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {data && data.pages > 1 && (
        <nav aria-label="Pagination" className="flex items-center justify-between">
          <Button variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <p className="text-sm text-muted-foreground">
            Page {data.page} of {data.pages}
          </p>
          <Button variant="outline" disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}
