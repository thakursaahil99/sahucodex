"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";
import type { AdminPage, AdminProblem, ProblemStatus, ValidationIssue } from "@/lib/admin/problem-form";
import { toInput, type ProblemForm } from "@/lib/admin/problem-form";
import type { Tag } from "@/lib/problems/types";

export interface AdminListParams {
  page: number;
  q: string;
  status: ProblemStatus | "";
}

export function useAdminProblems(params: AdminListParams) {
  const query = new URLSearchParams({ page: String(params.page), limit: "20" });
  if (params.q) query.set("q", params.q);
  if (params.status) query.set("status", params.status);
  return useQuery({
    queryKey: ["admin", "problems", query.toString()],
    queryFn: () => api<AdminPage>(`/admin/problems?${query.toString()}`),
  });
}

/** Total problems in a given state (`limit=1` keeps it cheap; only `total` is used). */
export function useAdminCount(status: ProblemStatus) {
  return useQuery({
    queryKey: ["admin", "count", status],
    queryFn: async () => (await api<AdminPage>(`/admin/problems?limit=1&status=${status}`)).total,
  });
}

export function useAdminProblem(id: string | undefined) {
  return useQuery({
    queryKey: ["admin", "problem", id],
    queryFn: () => api<AdminProblem>(`/admin/problems/${id}`),
    enabled: Boolean(id),
    // The editor owns the form state after loading; a background refetch must not clobber unsaved edits.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

export const createProblem = (form: ProblemForm) =>
  api<AdminProblem>("/admin/problems", { method: "POST", body: toInput(form) });

export const updateProblem = (id: string, form: ProblemForm) =>
  api<AdminProblem>(`/admin/problems/${id}`, { method: "PUT", body: toInput(form) });

export const problemAction = (id: string, action: "publish" | "unpublish" | "archive" | "restore") =>
  api<AdminProblem>(`/admin/problems/${id}/${action}`, { method: "POST" });

export const validateProblem = (id: string) =>
  api<{ ok: boolean; issues: ValidationIssue[] }>(`/admin/problems/${id}/validation`);

export const createTag = (name: string) => api<Tag>("/admin/tags", { method: "POST", body: { name } });

// --- analytics (phase 8) -------------------------------------------------------------------------------------

export interface PlatformTotals {
  users: number;
  published_problems: number;
  submissions: number;
  submissions_last_30d: number;
  published_contests: number;
  discussions: number;
}

export interface AiFeatureUsage {
  feature: string;
  requests: number;
  failed: number;
  avg_duration_ms: number;
  avg_response_chars: number;
}

export interface AiUsageSummary {
  window_days: number;
  total_requests: number;
  failed_requests: number;
  by_feature: AiFeatureUsage[];
}

export interface Analytics {
  platform: PlatformTotals;
  ai_usage: AiUsageSummary;
}

export function useAnalytics() {
  return useQuery({
    queryKey: ["admin", "analytics"],
    queryFn: () => api<Analytics>("/admin/analytics"),
    staleTime: 30_000,
  });
}
