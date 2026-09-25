"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { isApiError } from "@/lib/api/http";
import { createDiscussion, useDiscussions } from "@/lib/community/api";
import { timeAgo } from "@/lib/format";
import { useAuthStore } from "@/lib/auth/store";

function NewDiscussionForm({ problemSlug, onDone }: { problemSlug: string; onDone: () => void }) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: () => createDiscussion(problemSlug, { title: title.trim(), body: body.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["discussions", problemSlug] });
      setTitle("");
      setBody("");
      onDone();
    },
    onError: (error) => toast.error(isApiError(error) ? error.message : "Couldn't post that. Try again."),
  });

  return (
    <form
      className="space-y-3 rounded-xl border bg-card p-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim() && body.trim()) create.mutate();
      }}
    >
      <Input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Title — what's your question or note?"
        maxLength={200}
        autoFocus
        required
      />
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Details… (Markdown supported)"
        maxLength={20_000}
        rows={4}
        required
      />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={create.isPending}>
          {create.isPending ? "Posting…" : "Post"}
        </Button>
      </div>
    </form>
  );
}

export function DiscussionList({ problemSlug }: { problemSlug: string }) {
  const { data, isLoading } = useDiscussions(problemSlug);
  const authenticated = useAuthStore((s) => s.status === "authenticated");
  const [composing, setComposing] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {authenticated ? (
        composing ? (
          <NewDiscussionForm problemSlug={problemSlug} onDone={() => setComposing(false)} />
        ) : (
          <Button type="button" variant="outline" size="sm" onClick={() => setComposing(true)}>
            <Plus aria-hidden /> Start a discussion
          </Button>
        )
      ) : (
        <p className="text-sm text-muted-foreground">
          <Link href="/login" className="font-medium text-foreground underline underline-offset-2">
            Sign in
          </Link>{" "}
          to start or join a discussion.
        </p>
      )}

      {data && data.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No discussions yet — be the first to ask or share something about this problem.
        </p>
      )}

      <ul className="space-y-2">
        {data?.map((d) => (
          <li key={d.id}>
            <Link
              href={`/discussions/${d.id}`}
              className="block rounded-xl border bg-card p-4 transition-colors hover:border-foreground/30"
            >
              <p className="font-medium">{d.title}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span>{d.author.username ?? "[deleted]"}</span>
                <span>{timeAgo(d.created_at)}</span>
                <span className="inline-flex items-center gap-1">
                  <MessageSquare className="size-3.5" aria-hidden /> {d.comment_count}
                </span>
                <span>{d.vote_score >= 0 ? "+" : ""}{d.vote_score} votes</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
