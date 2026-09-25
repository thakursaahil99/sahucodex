"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Lock, MessageSquareOff, Unlock } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { hasRole } from "@sahucodex/shared";

import { ReportButton } from "@/components/community/report-button";
import { VoteButtons } from "@/components/community/vote-buttons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { isApiError } from "@/lib/api/http";
import { addComment, lockDiscussion, unlockDiscussion, useDiscussion } from "@/lib/community/api";
import type { CommentOut } from "@/lib/community/types";
import { timeAgo } from "@/lib/format";
import { useAuthStore } from "@/lib/auth/store";

function CommentRow({ comment, discussionId }: { comment: CommentOut; discussionId: string }) {
  return (
    <li className="flex gap-3 border-t py-4 first:border-t-0">
      <VoteButtons
        targetType="comment"
        targetId={comment.id}
        score={comment.vote_score}
        myVote={comment.my_vote}
        invalidateKey={["discussion", discussionId]}
        size="sm"
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{comment.author.username ?? "[deleted]"}</span>
          <span>{timeAgo(comment.created_at)}</span>
        </div>
        {comment.removed ? (
          <p className="mt-1.5 flex items-center gap-1.5 text-sm text-muted-foreground italic">
            <MessageSquareOff className="size-3.5" aria-hidden /> {comment.body}
          </p>
        ) : (
          <div className="mt-1.5 text-sm">
            <Markdown>{comment.body}</Markdown>
          </div>
        )}
        {!comment.removed && (
          <div className="mt-1">
            <ReportButton targetType="comment" targetId={comment.id} />
          </div>
        )}
      </div>
    </li>
  );
}

function CommentComposer({ discussionId, locked }: { discussionId: string; locked: boolean }) {
  const [body, setBody] = useState("");
  const queryClient = useQueryClient();
  const authenticated = useAuthStore((s) => s.status === "authenticated");

  const submit = useMutation({
    mutationFn: () => addComment(discussionId, { body: body.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["discussion", discussionId] });
      setBody("");
    },
    onError: (error) => toast.error(isApiError(error) ? error.message : "Couldn't post that reply. Try again."),
  });

  if (locked) {
    return (
      <p className="flex items-center gap-1.5 border-t pt-4 text-sm text-muted-foreground">
        <Lock className="size-3.5" aria-hidden /> This discussion is locked. No new replies.
      </p>
    );
  }

  if (!authenticated) {
    return (
      <p className="border-t pt-4 text-sm text-muted-foreground">
        <Link href="/login" className="font-medium text-foreground underline underline-offset-2">
          Sign in
        </Link>{" "}
        to reply.
      </p>
    );
  }

  return (
    <form
      className="space-y-2 border-t pt-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (body.trim()) submit.mutate();
      }}
    >
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Write a reply… (Markdown supported)"
        maxLength={10_000}
        rows={3}
        required
      />
      <div className="flex justify-end">
        <Button type="submit" size="sm" disabled={submit.isPending}>
          {submit.isPending ? "Posting…" : "Reply"}
        </Button>
      </div>
    </form>
  );
}

function LockToggle({ discussionId, locked }: { discussionId: string; locked: boolean }) {
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();

  const toggle = useMutation({
    mutationFn: () => (locked ? unlockDiscussion(discussionId) : lockDiscussion(discussionId)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["discussion", discussionId] });
      toast.success(locked ? "Discussion unlocked." : "Discussion locked.");
    },
    onError: (error) => toast.error(isApiError(error) ? error.message : "Couldn't update the lock. Try again."),
  });

  if (!hasRole(user?.roles, "MODERATOR")) return null;

  return (
    <Button variant="outline" size="sm" onClick={() => toggle.mutate()} disabled={toggle.isPending}>
      {locked ? <Unlock className="size-3.5" aria-hidden /> : <Lock className="size-3.5" aria-hidden />}
      {locked ? "Unlock" : "Lock"}
    </Button>
  );
}

export function DiscussionThread({ discussionId }: { discussionId: string }) {
  const { data, isLoading, error } = useDiscussion(discussionId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  if (error || !data) {
    return <p className="py-12 text-center text-sm text-muted-foreground">This discussion couldn&apos;t be found.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex gap-3">
        <VoteButtons
          targetType="discussion"
          targetId={data.id}
          score={data.vote_score}
          myVote={data.my_vote}
          invalidateKey={["discussion", discussionId]}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold">{data.title}</h1>
            {data.removed && <Badge variant="outline">Removed by a moderator</Badge>}
            {data.locked && (
              <Badge variant="outline" className="gap-1">
                <Lock className="size-3" aria-hidden /> Locked
              </Badge>
            )}
            <LockToggle discussionId={data.id} locked={data.locked} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{data.author.username ?? "[deleted]"}</span>
            <span>{timeAgo(data.created_at)}</span>
            <Link href={`/problems/${data.problem_slug}`} className="underline underline-offset-2">
              {data.problem_slug}
            </Link>
          </div>
          <div className="mt-4 text-sm">
            <Markdown>{data.body}</Markdown>
          </div>
          {!data.removed && (
            <div className="mt-2">
              <ReportButton targetType="discussion" targetId={data.id} />
            </div>
          )}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">
          {data.comments.length} {data.comments.length === 1 ? "reply" : "replies"}
        </h2>
        <ul>
          {data.comments.map((c) => (
            <CommentRow key={c.id} comment={c} discussionId={discussionId} />
          ))}
        </ul>
        <CommentComposer discussionId={discussionId} locked={data.locked} />
      </div>
    </div>
  );
}
