"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";

import { StatusLabel, VerdictBadge, formatKb, formatMs } from "@/components/submissions/verdict-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api/http";
import { useSubmission } from "@/lib/submissions/api";
import { useJudgeSocket } from "@/lib/submissions/socket";
import { isPending } from "@/lib/submissions/types";
import { formatDate } from "@/lib/utils";

export function SubmissionDetailView({ id }: { id: string }) {
  const submission = useSubmission(id);
  const queryClient = useQueryClient();
  const watching = submission.isPending || isPending(submission.data?.status);

  useJudgeSocket(
    useCallback(
      (event) => {
        if (event.data.submission_id === id) void queryClient.invalidateQueries({ queryKey: ["submission", id] });
      },
      [id, queryClient],
    ),
    watching,
  );

  if (submission.isPending) return <DetailSkeleton />;

  if (submission.isError) {
    const missing = isApiError(submission.error) && submission.error.status === 404;
    return (
      <div className="mx-auto max-w-md py-24 text-center">
        <h1 className="text-2xl font-bold">{missing ? "Submission not found" : "Couldn't load this submission"}</h1>
        <p className="mt-2 text-muted-foreground">
          {missing ? "It may not be yours, or the link is wrong." : "Check your connection and try again."}
        </p>
        <Button asChild variant="outline" className="mt-6">
          <Link href="/submissions">
            <ArrowLeft aria-hidden /> All submissions
          </Link>
        </Button>
      </div>
    );
  }

  const s = submission.data;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link href="/submissions">
            <ArrowLeft aria-hidden /> All submissions
          </Link>
        </Button>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">
            <Link href={`/problems/${s.problem_slug}`} className="hover:underline">
              {s.problem_title}
            </Link>
          </h1>
          {s.verdict ? <VerdictBadge verdict={s.verdict} /> : <StatusLabel status={s.status} />}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {s.language} · submitted {formatDate(s.created_at, { dateStyle: "medium", timeStyle: "short" })}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Result</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(s.status === "QUEUED" || s.status === "RUNNING") && (
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {s.status === "QUEUED" ? "Queued for judging…" : "Running…"}
            </p>
          )}
          <div className="flex flex-wrap gap-6 text-sm">
            <Stat label="Tests passed" value={`${s.passed_count} / ${s.total_count}`} />
            <Stat label="Runtime" value={formatMs(s.runtime_ms)} />
            <Stat label="Memory" value={formatKb(s.memory_kb)} />
            {s.time_limit_ms !== null && <Stat label="Time limit" value={formatMs(s.time_limit_ms)} />}
          </div>
          {s.message && <p className="text-sm text-warning">{s.message}</p>}
          {s.compile_output && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Compiler output</p>
              <pre className="mt-1 max-h-64 overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-[13px] whitespace-pre-wrap">
                {s.compile_output}
              </pre>
            </div>
          )}
        </CardContent>
      </Card>

      {s.test_results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Test results</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <caption className="sr-only">Public test results</caption>
                <thead className="bg-muted/50 text-left text-xs tracking-wide text-muted-foreground uppercase">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">Test</th>
                    <th scope="col" className="px-3 py-2 font-medium">Verdict</th>
                    <th scope="col" className="px-3 py-2 font-medium">Runtime</th>
                    <th scope="col" className="px-3 py-2 font-medium">Memory</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {s.test_results.map((t) => (
                    <tr key={t.position}>
                      <td className="px-3 py-2">#{t.position}</td>
                      <td className="px-3 py-2">
                        <VerdictBadge verdict={t.verdict} />
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{formatMs(t.runtime_ms)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{formatKb(t.memory_kb)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {s.total_count > s.test_results.length && (
              <p className="mt-3 text-xs text-muted-foreground">
                {s.total_count - s.test_results.length} additional hidden test
                {s.total_count - s.test_results.length === 1 ? "" : "s"} ran — only their verdict counted above; their
                data is never shown.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Source code</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/40 p-3 font-mono text-[13px] whitespace-pre-wrap">
            {s.source_code}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="font-medium">{value}</p>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-6" role="status" aria-label="Loading submission">
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-40" />
      <Skeleton className="h-56" />
    </div>
  );
}
