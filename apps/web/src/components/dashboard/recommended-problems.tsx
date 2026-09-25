"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { DifficultyBadge } from "@/components/problems/difficulty-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecommendations } from "@/lib/problems/api";

/** "What to solve next", ranked from the caller's own solved-tag history and difficulty progression
 * (see apps/api/app/modules/problems/service.py's `recommend_problems`). Signed-in only. */
export function RecommendedProblems({ enabled }: { enabled: boolean }) {
  const { data, isPending, isError } = useRecommendations(enabled);

  if (!enabled) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="size-5 text-brand-cyan" aria-hidden /> Recommended for you
        </CardTitle>
        <CardDescription>Picked from what you&apos;ve solved so far.</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending && (
          <div className="space-y-2" role="status" aria-label="Loading recommendations">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        )}
        {isError && <p className="text-sm text-muted-foreground">Couldn&apos;t load recommendations.</p>}
        {data && data.length === 0 && (
          <p className="text-sm text-muted-foreground">No new problems to recommend right now — you&apos;re all caught up.</p>
        )}
        {data && data.length > 0 && (
          <ul className="divide-y">
            {data.slice(0, 5).map((problem) => (
              <li key={problem.slug}>
                <Link
                  href={`/problems/${problem.slug}`}
                  className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0 hover:text-brand-cyan"
                >
                  <span className="min-w-0 truncate font-medium">{problem.title}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    {problem.tags.slice(0, 1).map((tag) => (
                      <Badge key={tag.slug} variant="outline" className="font-normal">
                        {tag.name}
                      </Badge>
                    ))}
                    <DifficultyBadge difficulty={problem.difficulty} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
