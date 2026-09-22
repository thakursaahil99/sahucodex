"use client";

import { Check, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useStandings } from "@/lib/contests/api";
import { cn } from "@/lib/utils";

/** Live standings, ICPC-style: points desc, penalty asc. `live` polls while the contest is running. */
export function StandingsTable({ slug, live }: { slug: string; live: boolean }) {
  const { data, isPending, isError } = useStandings(slug, { live });

  if (isPending) return <Skeleton className="h-64" />;
  if (isError) return <p className="text-sm text-muted-foreground">Couldn&apos;t load standings.</p>;
  if (data.rows.length === 0) {
    return <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">No one has registered yet.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[36rem] text-sm">
        <caption className="sr-only">Contest standings</caption>
        <thead className="bg-muted/50 text-left text-xs tracking-wide text-muted-foreground uppercase">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">#</th>
            <th scope="col" className="px-3 py-2 font-medium">Participant</th>
            <th scope="col" className="px-3 py-2 font-medium">Points</th>
            <th scope="col" className="px-3 py-2 font-medium">Penalty</th>
            {data.problems.map((p) => (
              <th key={p.label} scope="col" className="px-3 py-2 text-center font-medium" title={`${p.points} points`}>
                {p.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {data.rows.map((row) => (
            <tr key={row.username}>
              <td className="px-3 py-2 tabular-nums">{row.rank}</td>
              <td className="px-3 py-2 font-medium">{row.username}</td>
              <td className="px-3 py-2 tabular-nums">{row.total_points}</td>
              <td className="px-3 py-2 tabular-nums text-muted-foreground">{row.total_penalty_minutes}</td>
              {data.problems.map((p) => {
                const cell = row.cells[p.label];
                return (
                  <td key={p.label} className="px-3 py-2 text-center">
                    {!cell || (cell.attempts === 0 && !cell.solved) ? (
                      <span className="text-muted-foreground">—</span>
                    ) : cell.solved ? (
                      <span
                        className={cn("inline-flex items-center gap-1 font-medium text-success")}
                        title={`Solved · penalty ${cell.penalty_minutes}m`}
                      >
                        <Check className="size-3.5" aria-hidden />
                        {cell.penalty_minutes}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-destructive" title={`${cell.attempts} attempt(s)`}>
                        <X className="size-3.5" aria-hidden />
                        {cell.attempts}
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
