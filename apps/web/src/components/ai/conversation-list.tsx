"use client";

import { Check, MessageSquarePlus, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import type { ConversationSummary } from "@/lib/ai/types";
import { cn } from "@/lib/utils";

interface ConversationListProps {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function ConversationList({ conversations, activeId, onSelect, onRename, onDelete }: ConversationListProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  function commit(id: string) {
    const title = draft.trim();
    if (title) onRename(id, title);
    setEditing(null);
  }

  return (
    <nav aria-label="Conversations" className="flex min-h-0 flex-1 flex-col gap-2">
      <Button variant="outline" size="sm" onClick={() => onSelect(null)}>
        <MessageSquarePlus aria-hidden /> New chat
      </Button>
      <ul className="min-h-0 flex-1 space-y-1 overflow-y-auto">
        {conversations.map((conversation) => (
          <li key={conversation.id}>
            {editing === conversation.id ? (
              <form
                className="flex items-center gap-1"
                onSubmit={(event) => {
                  event.preventDefault();
                  commit(conversation.id);
                }}
              >
                <Input
                  autoFocus
                  aria-label="Conversation title"
                  value={draft}
                  maxLength={120}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => event.key === "Escape" && setEditing(null)}
                  className="h-8"
                />
                <Button type="submit" variant="ghost" size="icon" className="size-8" aria-label="Save title">
                  <Check aria-hidden />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8"
                  aria-label="Cancel rename"
                  onClick={() => setEditing(null)}
                >
                  <X aria-hidden />
                </Button>
              </form>
            ) : (
              <div
                className={cn(
                  "flex items-center gap-1 rounded-lg pr-1",
                  conversation.id === activeId ? "bg-muted" : "hover:bg-muted/60",
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect(conversation.id)}
                  aria-current={conversation.id === activeId ? "true" : undefined}
                  className="min-w-0 flex-1 truncate rounded-lg px-3 py-2 text-left text-sm"
                >
                  {conversation.title}
                </button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-7 shrink-0"
                  aria-label={`Rename ${conversation.title}`}
                  onClick={() => {
                    setDraft(conversation.title);
                    setEditing(conversation.id);
                  }}
                >
                  <Pencil aria-hidden />
                </Button>
                <ConfirmDialog
                  trigger={
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7 shrink-0"
                      aria-label={`Delete ${conversation.title}`}
                    >
                      <Trash2 aria-hidden />
                    </Button>
                  }
                  title="Delete this conversation?"
                  description="The whole conversation is removed permanently."
                  confirmLabel="Delete"
                  destructive
                  onConfirm={() => onDelete(conversation.id)}
                />
              </div>
            )}
          </li>
        ))}
        {conversations.length === 0 && (
          <li className="px-3 py-2 text-sm text-muted-foreground">No conversations yet.</li>
        )}
      </ul>
    </nav>
  );
}
