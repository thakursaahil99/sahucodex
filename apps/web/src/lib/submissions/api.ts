"use client";

import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { Page } from "@/lib/problems/types";
import {
  isPending,
  type RunOut,
  type RunQueued,
  type SubmissionDetail,
  type SubmissionQueued,
  type SubmissionSummary,
} from "@/lib/submissions/types";

export interface SubmissionFilters {
  page: number;
  problem?: string;
  verdict?: string;
  language?: string;
  status?: string;
}

function toQuery(filters: SubmissionFilters): string {
  const q = new URLSearchParams({ page: String(filters.page), limit: "20" });
  if (filters.problem) q.set("problem", filters.problem);
  if (filters.verdict) q.set("verdict", filters.verdict);
  if (filters.language) q.set("language", filters.language);
  if (filters.status) q.set("status", filters.status);
  return q.toString();
}

/**
 * A user's submission history. Polls lightly while any row on the current page is still being judged, and stops
 * once everything has settled — this list can span many problems at once, so it uses polling rather than the
 * WebSocket (which is used where a single submission is being watched: the workspace and the detail page below).
 */
export function useSubmissions(filters: SubmissionFilters): UseQueryResult<Page<SubmissionSummary>> {
  const q = toQuery(filters);
  return useQuery({
    queryKey: ["submissions", q],
    queryFn: () => api<Page<SubmissionSummary>>(`/users/me/submissions?${q}`),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((row) => isPending(row.status)) ? 2000 : false),
  });
}

/** One submission's detail. `live: false` turns off the polling fallback (the caller is relying on the socket instead). */
export function useSubmission(id: string | undefined, options: { live?: boolean } = {}): UseQueryResult<SubmissionDetail> {
  const live = options.live ?? true;
  return useQuery({
    queryKey: ["submission", id],
    queryFn: () => api<SubmissionDetail>(`/submissions/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => (live && isPending(query.state.data?.status) ? 1500 : false),
  });
}

export const submitCode = (body: { problem_slug: string; language: string; source_code: string }) =>
  api<SubmissionQueued>("/submissions", { method: "POST", body });

export const runCode = (body: {
  problem_slug: string;
  language: string;
  source_code: string;
  mode: "samples" | "custom";
  input?: string;
}) => api<RunQueued>("/run", { method: "POST", body });

export const getRun = (id: string) => api<RunOut>(`/run/${encodeURIComponent(id)}`);

/** The one run currently being watched (the workspace's Run button). Polls fast while it's still going. */
export function useRun(id: string | undefined, options: { live?: boolean } = {}): UseQueryResult<RunOut> {
  const live = options.live ?? true;
  return useQuery({
    queryKey: ["run", id],
    queryFn: () => getRun(id!),
    enabled: Boolean(id),
    refetchInterval: (query) => (live && isPending(query.state.data?.status) ? 800 : false),
  });
}

export const getWsTicket = () => api<{ ticket: string; expires_in: number }>("/ws/ticket", { method: "POST" });
