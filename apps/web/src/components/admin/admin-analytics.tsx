"use client";

import { AlertTriangle, Bot, MessageSquare, Trophy, Users, FileCode2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics, type AiFeatureUsage } from "@/lib/admin/api";

const PLATFORM_TILES: Array<{ key: keyof import("@/lib/admin/api").PlatformTotals; label: string; Icon: typeof Users }> = [
  { key: "users", label: "Users", Icon: Users },
  { key: "published_problems", label: "Published problems", Icon: FileCode2 },
  { key: "submissions", label: "Submissions (all time)", Icon: FileCode2 },
  { key: "submissions_last_30d", label: "Submissions (30d)", Icon: FileCode2 },
  { key: "published_contests", label: "Published contests", Icon: Trophy },
  { key: "discussions", label: "Discussions", Icon: MessageSquare },
];

export function AdminAnalytics() {
  const { data, isPending, isError, refetch } = useAnalytics();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
        <p className="mt-1 text-muted-foreground">A live snapshot of platform activity — nothing here is stored or pre-aggregated.</p>
      </div>

      {isError && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm">
          <span className="flex items-center gap-2">
            <AlertTriangle className="size-4" aria-hidden /> Couldn&apos;t load analytics.
          </span>
          <button onClick={() => refetch()} className="font-medium underline underline-offset-2">
            Retry
          </button>
        </div>
      )}

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {PLATFORM_TILES.map(({ key, label, Icon }) => (
              <Card key={key}>
                <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">{label}</CardTitle>
                  <Icon className="size-4 text-muted-foreground" aria-hidden />
                </CardHeader>
                <CardContent>
                  <p className="text-3xl font-bold">{data.platform[key]}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-5 text-brand-cyan" aria-hidden /> SahuCodeX AI usage
              </CardTitle>
              <CardDescription>Last {data.ai_usage.window_days} days, from the `AiUsage` rows recorded on every request.</CardDescription>
            </CardHeader>
            <CardContent>
              {data.ai_usage.total_requests === 0 ? (
                <p className="text-sm text-muted-foreground">No AI requests in this window.</p>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap gap-4 text-sm">
                    <span>
                      <span className="font-semibold">{data.ai_usage.total_requests}</span> total requests
                    </span>
                    <span>
                      <span className="font-semibold">{data.ai_usage.failed_requests}</span> failed
                      {data.ai_usage.total_requests > 0 && (
                        <span className="text-muted-foreground">
                          {" "}
                          ({Math.round((data.ai_usage.failed_requests / data.ai_usage.total_requests) * 100)}%)
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="py-2 pr-4 font-medium">Feature</th>
                          <th className="py-2 pr-4 font-medium">Requests</th>
                          <th className="py-2 pr-4 font-medium">Failed</th>
                          <th className="py-2 pr-4 font-medium">Avg duration</th>
                          <th className="py-2 font-medium">Avg reply length</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.ai_usage.by_feature.map((row) => (
                          <FeatureRow key={row.feature} row={row} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function FeatureRow({ row }: { row: AiFeatureUsage }) {
  return (
    <tr className="border-b last:border-0">
      <td className="py-2 pr-4 font-medium capitalize">{row.feature.toLowerCase()}</td>
      <td className="py-2 pr-4">{row.requests}</td>
      <td className="py-2 pr-4">
        {row.failed > 0 ? <Badge variant="warning">{row.failed}</Badge> : <span className="text-muted-foreground">0</span>}
      </td>
      <td className="py-2 pr-4 tabular-nums">{Math.round(row.avg_duration_ms)} ms</td>
      <td className="py-2 tabular-nums">{Math.round(row.avg_response_chars)} chars</td>
    </tr>
  );
}
