"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { Countdown } from "@/components/contests/countdown";
import { PhaseBadge } from "@/components/contests/phase-badge";
import { StandingsTable } from "@/components/contests/standings-table";
import { isApiError } from "@/lib/api/http";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { registerForContest, useContest } from "@/lib/contests/api";
import { useAuthStore } from "@/lib/auth/store";
import { formatDate } from "@/lib/utils";

export function ContestOverview({ slug }: { slug: string }) {
  const { data: contest, isPending, isError, refetch } = useContest(slug);
  const signedIn = useAuthStore((s) => s.status === "authenticated");
  const queryClient = useQueryClient();

  const register = useMutation({
    mutationFn: () => registerForContest(slug),
    onSuccess: () => {
      toast.success("You're registered", { description: "Come back once the contest starts to solve and submit." });
      // Prefix match: covers every ["contest", viewerId, slug] key regardless of who's signed in.
      void queryClient.invalidateQueries({ queryKey: ["contest"] });
    },
    onError: (error) => {
      toast.error("Couldn't register", { description: isApiError(error) ? error.message : undefined });
    },
  });

  if (isPending) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading contest">
        <Skeleton className="h-9 w-1/2" />
        <Skeleton className="h-32" />
      </div>
    );
  }
  if (isError) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <h1 className="text-2xl font-bold">Couldn&apos;t load this contest</h1>
        <Button className="mt-4" onClick={() => refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold">{contest.title}</h1>
            <PhaseBadge phase={contest.phase} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {formatDate(contest.start_time, { dateStyle: "medium", timeStyle: "short" })} –{" "}
            {formatDate(contest.end_time, { dateStyle: "medium", timeStyle: "short" })}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {contest.phase === "upcoming" && (
            <span className="text-sm text-muted-foreground">
              Starts in <Countdown target={contest.start_time} onReach={() => refetch()} />
            </span>
          )}
          {contest.phase === "running" && (
            <span className="text-sm text-muted-foreground">
              Ends in <Countdown target={contest.end_time} onReach={() => refetch()} />
            </span>
          )}
          {signedIn && !contest.registered && contest.phase !== "ended" && (
            <Button onClick={() => register.mutate()} disabled={register.isPending}>
              Register
            </Button>
          )}
          {signedIn && contest.registered && <span className="text-sm font-medium text-success">Registered</span>}
          {!signedIn && (
            <Button asChild variant="outline">
              <Link href={`/login?next=/contests/${slug}`}>Sign in to register</Link>
            </Button>
          )}
        </div>
      </div>

      <Markdown>{contest.description || "_No description yet._"}</Markdown>

      <Tabs defaultValue="problems">
        <TabsList>
          <TabsTrigger value="problems">Problems</TabsTrigger>
          <TabsTrigger value="standings">Standings</TabsTrigger>
        </TabsList>

        <TabsContent value="problems" className="mt-4">
          {contest.phase === "upcoming" ? (
            <div className="rounded-lg border border-dashed p-8 text-center">
              <Lock className="mx-auto size-6 text-muted-foreground" aria-hidden />
              <p className="mt-2 font-medium">Problems are hidden until the contest starts</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {contest.problem_count} problem{contest.problem_count === 1 ? "" : "s"} · register now so you&apos;re ready.
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <caption className="sr-only">Contest problems</caption>
                <tbody className="divide-y">
                  {contest.problems.map((p) => (
                    <tr key={p.label}>
                      <td className="w-12 px-4 py-3 font-mono font-semibold">{p.label}</td>
                      <td className="px-4 py-3">
                        <Link href={`/contests/${slug}/${p.label}`} className="font-medium text-link hover:underline">
                          {p.title}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-right text-muted-foreground">{p.points} pts</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="standings" className="mt-4">
          <StandingsTable slug={slug} live={contest.phase === "running"} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
