"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { castVote, removeVote } from "@/lib/community/api";
import type { TargetType } from "@/lib/community/types";
import { useAuthStore } from "@/lib/auth/store";
import { cn } from "@/lib/utils";

/** Up/down vote pair for a discussion or comment. Clicking the already-active direction removes the vote
 * (matches the API's PUT-to-set / DELETE-to-clear contract); the other direction switches it. */
export function VoteButtons({
  targetType,
  targetId,
  score,
  myVote,
  invalidateKey,
  size = "default",
}: {
  targetType: TargetType;
  targetId: string;
  score: number;
  myVote: number;
  /** react-query key to refetch after a successful vote (the discussion detail query, typically). */
  invalidateKey: unknown[];
  size?: "default" | "sm";
}) {
  const authenticated = useAuthStore((s) => s.status === "authenticated");
  const queryClient = useQueryClient();

  const vote = useMutation({
    mutationFn: (value: 1 | -1) => (myVote === value ? removeVote(targetType, targetId) : castVote(targetType, targetId, value)),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: invalidateKey }),
    onError: () => toast.error("Couldn't record your vote. Try again."),
  });

  const disabled = !authenticated || vote.isPending;
  const iconSize = size === "sm" ? "size-3.5" : "size-4";

  return (
    <div className="flex items-center gap-0.5 rounded-full border bg-card p-0.5">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={cn("size-6 rounded-full", myVote === 1 && "bg-brand-violet/15 text-brand-violet")}
        disabled={disabled}
        aria-pressed={myVote === 1}
        aria-label="Upvote"
        onClick={() => vote.mutate(1)}
      >
        <ChevronUp className={iconSize} aria-hidden />
      </Button>
      <span className="min-w-4 text-center text-xs font-semibold tabular-nums">{score}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={cn("size-6 rounded-full", myVote === -1 && "bg-destructive/15 text-destructive")}
        disabled={disabled}
        aria-pressed={myVote === -1}
        aria-label="Downvote"
        onClick={() => vote.mutate(-1)}
      >
        <ChevronDown className={iconSize} aria-hidden />
      </Button>
    </div>
  );
}
