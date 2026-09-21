"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { api } from "@/lib/api/client";
import type { SessionInfo, User } from "@/lib/api/types";
import { useAuthStore } from "@/lib/auth/store";

/** The signed-in user, straight from the API. Refetches when the tab regains focus. */
export function useMe() {
  const status = useAuthStore((s) => s.status);
  const setUser = useAuthStore((s) => s.setUser);
  const query = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/users/me"),
    enabled: status === "authenticated",
    refetchOnWindowFocus: true,
  });
  useEffect(() => {
    if (query.data) setUser(query.data);
  }, [query.data, setUser]);
  return query;
}

export function useSessions() {
  const status = useAuthStore((s) => s.status);
  return useQuery({
    queryKey: ["sessions"],
    queryFn: () => api<SessionInfo[]>("/auth/sessions"),
    enabled: status === "authenticated",
  });
}

export interface ProfileUpdate {
  bio?: string | null;
  country?: string | null;
  website?: string | null;
  github_url?: string | null;
  avatar_url?: string | null;
}

export const updateProfile = (changes: ProfileUpdate) => api<User>("/users/me", { method: "PATCH", body: changes });
