"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { useMutation } from "@tanstack/react-query";
import { Flag } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { isApiError } from "@/lib/api/http";
import { reportContent } from "@/lib/community/api";
import type { TargetType } from "@/lib/community/types";
import { useAuthStore } from "@/lib/auth/store";

/** Flags a discussion or comment for a moderator to review. Never removes anything itself — see
 * docs/community.md's "reports never auto-remove content" rule. */
export function ReportButton({ targetType, targetId }: { targetType: TargetType; targetId: string }) {
  const authenticated = useAuthStore((s) => s.status === "authenticated");
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  const report = useMutation({
    mutationFn: () => reportContent(targetType, targetId, reason.trim()),
    onSuccess: () => {
      toast.success("Reported. A moderator will take a look.");
      setOpen(false);
      setReason("");
    },
    onError: (error) => {
      toast.error(isApiError(error) ? error.message : "Couldn't send the report. Try again.");
    },
  });

  if (!authenticated) return null;

  return (
    <AlertDialog.Root open={open} onOpenChange={setOpen}>
      <AlertDialog.Trigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-destructive"
        >
          <Flag className="size-3.5" aria-hidden /> Report
        </Button>
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border bg-popover p-6 shadow-2xl data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
          <AlertDialog.Title className="text-lg font-semibold">
            Report this {targetType === "discussion" ? "thread" : "comment"}
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-2 text-sm text-muted-foreground">
            Tell a moderator what&apos;s wrong with it. They&apos;ll review before anything is removed.
          </AlertDialog.Description>
          <Textarea
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. spam, off-topic, gives away the solution…"
            maxLength={2000}
            className="mt-4"
            rows={3}
          />
          <div className="mt-6 flex justify-end gap-2">
            <AlertDialog.Cancel asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </AlertDialog.Cancel>
            <Button
              type="button"
              variant="destructive"
              disabled={reason.trim().length === 0 || report.isPending}
              onClick={() => report.mutate()}
            >
              {report.isPending ? "Sending…" : "Send report"}
            </Button>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
