"use client";

import { FilePlus2 } from "lucide-react";
import Link from "next/link";

import { PhaseBadge } from "@/components/contests/phase-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminContests } from "@/lib/contests/api";
import { formatDate } from "@/lib/utils";

function phaseOf(startIso: string, endIso: string): "upcoming" | "running" | "ended" {
  const now = Date.now();
  if (now < new Date(startIso).getTime()) return "upcoming";
  if (now <= new Date(endIso).getTime()) return "running";
  return "ended";
}

export function AdminContestsTable() {
  const { data, isPending, isError } = useAdminContests();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Contests</h1>
        <Button asChild variant="gradient">
          <Link href="/admin/contests/new">
            <FilePlus2 aria-hidden /> New contest
          </Link>
        </Button>
      </div>

      {isPending && (
        <div className="space-y-2" role="status" aria-label="Loading contests">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      )}
      {isError && <p className="text-sm text-muted-foreground">Couldn&apos;t load contests.</p>}
      {data && data.length === 0 && <p className="text-sm text-muted-foreground">No contests yet.</p>}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">Contests</caption>
            <thead className="bg-muted/50 text-left text-xs tracking-wide text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Title</th>
                <th scope="col" className="px-4 py-2 font-medium">Status</th>
                <th scope="col" className="px-4 py-2 font-medium">Phase</th>
                <th scope="col" className="px-4 py-2 font-medium">Problems</th>
                <th scope="col" className="px-4 py-2 font-medium">Starts</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.map((contest) => (
                <tr key={contest.id}>
                  <td className="px-4 py-3">
                    <Link href={`/admin/contests/${contest.id}/edit`} className="font-medium text-link hover:underline">
                      {contest.title}
                    </Link>
                    <div className="text-xs text-muted-foreground">{contest.slug}</div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={contest.published ? "success" : "outline"}>{contest.published ? "Published" : "Draft"}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <PhaseBadge phase={phaseOf(contest.start_time, contest.end_time)} />
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{contest.problems.length}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDate(contest.start_time, { dateStyle: "medium", timeStyle: "short" })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
