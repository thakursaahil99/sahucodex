"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { StatusLabel, VerdictBadge, formatKb, formatMs } from "@/components/submissions/verdict-badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useSubmissions } from "@/lib/submissions/api";
import type { Verdict } from "@/lib/submissions/types";
import { formatDate } from "@/lib/utils";

const VERDICTS: Verdict[] = [
  "ACCEPTED",
  "WRONG_ANSWER",
  "TIME_LIMIT_EXCEEDED",
  "MEMORY_LIMIT_EXCEEDED",
  "RUNTIME_ERROR",
  "COMPILATION_ERROR",
  "SYSTEM_ERROR",
];

export function SubmissionsTable() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const verdict = (VERDICTS.includes(params.get("verdict") as Verdict) ? params.get("verdict") : "") as Verdict | "";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  const { data, isPending, isError, refetch } = useSubmissions({ page, verdict: verdict || undefined });

  function go(next: { verdict?: string; page?: number }) {
    const merged = new URLSearchParams();
    const v = next.verdict ?? verdict;
    const p = next.page ?? 1;
    if (v) merged.set("verdict", v);
    if (p > 1) merged.set("page", String(p));
    router.replace(merged.size ? `${pathname}?${merged}` : pathname);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Submissions</h1>
          <p className="mt-1 text-muted-foreground">Your SahuJudge submission history.</p>
        </div>
        <div className="w-56">
          <label htmlFor="verdict-filter" className="sr-only">
            Filter by verdict
          </label>
          <Select id="verdict-filter" value={verdict} onChange={(e) => go({ verdict: e.target.value })}>
            <option value="">All verdicts</option>
            {VERDICTS.map((v) => (
              <option key={v} value={v}>
                {v.replaceAll("_", " ")}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {isPending && (
        <div className="space-y-2" role="status" aria-label="Loading submissions">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-14" />
          ))}
        </div>
      )}
      {isError && (
        <div role="alert" className="flex items-center justify-between rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm">
          Couldn&apos;t load your submissions.
          <Button size="sm" variant="outline" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="rounded-xl border border-dashed p-12 text-center">
          <p className="font-medium">No submissions {verdict ? "with this verdict " : ""}yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Solve a <Link href="/problems" className="underline">problem</Link> and submit your solution to see it here.
          </p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full min-w-[46rem] text-sm">
            <caption className="sr-only">Submissions</caption>
            <thead className="bg-muted/50 text-left text-xs tracking-wide text-muted-foreground uppercase">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">Problem</th>
                <th scope="col" className="px-4 py-3 font-medium">Verdict</th>
                <th scope="col" className="px-4 py-3 font-medium">Language</th>
                <th scope="col" className="px-4 py-3 font-medium">Runtime</th>
                <th scope="col" className="px-4 py-3 font-medium">Memory</th>
                <th scope="col" className="px-4 py-3 font-medium">Submitted</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((row) => (
                <tr key={row.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <Link href={`/submissions/${row.id}`} className="font-medium hover:underline">
                      {row.problem_title}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {row.passed_count}/{row.total_count} tests
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    {row.verdict ? <VerdictBadge verdict={row.verdict} /> : <StatusLabel status={row.status} />}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{row.language}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatMs(row.runtime_ms)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{formatKb(row.memory_kb)}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatDate(row.created_at, { dateStyle: "medium", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.pages > 1 && (
        <nav aria-label="Pagination" className="flex items-center justify-between">
          <Button variant="outline" disabled={page <= 1} onClick={() => go({ page: page - 1 })}>
            Previous
          </Button>
          <p className="text-sm text-muted-foreground">
            Page {data.page} of {data.pages}
          </p>
          <Button variant="outline" disabled={page >= data.pages} onClick={() => go({ page: page + 1 })}>
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}
