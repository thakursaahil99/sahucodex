"use client";

import { Trophy } from "lucide-react";
import Link from "next/link";

import { Countdown } from "@/components/contests/countdown";
import { PhaseBadge } from "@/components/contests/phase-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useContests } from "@/lib/contests/api";
import type { ContestListItem } from "@/lib/contests/types";
import { formatDate } from "@/lib/utils";

function ContestCard({ contest }: { contest: ContestListItem }) {
  return (
    <Link href={`/contests/${contest.slug}`} className="block">
      <Card className="transition-colors hover:border-primary/40">
        <CardHeader>
          <div className="flex items-start justify-between gap-3">
            <CardTitle className="text-lg">{contest.title}</CardTitle>
            <PhaseBadge phase={contest.phase} />
          </div>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p>
            {formatDate(contest.start_time, { dateStyle: "medium", timeStyle: "short" })} –{" "}
            {formatDate(contest.end_time, { dateStyle: "medium", timeStyle: "short" })}
          </p>
          <p>
            {contest.problem_count} problem{contest.problem_count === 1 ? "" : "s"}
            {contest.phase === "upcoming" && (
              <>
                {" "}
                · starts in <Countdown target={contest.start_time} />
              </>
            )}
            {contest.phase === "running" && (
              <>
                {" "}
                · ends in <Countdown target={contest.end_time} />
              </>
            )}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}

export function ContestsList() {
  const { data, isPending, isError, refetch } = useContests();

  if (isPending) {
    return (
      <div className="space-y-3" role="status" aria-label="Loading contests">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
        Couldn&apos;t load contests.{" "}
        <button type="button" onClick={() => refetch()} className="text-link underline underline-offset-2">
          Try again
        </button>
      </div>
    );
  }
  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-10 text-center">
        <Trophy className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <p className="mt-3 font-medium">No contests yet</p>
        <p className="mt-1 text-sm text-muted-foreground">Check back soon — new contests appear here as they&apos;re scheduled.</p>
      </div>
    );
  }

  const running = data.filter((c) => c.phase === "running");
  const upcoming = data.filter((c) => c.phase === "upcoming");
  const ended = data.filter((c) => c.phase === "ended");

  return (
    <div className="space-y-8">
      {running.length > 0 && (
        <section aria-label="Running contests">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase">Running now</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {running.map((c) => (
              <ContestCard key={c.slug} contest={c} />
            ))}
          </div>
        </section>
      )}
      {upcoming.length > 0 && (
        <section aria-label="Upcoming contests">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase">Upcoming</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {upcoming.map((c) => (
              <ContestCard key={c.slug} contest={c} />
            ))}
          </div>
        </section>
      )}
      {ended.length > 0 && (
        <section aria-label="Past contests">
          <h2 className="mb-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase">Past</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {ended.map((c) => (
              <ContestCard key={c.slug} contest={c} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
