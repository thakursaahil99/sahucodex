"use client";

import { useQuery } from "@tanstack/react-query";

import { apiPublic } from "@/lib/api/client";
import type { ProfileStats, PublicProfile } from "@/lib/profiles/types";

/** Public: anyone may view anyone's profile and stats, same as GitHub/LeetCode public activity. An empty username
 * (the dashboard, before the signed-in user has loaded) is never sent — that would hit /users//stats. */
export function useProfile(username: string) {
  return useQuery({
    queryKey: ["profile", username],
    queryFn: () => apiPublic<PublicProfile>(`/users/${encodeURIComponent(username)}`),
    enabled: username.length > 0,
  });
}

export function useProfileStats(username: string) {
  return useQuery({
    queryKey: ["profile-stats", username],
    queryFn: () => apiPublic<ProfileStats>(`/users/${encodeURIComponent(username)}/stats`),
    enabled: username.length > 0,
  });
}
