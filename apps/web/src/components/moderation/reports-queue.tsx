"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { isApiError } from "@/lib/api/http";
import { resolveReport, useReports } from "@/lib/community/api";
import type { ReportOut } from "@/lib/community/types";
import { timeAgo } from "@/lib/format";

const STATUS_VARIANT = {
  OPEN: "warning",
  RESOLVED: "success",
  DISMISSED: "outline",
} as const;

function ReportRow({ report }: { report: ReportOut }) {
  const queryClient = useQueryClient();
  const [pendingAction, setPendingAction] = useState<"remove_content" | "dismiss" | null>(null);

  const resolve = useMutation({
    mutationFn: (action: "remove_content" | "dismiss") => resolveReport(report.id, action),
    onMutate: (action) => setPendingAction(action),
    onSuccess: () => {
      toast.success("Report resolved.");
      void queryClient.invalidateQueries({ queryKey: ["moderation-reports"] });
    },
    onError: (error) => {
      toast.error(isApiError(error) ? error.message : "Couldn't resolve that report. Try again.");
    },
    onSettled: () => setPendingAction(null),
  });

  return (
    <li className="space-y-2 rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Badge variant={STATUS_VARIANT[report.status]}>{report.status}</Badge>
          <span className="capitalize">{report.target_type}</span>
          <span>reported by {report.reporter.username ?? "[deleted]"}</span>
          <span>{timeAgo(report.created_at)}</span>
        </div>
        {report.status === "OPEN" && (
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={resolve.isPending}
              onClick={() => resolve.mutate("dismiss")}
            >
              {pendingAction === "dismiss" && resolve.isPending ? (
                "Dismissing…"
              ) : (
                <>
                  <X className="size-3.5" aria-hidden /> Dismiss
                </>
              )}
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={resolve.isPending}
              onClick={() => resolve.mutate("remove_content")}
            >
              {pendingAction === "remove_content" && resolve.isPending ? (
                "Removing…"
              ) : (
                <>
                  <Check className="size-3.5" aria-hidden /> Remove content
                </>
              )}
            </Button>
          </div>
        )}
      </div>

      <p className="text-sm">
        <span className="font-medium">Reason: </span>
        {report.reason}
      </p>

      <p className="rounded-lg border bg-muted/40 p-2.5 text-sm text-muted-foreground">
        {report.target_removed
          ? "[already removed]"
          : (report.target_snippet ?? "[the reported content no longer exists]")}
      </p>
    </li>
  );
}

function ReportsList({ status }: { status?: "OPEN" | "RESOLVED" | "DISMISSED" }) {
  const { data, isLoading } = useReports(status);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (data && data.length === 0) {
    return <p className="py-12 text-center text-sm text-muted-foreground">Nothing here.</p>;
  }

  return <ul className="space-y-3">{data?.map((r) => <ReportRow key={r.id} report={r} />)}</ul>;
}

/** Moderator/admin queue — resolves reports filed via `ReportButton`. Gated server-side by `require_role`; the
 * `/moderation` nav link itself is only shown to moderators+ (see NAV_ITEMS' `minimumRole`). */
export function ReportsQueue() {
  return (
    <Tabs defaultValue="OPEN">
      <TabsList>
        <TabsTrigger value="OPEN">Open</TabsTrigger>
        <TabsTrigger value="RESOLVED">Resolved</TabsTrigger>
        <TabsTrigger value="DISMISSED">Dismissed</TabsTrigger>
      </TabsList>
      <TabsContent value="OPEN" className="mt-5">
        <ReportsList status="OPEN" />
      </TabsContent>
      <TabsContent value="RESOLVED" className="mt-5">
        <ReportsList status="RESOLVED" />
      </TabsContent>
      <TabsContent value="DISMISSED" className="mt-5">
        <ReportsList status="DISMISSED" />
      </TabsContent>
    </Tabs>
  );
}
