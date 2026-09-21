"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { ChatComposer } from "@/components/ai/chat-composer";
import { ChatThread } from "@/components/ai/chat-thread";
import { ConversationList } from "@/components/ai/conversation-list";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { deleteConversation, renameConversation, useAiStatus, useConversation, useConversations } from "@/lib/ai/api";
import { aiErrorMessage } from "@/lib/ai/errors";
import { useChat } from "@/lib/ai/use-chat";

/** The AI Assistant page: conversation history on the left, the open conversation on the right. */
export function Assistant({ problemSlug }: { problemSlug?: string }) {
  const status = useAiStatus();
  const conversations = useConversations();
  const chat = useChat(problemSlug);
  const active = useConversation(chat.activeId);
  const queryClient = useQueryClient();

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => renameConversation(id, title),
    onSuccess: (_, { id }) => {
      // The list shows the title, and so does the open conversation's header (its own cached copy).
      void queryClient.invalidateQueries({ queryKey: ["ai-conversations"] });
      void queryClient.invalidateQueries({ queryKey: ["ai-conversation", id] });
    },
    onError: (error) => toast.error("Couldn't rename it", { description: aiErrorMessage(error) }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onSuccess: (_, id) => {
      if (chat.activeId === id) chat.select(null);
      void queryClient.invalidateQueries({ queryKey: ["ai-conversations"] });
    },
    onError: (error) => toast.error("Couldn't delete it", { description: aiErrorMessage(error) }),
  });

  if (status.isPending) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-6" role="status" aria-label="Loading">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (status.data && !status.data.configured) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <Sparkles className="mx-auto size-8 text-brand-violet" aria-hidden />
        <h1 className="mt-4 text-2xl font-bold">SahuCodeX AI isn&apos;t set up yet</h1>
        <p className="mt-2 text-muted-foreground">
          The AI assistant runs on a local, open-source model through Ollama — no paid API. The person running this
          server needs to pull a model and set <code className="rounded bg-muted px-1">OLLAMA_MODEL</code>. Everything
          else on SahuCodeX works without it.
        </p>
        <Button asChild variant="outline" className="mt-6">
          <Link href="/problems">Back to problems</Link>
        </Button>
      </div>
    );
  }

  const messages = active.data?.messages ?? [];
  const loadingSaved = chat.activeId !== null && active.isPending && chat.pendingUser === null;
  const empty = messages.length === 0 && chat.pendingUser === null;

  return (
    <div className="mx-auto grid h-[calc(100dvh-4.0625rem)] min-h-[30rem] max-w-6xl gap-4 p-4 md:grid-cols-[16rem_1fr]">
      <aside className="flex min-h-0 flex-col md:border-r md:pr-4">
        <ConversationList
          conversations={conversations.data ?? []}
          activeId={chat.activeId}
          onSelect={chat.select}
          onRename={(id, title) => rename.mutate({ id, title })}
          onDelete={(id) => remove.mutate(id)}
        />
      </aside>

      <section aria-label="Chat" className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-background">
        <header className="flex items-center gap-2 border-b px-4 py-2.5">
          <Sparkles className="size-4 text-brand-violet" aria-hidden />
          <h1 className="text-sm font-semibold">{active.data?.title ?? "New conversation"}</h1>
          {status.data?.model && <span className="ml-auto text-xs text-muted-foreground">{status.data.model}</span>}
        </header>

        {loadingSaved ? (
          <div className="flex-1 space-y-3 p-4" role="status" aria-label="Loading conversation">
            <Skeleton className="h-16" />
            <Skeleton className="h-24" />
          </div>
        ) : empty && !chat.error ? (
          <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
            <p className="font-medium">Ask SahuCodeX AI anything about coding</p>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">
              Replies come from a local model and can be wrong. SahuJudge — not the AI — decides whether a solution is
              correct.
            </p>
          </div>
        ) : (
          <ChatThread
            messages={messages}
            pendingUser={chat.pendingUser}
            streamed={chat.streamed}
            streaming={chat.streaming}
            error={chat.error}
          />
        )}

        <ChatComposer disabled={false} streaming={chat.streaming} onSend={chat.send} onStop={chat.stop} />
      </section>
    </div>
  );
}
