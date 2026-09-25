"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, apiPublic } from "@/lib/api/client";
import type { Page } from "@/lib/problems/types";
import type {
  CommentOut,
  DiscussionDetail,
  DiscussionListItem,
  NotificationOut,
  RecentDiscussionItem,
  ReportOut,
  TargetType,
} from "@/lib/community/types";

export function useDiscussions(problemSlug: string) {
  return useQuery({
    queryKey: ["discussions", problemSlug],
    queryFn: () => apiPublic<DiscussionListItem[]>(`/problems/${encodeURIComponent(problemSlug)}/discussions`),
    enabled: problemSlug.length > 0,
  });
}

/** The cross-problem feed behind the `/discussions` landing page (not a single problem's own tab). */
export function useRecentDiscussions(page: number, limit = 20) {
  return useQuery({
    queryKey: ["discussions-recent", page, limit],
    queryFn: () => apiPublic<Page<RecentDiscussionItem>>(`/discussions?page=${page}&limit=${limit}`),
    placeholderData: keepPreviousData,
  });
}

export function useDiscussion(id: string | undefined) {
  return useQuery({
    queryKey: ["discussion", id],
    queryFn: () => apiPublic<DiscussionDetail>(`/discussions/${id}`),
    enabled: Boolean(id),
  });
}

export const createDiscussion = (problemSlug: string, body: { title: string; body: string }) =>
  api<DiscussionListItem>(`/problems/${encodeURIComponent(problemSlug)}/discussions`, { method: "POST", body });

export const addComment = (discussionId: string, body: { body: string }) =>
  api<CommentOut>(`/discussions/${discussionId}/comments`, { method: "POST", body });

export const castVote = (targetType: TargetType, targetId: string, value: 1 | -1) =>
  api<void>(`/community/${targetType}/${targetId}/vote`, { method: "PUT", body: { value } });

export const removeVote = (targetType: TargetType, targetId: string) =>
  api<void>(`/community/${targetType}/${targetId}/vote`, { method: "DELETE" });

export const reportContent = (targetType: TargetType, targetId: string, reason: string) =>
  api<void>(`/community/${targetType}/${targetId}/report`, { method: "POST", body: { reason } });

// --- notifications -----------------------------------------------------------------------------------------------

export function useNotifications(unreadOnly = false, enabled = true) {
  return useQuery({
    queryKey: ["notifications", unreadOnly],
    queryFn: () => api<NotificationOut[]>(`/notifications${unreadOnly ? "?unread_only=true" : ""}`),
    enabled,
  });
}

export function useUnreadCount(enabled: boolean) {
  return useQuery({
    queryKey: ["notifications-unread-count"],
    queryFn: () => api<{ count: number }>("/notifications/unread-count"),
    enabled,
    refetchInterval: enabled ? 30_000 : false,
  });
}

export const markNotificationRead = (id: string) => api<void>(`/notifications/${id}/read`, { method: "POST" });

export const markAllNotificationsRead = () => api<void>("/notifications/read-all", { method: "POST" });

// --- moderation ----------------------------------------------------------------------------------------------------

export function useReports(status?: "OPEN" | "RESOLVED" | "DISMISSED") {
  return useQuery({
    queryKey: ["moderation-reports", status],
    queryFn: () => api<ReportOut[]>(`/moderation/reports${status ? `?status=${status}` : ""}`),
  });
}

export const resolveReport = (reportId: string, action: "remove_content" | "dismiss") =>
  api<void>(`/moderation/reports/${reportId}/resolve`, { method: "POST", body: { action } });

export const lockDiscussion = (discussionId: string) =>
  api<void>(`/moderation/discussions/${discussionId}/lock`, { method: "POST" });

export const unlockDiscussion = (discussionId: string) =>
  api<void>(`/moderation/discussions/${discussionId}/unlock`, { method: "POST" });
