"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiPublic } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/store";
import { filtersToApiQuery, type ProblemFilters } from "@/lib/problems/filters";
import type { Hint, Language, Page, ProblemDetail, ProblemListItem, TagWithCount } from "@/lib/problems/types";

/** Personalised results (solved/attempted marks) depend on who is asking, so the user is part of every key. */
function useViewerKey() {
  return useAuthStore((s) => s.user?.id ?? "anonymous");
}

export function useProblemList(filters: ProblemFilters) {
  const viewer = useViewerKey();
  return useQuery({
    queryKey: ["problems", viewer, filtersToApiQuery(filters)],
    queryFn: () => apiPublic<Page<ProblemListItem>>(`/problems?${filtersToApiQuery(filters)}`),
    placeholderData: keepPreviousData,
  });
}

export function useProblem(slug: string) {
  const viewer = useViewerKey();
  return useQuery({
    queryKey: ["problem", viewer, slug],
    queryFn: () => apiPublic<ProblemDetail>(`/problems/${encodeURIComponent(slug)}`),
  });
}

export function useTags() {
  return useQuery({
    queryKey: ["tags"],
    queryFn: () => apiPublic<TagWithCount[]>("/tags"),
    staleTime: 5 * 60_000,
  });
}

export function useLanguages() {
  return useQuery({
    queryKey: ["languages"],
    queryFn: () => apiPublic<Language[]>("/languages"),
    staleTime: 30 * 60_000,
  });
}

export function fetchHint(slug: string, index: number): Promise<Hint> {
  return apiPublic<Hint>(`/problems/${encodeURIComponent(slug)}/hints/${index}`);
}
