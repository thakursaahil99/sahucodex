"use client";

import { Bot, User } from "lucide-react";
import { useEffect, useRef } from "react";

import { Markdown } from "@/components/ui/markdown";
import type { ChatMessage } from "@/lib/ai/types";
import { cn } from "@/lib/utils";

function Bubble({ role, children }: { role: ChatMessage["role"]; children: React.ReactNode }) {
  const assistant = role === "assistant";
  return (
    <div className={cn("flex gap-3", !assistant && "flex-row-reverse")}>
      <div
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full border",
          assistant ? "bg-brand-violet/15 text-brand-violet" : "bg-muted text-muted-foreground",
        )}
        aria-hidden
      >
        {assistant ? <Bot className="size-4" /> : <User className="size-4" />}
      </div>
      <div
        className={cn("min-w-0 max-w-[85%] rounded-2xl border px-4 py-3", assistant ? "bg-card" : "bg-muted/60")}
        data-role={role}
      >
        {children}
      </div>
    </div>
  );
}

interface ChatThreadProps {
  messages: ChatMessage[];
  pendingUser: string | null;
  streamed: string;
  streaming: boolean;
  error: string | null;
}

/** The transcript. Model replies are Markdown rendered as inert content — never HTML, never executed. */
export function ChatThread({ messages, pendingUser, streamed, streaming, error }: ChatThreadProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, pendingUser, streamed]);

  return (
    <div className="flex-1 space-y-5 overflow-y-auto p-4" role="log" aria-live="polite" aria-label="Conversation">
      {messages.map((message) => (
        <Bubble key={message.id} role={message.role}>
          <Markdown>{message.content}</Markdown>
        </Bubble>
      ))}
      {pendingUser !== null && (
        <Bubble role="user">
          <Markdown>{pendingUser}</Markdown>
        </Bubble>
      )}
      {streaming && (
        <Bubble role="assistant">
          {streamed ? (
            <Markdown>{streamed}</Markdown>
          ) : (
            <p className="text-sm text-muted-foreground" role="status">
              SahuCodeX AI is thinking… a local model can take a little while to start.
            </p>
          )}
        </Bubble>
      )}
      {error && (
        <p className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm" role="alert">
          {error}
        </p>
      )}
      <div ref={endRef} />
    </div>
  );
}
