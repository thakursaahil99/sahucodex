"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import { aiErrorMessage } from "@/lib/ai/errors";
import { streamAi } from "@/lib/ai/stream";
import type { StreamEvent } from "@/lib/ai/types";

export interface Chat {
  activeId: string | null;
  /** The user's message while its reply streams in, before the saved transcript includes it. */
  pendingUser: string | null;
  /** The assistant's reply so far. */
  streamed: string;
  streaming: boolean;
  error: string | null;
  /** Resolves to whether the server accepted the message (so the composer knows to keep the text if it did not). */
  send: (text: string) => Promise<boolean>;
  stop: () => void;
  /** Open a saved conversation, or `null` for a blank new one. */
  select: (id: string | null) => void;
}

/**
 * Drives one Assistant conversation: sends a message (creating the conversation on the first one), streams the
 * reply, and reconciles with the saved transcript when the stream ends.
 */
export function useChat(problemSlug?: string): Chat {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const [streamed, setStreamed] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => abortRef.current?.abort(), []);
  useEffect(() => () => abortRef.current?.abort(), []);

  const select = useCallback((id: string | null) => {
    abortRef.current?.abort();
    setActiveId(id);
    setPendingUser(null);
    setStreamed("");
    setError(null);
  }, []);

  const send = useCallback(
    async (text: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      let id = activeId;
      let accepted = false;
      setError(null);
      setPendingUser(text);
      setStreamed("");
      setStreaming(true);

      const onEvent = (event: StreamEvent) => {
        if (event.type === "start") {
          accepted = true;
          id = event.conversationId;
          setActiveId(id);
        } else if (event.type === "token") {
          setStreamed((so_far) => so_far + event.content);
        } else if (event.type === "error") {
          setError(event.message);
        }
      };

      try {
        await streamAi(
          id ? `/ai/conversations/${id}/messages` : "/ai/conversations",
          id ? { content: text } : { message: text, ...(problemSlug ? { problem_slug: problemSlug } : {}) },
          onEvent,
          controller.signal,
        );
      } catch (caught) {
        if (!controller.signal.aborted) setError(aiErrorMessage(caught));
      } finally {
        // Pull the saved transcript first, then drop the temporary bubbles, so nothing flickers away and back.
        if (id) await queryClient.refetchQueries({ queryKey: ["ai-conversation", id] });
        await queryClient.invalidateQueries({ queryKey: ["ai-conversations"] });
        setStreaming(false);
        setPendingUser(null);
        setStreamed("");
      }
      return accepted;
    },
    [activeId, problemSlug, queryClient],
  );

  return { activeId, pendingUser, streamed, streaming, error, send, stop, select };
}
