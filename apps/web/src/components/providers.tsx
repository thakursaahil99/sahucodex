"use client";

import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Toaster } from "@/components/ui/sonner";
import { isApiError } from "@/lib/api/http";
import { AUTH_CHANNEL, refreshSession } from "@/lib/auth/session";
import { useAuthStore } from "@/lib/auth/store";

const SESSION_HINT = "sahucodex_session=1";
const REFRESH_LEAD_MS = 60_000; // renew the access token a minute before it expires

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Client errors (4xx) won't fix themselves; only retry transient failures.
        retry: (count, error) => !(isApiError(error) && error.status >= 400 && error.status < 500) && count < 2,
      },
    },
  });
}

/** Keeps the in-memory session alive and in sync: bootstrap, proactive refresh, cross-tab logout. */
function AuthSessionManager() {
  const status = useAuthStore((s) => s.status);
  const expiresAt = useAuthStore((s) => s.expiresAt);
  const queryClient = useQueryClient();

  // Bootstrap: only ask the server if the non-secret session hint cookie says there may be a session.
  useEffect(() => {
    if (useAuthStore.getState().status !== "loading") return;
    if (document.cookie.split("; ").includes(SESSION_HINT)) {
      refreshSession().catch(() => useAuthStore.getState().setStatus("unavailable"));
    } else {
      useAuthStore.getState().clear();
    }
  }, []);

  useEffect(() => {
    if (!expiresAt) return;
    const delay = Math.max(expiresAt - Date.now() - REFRESH_LEAD_MS, 5_000);
    const timer = setTimeout(() => void refreshSession().catch(() => undefined), delay);
    return () => clearTimeout(timer);
  }, [expiresAt]);

  // Never leave one user's cached data in memory for the next person on this browser. Only a genuine sign-out
  // counts: the very first `loading -> anonymous` step of a visitor must NOT touch the cache, or it would orphan
  // the queries public pages have already started. Queries still on screen are reset (which refetches them as
  // the now-anonymous viewer) rather than cleared (which would leave them stuck loading).
  const previousStatus = useRef(status);
  useEffect(() => {
    if (previousStatus.current === "authenticated" && status === "anonymous") {
      queryClient.removeQueries({ type: "inactive" });
      void queryClient.resetQueries();
    }
    previousStatus.current = status;
  }, [status, queryClient]);

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(AUTH_CHANNEL);
    channel.onmessage = (event) => {
      if (event.data === "logout") useAuthStore.getState().clear();
    };
    return () => channel.close();
  }, []);

  return null;
}

export function Providers({ children, nonce }: { children: ReactNode; nonce?: string }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange nonce={nonce}>
      <QueryClientProvider client={queryClient}>
        <AuthSessionManager />
        {children}
        <Toaster />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
