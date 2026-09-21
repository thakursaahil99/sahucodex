"use client";

import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/store";
import type { AiFeature, AiStatus, ConversationDetail, ConversationSummary, Generation } from "@/lib/ai/types";

/** Whether the server has a model chosen. Cheap (no model call), so it is safe to ask on every workspace load. */
export function useAiStatus() {
  const signedIn = useAuthStore((s) => s.status === "authenticated");
  return useQuery({
    queryKey: ["ai-status"],
    queryFn: () => api<AiStatus>("/ai/status"),
    enabled: signedIn,
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export interface GenerateInput {
  feature: AiFeature;
  problemSlug: string;
  language: string;
  code: string;
  previousHints: string[];
}

/** One-off Hint / Explain / Review. The problem is always passed by slug so the server builds the (public-only)
 * context itself; the client never sends problem text. */
export function generate({ feature, problemSlug, language, code, previousHints }: GenerateInput): Promise<Generation> {
  const body =
    feature === "hint"
      ? { problem_slug: problemSlug, language, code, previous_hints: previousHints }
      : { problem_slug: problemSlug, language, code };
  return api<Generation>(`/ai/${feature}`, { method: "POST", body });
}

export function useGenerate() {
  return useMutation({ mutationFn: generate });
}

export function useConversations() {
  return useQuery({
    queryKey: ["ai-conversations"],
    queryFn: () => api<ConversationSummary[]>("/ai/conversations"),
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ["ai-conversation", id],
    queryFn: () => api<ConversationDetail>(`/ai/conversations/${id}`),
    enabled: id !== null,
  });
}

export function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  return api<ConversationSummary>(`/ai/conversations/${id}`, { method: "PATCH", body: { title } });
}

export function deleteConversation(id: string): Promise<void> {
  return api<void>(`/ai/conversations/${id}`, { method: "DELETE" });
}
