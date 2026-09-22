"use client";

import { useQuery } from "@tanstack/react-query";

import { api, apiPublic } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/store";
import type {
  ContestAdminInput,
  ContestAdminOut,
  ContestDetail,
  ContestListItem,
  ContestProblemOut,
  StandingsOut,
} from "@/lib/contests/types";
import type { RunQueued, SubmissionQueued } from "@/lib/submissions/types";

function useViewerKey() {
  return useAuthStore((s) => s.user?.id ?? "anonymous");
}

export function useContests() {
  return useQuery({
    queryKey: ["contests"],
    queryFn: () => apiPublic<ContestListItem[]>("/contests"),
    staleTime: 30_000,
  });
}

export function useContest(slug: string) {
  const viewer = useViewerKey();
  return useQuery({
    queryKey: ["contest", viewer, slug],
    queryFn: () => apiPublic<ContestDetail>(`/contests/${encodeURIComponent(slug)}`),
    enabled: slug.length > 0,
    // A contest's phase (and so what it may show) changes at start_time/end_time; refetch often enough that the
    // countdown transitioning to "running" also refreshes the problem list and registration state promptly.
    refetchInterval: 15_000,
  });
}

export function useContestProblem(slug: string, label: string | undefined) {
  return useQuery({
    queryKey: ["contest-problem", slug, label],
    queryFn: () => apiPublic<ContestProblemOut>(`/contests/${encodeURIComponent(slug)}/problems/${label}`),
    enabled: Boolean(label),
  });
}

export function useStandings(slug: string, options: { live?: boolean } = {}) {
  return useQuery({
    queryKey: ["standings", slug],
    queryFn: () => apiPublic<StandingsOut>(`/contests/${encodeURIComponent(slug)}/standings`),
    enabled: slug.length > 0,
    refetchInterval: options.live ? 20_000 : false,
  });
}

export const registerForContest = (slug: string): Promise<void> =>
  api<void>(`/contests/${encodeURIComponent(slug)}/register`, { method: "POST" });

export const submitContestCode = (slug: string, label: string, body: { language: string; source_code: string }) =>
  api<SubmissionQueued>(`/contests/${encodeURIComponent(slug)}/problems/${label}/submit`, { method: "POST", body });

export const runContestCode = (
  slug: string,
  label: string,
  body: { language: string; source_code: string; mode: "samples" | "custom"; input?: string },
) => api<RunQueued>(`/contests/${encodeURIComponent(slug)}/problems/${label}/run`, { method: "POST", body });

// --- admin -----------------------------------------------------------------------------------------------------

export function useAdminContests() {
  return useQuery({
    queryKey: ["admin-contests"],
    queryFn: () => api<ContestAdminOut[]>("/admin/contests"),
  });
}

export function useAdminContest(id: string | undefined) {
  return useQuery({
    queryKey: ["admin-contest", id],
    queryFn: () => api<ContestAdminOut>(`/admin/contests/${id}`),
    enabled: Boolean(id),
  });
}

export const createContest = (body: ContestAdminInput) =>
  api<ContestAdminOut>("/admin/contests", { method: "POST", body });

export const updateContest = (id: string, body: ContestAdminInput) =>
  api<ContestAdminOut>(`/admin/contests/${id}`, { method: "PUT", body });

export const setContestPublished = (id: string, published: boolean) =>
  api<ContestAdminOut>(`/admin/contests/${id}/${published ? "publish" : "unpublish"}`, { method: "POST" });
